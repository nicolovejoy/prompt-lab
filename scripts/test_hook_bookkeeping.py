"""Standalone installed-copy contract tests. Disposable DB/Git only."""
from __future__ import annotations

import importlib.util
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = """
CREATE TABLE sessions (id INTEGER PRIMARY KEY, project TEXT NOT NULL,
 started_at TEXT DEFAULT (datetime('now')), ended_at TEXT, summary TEXT,
 hostname TEXT, claude_session_id TEXT);
CREATE TABLE commits (id INTEGER PRIMARY KEY, hash TEXT, message TEXT,
 timestamp TEXT, session_id INTEGER);
CREATE TABLE prompts (id INTEGER PRIMARY KEY, timestamp TEXT DEFAULT (datetime('now')),
 project TEXT, prompt TEXT NOT NULL, session_id INTEGER, context TEXT, hostname TEXT);
CREATE TABLE projects (name TEXT PRIMARY KEY);
"""
LOG_PROMPT = ROOT / 'workflow/hooks/log-prompt.sh'



class Fixture:
    def __init__(self, root):
        self.root = root.resolve()
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.repo)], check=True)
        self.host = self.root / 'host'
        # The installed prompt hook finds the DB through $HOME, so the disposable
        # DB lives at the path log-prompt.sh would open under a fake HOME.
        self.home = self.root / 'home'
        (self.home / '.claude').mkdir(parents=True)
        self.db = self.home / '.claude/prompt-history.db'
        with sqlite3.connect(self.db) as conn:
            conn.executescript(SCHEMA)
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/stage_codex_bookkeeping.py'),
                                 '--destination', str(self.host), '--db', str(self.db),
                                 '--workspace', str(self.repo)], capture_output=True, text=True)
        assert result.returncode == 0, 'Host bundle staging failed: ' + result.stderr
        self.command = json.loads((self.host / 'launch.json').read_text())

    def event(self, kind='SessionStart', native='thread-a', **extra):
        if kind == 'Stop':
            extra.setdefault('last_assistant_message', getattr(self, 'intents', {}).get(native, 'No handoff queued'))
        return dict(dict(hook_event_name=kind, session_id=native, cwd=str(self.repo),
                         turn_id='turn-1', stop_hook_active=False), **extra)

    def call(self, event, ok=True):
        result = subprocess.run(self.command, input=json.dumps(event), capture_output=True,
                                text=True, cwd=self.repo)
        if ok:
            assert result.returncode == 0, result.stderr
        return json.loads(result.stdout or '{}')

    def identity(self, native='thread-a'):
        output = self.call(self.event(native=native))
        context = output['hookSpecificOutput']['additionalContext']
        data = json.loads(context.split('GC_IDENTITY=', 1)[1])
        assert f"Session: {data['session_id']}|{data['started_at']}" in context
        return data

    def request(self, identity, **updates):
        request = {k: identity[k] for k in ('project', 'conversation_id', 'session_id', 'started_at')}
        request.update(version=1, request_id=str(uuid.uuid4()), summary='Disposable findings', commits=[])
        request.update(updates)
        path = Path(identity['request_path'])
        path.write_text(json.dumps(request))
        path.chmod(0o600)
        if not hasattr(self, 'intents'):
            self.intents = {}
        self.intents[identity['conversation_id']] = 'Queued GC_REQUEST=' + request['request_id'] + ':' + hashlib.sha256(path.read_bytes()).hexdigest()
        return path, request

    def log_prompt(self, native='thread-a', prompt='Ordinary prompt', **payload):
        """Run the real UserPromptSubmit prompt logger against the disposable HOME."""
        payload = dict(dict(hook_event_name='UserPromptSubmit', session_id=native, cwd=str(self.repo),
                            prompt=prompt), **payload)
        env = {k: v for k, v in os.environ.items() if k not in ('CODEX_THREAD_ID', 'GC_SESSION_SCOPE')}
        env['HOME'] = str(self.home)
        result = subprocess.run(['/bin/bash', str(LOG_PROMPT)], input=json.dumps(payload),
                                capture_output=True, text=True, env=env)
        assert result.returncode == 0, result.stderr
        return self.rows('SELECT * FROM prompts WHERE prompt=?', (prompt,))

    def rows(self, sql='SELECT * FROM sessions', args=()):
        with sqlite3.connect(self.db) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute(sql, args)]


def receipt(output):
    assert output['decision'] == 'block', output
    return json.loads(output['reason'].split('GC_RECEIPT=', 1)[1])


def test_identity_and_atomic_save(f):
    a = f.identity()
    assert f.identity() == a
    assert f.call(f.event('UserPromptSubmit'))['hookSpecificOutput']['additionalContext'].endswith(json.dumps(a, sort_keys=True))
    b = f.identity('thread-b')
    assert a['session_id'] != b['session_id']
    assert a['request_path'] != b['request_path']
    path, request = f.request(a)
    saved = receipt(f.call(f.event('Stop')))
    assert saved['status'] == 'saved' and saved['request_id'] == request['request_id']
    assert saved['session_id'] == a['session_id'] and saved['conversation_id'] == 'thread-a'
    rows = f.rows()
    assert rows[0]['summary'] == 'Disposable findings' and rows[0]['ended_at']
    assert rows[1]['ended_at'] is None and rows[1]['summary'] is None
    assert path.exists()
    event = f.event('Stop')
    event['stop_hook_active'] = True
    assert f.call(event) == {}
    assert f.identity() == a  # resume remains bound, even after closure
    assert f.rows() == rows



def test_wrong_identity_and_missing_host_context(f):
    a, b = f.identity(), f.identity('thread-b')
    for change in ({'session_id': b['session_id']}, {'conversation_id': 'thread-b'},
                   {'project': 'other'}, {'started_at': '1999-01-01 00:00:00'}):
        f.request(a, **change)
        out = f.call(f.event('Stop'))
        assert out['decision'] == 'block' and 'failed' in out['reason']
        assert all(r['ended_at'] is None and r['summary'] is None for r in f.rows())
    for field in ('session_id', 'cwd'):
        event = f.event()
        del event[field]
        assert 'pending' in f.call(event, ok=False)['systemMessage']
    assert len(f.rows()) == 2
    assert 'failed' in f.call(f.event('Stop', native='unknown'))['reason']
    assert len(f.rows()) == 2
    with sqlite3.connect(f.db) as conn:
        conn.execute('UPDATE session_identity_bindings SET session_id=? WHERE identity=?',
                     (b['session_id'], 'codex:thread-a'))
    assert 'Inconsistent' in f.call(f.event(), ok=False)['systemMessage']
    assert len(f.rows()) == 2


def git_commit(f):
    env = dict(os.environ, GIT_AUTHOR_DATE='2001-02-03T04:05:06Z', GIT_COMMITTER_DATE='2001-02-03T04:05:06Z')
    subprocess.run(['git', '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                    '-c', 'core.hooksPath=/dev/null', 'commit', '--allow-empty', '-qm', 'Original | message'],
                   cwd=f.repo, env=env, check=True)
    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=f.repo, text=True).strip()
    return dict(hash=sha, message='Original | message', timestamp=981173106)


def test_commits_retries_and_first_attribution(f):
    a, b = f.identity(), f.identity('thread-b')
    commit = git_commit(f)
    path, request = f.request(a, commits=[commit])
    saved = receipt(f.call(f.event('Stop')))
    assert saved['commits_inserted'] == 1
    rows = f.rows('SELECT * FROM commits')
    assert len(rows) == 1 and rows[0]['timestamp'] == '2001-02-03 04:05:06'
    assert rows[0]['message'] == 'Original | message' and rows[0]['session_id'] == a['session_id']
    event = f.event('Stop')
    event['turn_id'] = 'later-turn'
    assert receipt(f.call(event)) == saved
    assert f.rows('SELECT * FROM commits') == rows
    request['summary'] = 'Replacement with reused ID'
    path.write_text(json.dumps(request))
    assert 'already used' in f.call(event)['reason']
    assert f.rows()[0]['summary'] == 'Disposable findings'
    # A new request in a different conversation must not reassign an old hash.
    f.request(b, commits=[dict(commit, message='Changed', timestamp=1000000000)])
    assert receipt(f.call(f.event('Stop', native='thread-b')))['commits_inserted'] == 0
    assert f.rows('SELECT * FROM commits') == rows
    # The #57 unique index remains compatible; no migration required by consumer.
    with sqlite3.connect(f.db) as conn:
        conn.execute('CREATE UNIQUE INDEX commits_hash ON commits(hash)')
    f.request(a, commits=[commit])
    event = f.event('Stop')
    event['turn_id'] = 'another-turn'
    assert receipt(f.call(event))['commits_inserted'] == 0
    assert f.rows('SELECT * FROM commits') == rows


def test_unrelated_requests_and_missing_receipt(f):
    a, b = f.identity(), f.identity('thread-b')
    f.request(b)
    assert f.call(f.event('Stop')) == {}
    assert all(r['ended_at'] is None for r in f.rows())
    assert not f.rows('SELECT * FROM hook_bookkeeping_requests')
    f.request(a)
    assert f.rows()[0]['summary'] is None  # Writing a file is only queued.
    assert f.rows()[0]['ended_at'] is None


def test_malformed_and_unsafe_files(f):
    a = f.identity()
    path, good = f.request(a)
    variants = [b'{', b'\xff', b'[]', b'null', b'{}', b'x' * 131073, ('[' * 1500 + '0' + ']' * 1500).encode(),
                json.dumps(dict(good, sql='DROP TABLE sessions')).encode(),
                json.dumps(dict(good, summary='')).encode(),
                json.dumps(dict(good, summary='x' * 16385)).encode(),
                json.dumps(dict(good, session_id=True)).encode(),
                json.dumps(dict(good, commits=[{'hash': 'a' * 40, 'timestamp': True, 'message': 'x'}])).encode(),
                json.dumps(dict(good, commits=[{'hash': 'a' * 40, 'timestamp': 1, 'message': 'x', 'sql': 'x'}])).encode(),
                json.dumps(good).replace('"version": 1', '"version": 1, "version": 1').encode()]
    for data in variants:
        path.write_bytes(data)
        assert 'failed' in f.call(f.event('Stop'))['reason']
        assert f.rows()[0]['ended_at'] is None and f.rows()[0]['summary'] is None
    path.unlink()
    target = f.root / 'target'
    target.write_text(json.dumps(good))
    path.symlink_to(target)
    assert 'failed' in f.call(f.event('Stop'))['reason']
    assert target.read_text() == json.dumps(good)
    path.unlink()
    os.link(target, path)
    assert 'Unsafe' in f.call(f.event('Stop'))['reason']
    path.unlink()
    os.mkfifo(path)
    assert 'Unsafe' in f.call(f.event('Stop'))['reason']
    path.unlink()
    path.write_text(json.dumps(good))
    path.chmod(0o666)
    assert 'Unsafe' in f.call(f.event('Stop'))['reason']
    assert f.rows()[0]['ended_at'] is None
    event = f.event('Stop')
    event['stop_hook_active'] = True
    out = f.call(event, ok=False)
    assert 'decision' not in out and 'pending' in out['systemMessage']


def load_copy(f):
    def load(name, filename):
        spec = importlib.util.spec_from_file_location(name, f.host / filename)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    module = load('fixture_consumer', 'bookkeeping.py')
    resolver = load('fixture_identity', '_gc_session_identity.py')
    return module, (f.host, f.db, [f.repo], resolver)


def test_each_transaction_boundary_rolls_back(f):
    a = f.identity()
    commit = git_commit(f)
    f.request(a, commits=[commit])
    # Actual SQLite failures for commit persistence, summary/closure, and ledger.
    for table, operation in [('commits', 'INSERT'), ('sessions', 'UPDATE'),
                             ('hook_bookkeeping_requests', 'INSERT')]:
        with sqlite3.connect(f.db) as conn:
            conn.execute(f"CREATE TRIGGER deny_save BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT,'injected denial'); END")
        assert 'failed' in f.call(f.event('Stop'))['reason']
        assert f.rows()[0]['ended_at'] is None and f.rows()[0]['summary'] is None
        assert not f.rows('SELECT * FROM commits') and not f.rows('SELECT * FROM hook_bookkeeping_requests')
        with sqlite3.connect(f.db) as conn:
            conn.execute('DROP TRIGGER deny_save')
    module, host = load_copy(f)
    connect = sqlite3.connect
    for boundary in ('BEGIN', 'COMMIT', 'OPEN'):
        class FailingConnection(sqlite3.Connection):
            def execute(self, sql, *args):
                if boundary == 'BEGIN' and sql.startswith('BEGIN'):
                    raise sqlite3.OperationalError('injected lock denial')
                return super().execute(sql, *args)

            def commit(self):
                if boundary == 'COMMIT':
                    raise sqlite3.OperationalError('injected commit failure')
                return super().commit()

        def failing_connect(*args, **kwargs):
            if boundary == 'OPEN':
                raise sqlite3.OperationalError('injected open denial')
            return connect(*args, factory=FailingConnection, **kwargs)

        module.sqlite3.connect = failing_connect
        output = []
        try:
            try:
                module.run(f.event('Stop'), host, output.append)
                raise AssertionError('Expected boundary failure')
            except sqlite3.OperationalError:
                pass
        finally:
            module.sqlite3.connect = connect
        assert not output
        assert f.rows()[0]['ended_at'] is None and f.rows()[0]['summary'] is None
        assert not f.rows('SELECT * FROM commits')
    assert receipt(f.call(f.event('Stop')))['status'] == 'saved'


def test_replacement_and_read_denial_roll_back(f):
    a = f.identity()
    path, request = f.request(a)
    module, host = load_copy(f)
    real_read = module.read_request
    for failure in ('replace', 'deny'):
        count = 0

        def changed_read(p):
            nonlocal count
            count += 1
            if failure == 'deny':
                raise PermissionError('injected file denial')
            if count == 2:
                replacement = p.with_suffix('.replacement')
                replacement.write_text(json.dumps(request))
                replacement.replace(p)
            return real_read(p)

        module.read_request = changed_read
        output = []
        try:
            module.run(f.event('Stop'), host, output.append)
            raise AssertionError('Expected request failure')
        except (ValueError, PermissionError):
            pass
        assert not output and path.exists()
        assert f.rows()[0]['ended_at'] is None and f.rows()[0]['summary'] is None
        assert not f.rows('SELECT * FROM hook_bookkeeping_requests')


def test_crash_after_commit_before_receipt(f):
    a = f.identity()
    f.request(a, commits=[git_commit(f)])
    # A separate process really dies after the DB commit, before any output.
    code = """
import importlib.util, json, os, sys
spec = importlib.util.spec_from_file_location('hook', sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
event = json.loads(sys.argv[2])
m.run(event, m.load_host(), lambda output: os._exit(78))
"""
    result = subprocess.run([sys.executable, '-I', '-S', '-c', code,
                             str(f.host / 'bookkeeping.py'), json.dumps(f.event('Stop'))], capture_output=True)
    assert result.returncode == 78 and result.stdout == b''
    before = f.rows()
    assert before[0]['ended_at'] and len(f.rows('SELECT * FROM commits')) == 1
    assert f.rows('SELECT * FROM hook_bookkeeping_requests')[0]['emitted_turn'] is None
    assert receipt(f.call(f.event('Stop')))['status'] == 'saved'
    assert f.rows() == before and len(f.rows('SELECT * FROM commits')) == 1
    assert f.call(f.event('Stop')) == {}


def test_protected_dependency_and_environment(f):
    a = f.identity()
    f.request(a)
    # A dependency symlink into the checkout must be rejected before executing it.
    original = f.host / '_gc_session_identity.py'
    content = original.read_text()
    planted = f.repo / 'identity.py'
    planted.write_text("raise RuntimeError('AGENT CODE RAN')")
    original.unlink()
    original.symlink_to(planted)
    out = f.call(f.event('Stop'))
    assert 'Protected dependency' in out['reason'] and 'AGENT CODE RAN' not in out['reason']
    assert f.rows()[0]['ended_at'] is None
    original.unlink()
    original.write_text(content)
    original.chmod(0o600)
    # PYTHONPATH/sitecustomize and cwd modules cannot shadow host stdlib imports.
    (f.repo / 'sqlite3.py').write_text("raise RuntimeError('AGENT CODE RAN')")
    env = dict(os.environ, PYTHONPATH=str(f.repo), BASH_ENV=str(planted), CODEX_THREAD_ID='forged')
    result = subprocess.run(f.command, input=json.dumps(f.event('Stop')), env=env,
                            cwd=f.repo, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert receipt(json.loads(result.stdout))['conversation_id'] == 'thread-a'
    # Configured writable placement is independently refused by the entry point.
    config = f.host / 'config.json'
    config.write_text(json.dumps(dict(db=str(f.db), workspaces=[str(f.root)])))
    assert 'agent workspace' in f.call(f.event(), ok=False)['systemMessage']


def test_registration_failure_and_ambiguous_rows(f):
    with sqlite3.connect(f.db) as conn:
        conn.execute("CREATE TRIGGER deny_registration BEFORE INSERT ON sessions BEGIN SELECT RAISE(ABORT,'denied'); END")
    assert 'pending' in f.call(f.event(), ok=False)['systemMessage']
    assert f.rows() == []
    with sqlite3.connect(f.db) as conn:
        conn.execute('DROP TRIGGER deny_registration')
    a = f.identity()
    with sqlite3.connect(f.db) as conn:
        conn.execute('INSERT INTO sessions(project,claude_session_id) VALUES(?,?)', ('repo', 'codex:thread-a'))
    assert 'Inconsistent' in f.call(f.event(), ok=False)['systemMessage']
    assert len(f.rows()) == 2
    assert a['session_id'] == f.rows()[0]['id']


def test_invalid_host_events_surface_errors(f):
    for raw in ('null', '[]', '{', '{"hook_event_name":"Stop","hook_event_name":"Stop"}'):
        result = subprocess.run(f.command, input=raw, text=True, capture_output=True)
        assert result.returncode != 0
        assert 'pending' in json.loads(result.stdout)['systemMessage']
        assert 'Traceback' not in result.stderr
    assert f.rows() == []


def test_request_id_cannot_cross_conversations(f):
    a, b = f.identity(), f.identity('thread-b')
    _, request = f.request(a)
    receipt(f.call(f.event('Stop')))
    f.request(b, request_id=request['request_id'])
    assert 'already used' in f.call(f.event('Stop', native='thread-b'))['reason']
    assert f.rows()[1]['ended_at'] is None and f.rows()[1]['summary'] is None


def test_concurrent_registration_and_first_hash(f):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(lambda _: f.identity(), range(8)))
    assert len({r['session_id'] for r in rows}) == 1 and len(f.rows()) == 1
    b = f.identity('thread-b')
    commit = git_commit(f)
    f.request(rows[0], commits=[commit])
    f.request(b, commits=[commit])
    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts = list(pool.map(lambda native: receipt(f.call(f.event('Stop', native=native))),
                                ('thread-a', 'thread-b')))
    assert sorted(r['commits_inserted'] for r in receipts) == [0, 1]
    assert len(f.rows('SELECT * FROM commits')) == 1
    assert all(r['ended_at'] for r in f.rows())


def test_peer_cannot_forge_owner_intent(f):
    a, b = f.identity(), f.identity('thread-b')
    # B can write a perfectly formed request for A in the shared workspace.
    path, request = f.request(a)
    owner_event = f.event('Stop')
    owner_event['last_assistant_message'] = 'Finished audit. No handoff requested.'
    out = f.call(owner_event)
    assert 'intent' in out['reason']
    assert all(r['ended_at'] is None for r in f.rows())
    duplicate = f.event('Stop')
    duplicate['last_assistant_message'] *= 2
    assert 'intent' in f.call(duplicate)['reason']
    assert all(r['ended_at'] is None for r in f.rows())
    # Even after A queues, replacing its bytes invalidates A's host-event digest.
    request['summary'] = 'Planted by peer'
    path.write_text(json.dumps(request))
    assert 'intent' in f.call(f.event('Stop'))['reason']
    assert all(r['ended_at'] is None for r in f.rows())
    assert b['session_id'] != a['session_id']


def test_dotdot_cannot_place_protected_code_in_workspace(f):
    (f.root / 'bridge').mkdir()
    for destination, db in ((f.root / 'bridge/../repo/host', f.db),
                            (f.root / 'another-host', f.root / 'bridge/../repo/fake.db')):
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/stage_codex_bookkeeping.py'),
                                 '--destination', str(destination), '--db', str(db),
                                 '--workspace', str(f.repo)], capture_output=True, text=True)
        assert result.returncode != 0 and 'outside every agent workspace' in result.stderr
        assert not destination.exists()
    # Entry point independently catches a tampered installed DB path.
    inside = f.repo / 'fake.db'
    inside.write_bytes(f.db.read_bytes())
    (f.host / 'config.json').write_text(json.dumps(dict(db=str(f.root / 'bridge/../repo/fake.db'), workspaces=[str(f.repo)])))
    assert 'agent workspace' in f.call(f.event(), ok=False)['systemMessage']


def test_queued_but_missing_request_is_explicit_failure(f):
    a = f.identity()
    path, _ = f.request(a)
    path.unlink()
    out = f.call(f.event('Stop'))
    assert out.get('decision') == 'block' and 'missing' in out['reason']
    assert f.rows()[0]['ended_at'] is None


def test_corrupt_started_at_is_not_injected(f):
    a = f.identity()
    with sqlite3.connect(f.db) as conn:
        conn.execute('UPDATE sessions SET started_at=NULL WHERE id=?', (a['session_id'],))
    out = f.call(f.event(), ok=False)
    assert 'hookSpecificOutput' not in out and 'pending' in out['systemMessage']

def test_log_prompt_and_consumer_share_codex_identity(f):
    # Codex runs the installed prompt logger (log-prompt.sh) on UserPromptSubmit
    # alongside the host consumer. Codex events carry turn_id; Claude's do not.
    codex = dict(turn_id='turn-1', model='gpt-fixture', transcript_path=None)
    logged = f.log_prompt(prompt='First Codex prompt', **codex)
    assert len(logged) == 1
    a = f.identity()  # Must not see a colliding bare-native row.
    assert logged[0]['session_id'] == a['session_id']
    assert [r['claude_session_id'] for r in f.rows()] == ['codex:thread-a']
    assert f.log_prompt(prompt='Second Codex prompt', **codex)[0]['session_id'] == a['session_id']
    f.request(a)
    assert receipt(f.call(f.event('Stop')))['session_id'] == a['session_id']
    assert len(f.rows()) == 1
    # Claude's path is unchanged: no turn_id means a bare native Claude UUID row.
    claude = f.log_prompt(native='claude-uuid', prompt='Claude prompt')
    row = f.rows('SELECT * FROM sessions WHERE id=?', (claude[0]['session_id'],))[0]
    assert row['claude_session_id'] == 'claude-uuid'


def test_legacy_bare_codex_row_is_left_alone(f):
    # Rows written before the fix carry the bare native Codex ID. They were never
    # handed to an agent by the consumer, so they are historical, not an owner.
    with sqlite3.connect(f.db) as conn:
        legacy = conn.execute("INSERT INTO sessions(project,claude_session_id) VALUES('repo','thread-a')").lastrowid
        conn.execute("INSERT INTO prompts(project,prompt,session_id) VALUES('repo','old',?)", (legacy,))
    a = f.identity()
    assert a['session_id'] != legacy
    f.request(a)
    assert receipt(f.call(f.event('Stop')))['session_id'] == a['session_id']
    old = f.rows('SELECT * FROM sessions WHERE id=?', (legacy,))[0]
    assert old['claude_session_id'] == 'thread-a' and old['summary'] is None and old['ended_at'] is None
    assert f.log_prompt(prompt='Resumed prompt', turn_id='turn-2')[0]['session_id'] == a['session_id']


def test_receipt_is_delivered_once(f):
    a = f.identity()
    f.request(a)
    saved = receipt(f.call(f.event('Stop')))
    for n in (2, 3):  # Two ordinary later turns; the request file is still present.
        event = f.event('Stop', turn_id=f'turn-{n}', last_assistant_message=f'Ordinary answer {n}')
        assert f.call(event) == {}, n
    # An explicit replay of the same intent still gets the durable receipt.
    event = f.event('Stop', turn_id='turn-4')
    assert receipt(f.call(event)) == saved


def main():
    tests = [v for k, v in globals().items() if k.startswith('test_') and callable(v)]
    for test in tests:
        with tempfile.TemporaryDirectory(prefix='gc-hook-test-') as tmp:
            test(Fixture(Path(tmp)))
        print('PASS', test.__name__)
    print(f'PASS {len(tests)} hook bookkeeping scenario groups')


if __name__ == '__main__':
    main()
