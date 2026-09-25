#!/usr/bin/env python3
"""Host-only Codex hook. Launch an installed copy with Python -I -S.

No database default and no agent-controlled command/config arguments. Configuration
and all non-stdlib dependencies are copied alongside this entry point by staging.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
import importlib.util
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
import sys
import uuid

MAX_REQUEST = 131072
MAX_EVENT = 1048576


def exact(value, keys):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError('Unknown or missing fields')


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


def decode(data):
    try:
        return json.loads(data, object_pairs_hook=unique_object)
    except RecursionError as exc:
        raise ValueError('JSON nesting exceeds the supported bound') from exc


def small_text(value, limit, label):
    if not isinstance(value, str) or not value.strip() or len(value.encode('utf-8')) > limit or '\x00' in value:
        raise ValueError(f'Invalid {label}')
    return value


def protected(path, workspaces):
    """Structural guard, not an OS sandbox test. Pilot must prove effective denies."""
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Protected dependency must not be a symlink')
    path = path.resolve(strict=True)
    if any(path == root or root in path.parents for root in workspaces):
        raise ValueError('Protected dependency is in an agent workspace')
    info = path.stat()
    if info.st_uid not in (0, os.getuid()) or info.st_mode & 0o022:
        raise ValueError('Unsafe protected dependency ownership/mode')
    return path


def load_host():
    bundle = Path(__file__).absolute().parent
    config = decode((bundle / 'config.json').read_bytes())
    exact(config, ('db', 'workspaces'))
    roots = [Path(p).resolve(strict=True) for p in config['workspaces']]
    if not roots:
        raise ValueError('No configured pilot workspace')
    for name in ('bookkeeping.py', '_gc_session_identity.py', '_gc_project.sh', 'config.json'):
        protected(bundle / name, roots)
    protected(bundle, roots)
    # -I excludes cwd/PYTHONPATH; -S excludes site packages and executable .pth.
    if not sys.flags.isolated or not sys.flags.no_site:
        raise ValueError('Host hook requires isolated Python -I -S')
    for path in (Path(sys.executable).resolve(), Path(os.__file__).resolve(), *map(Path, sys.path)):
        if any(path == root or root in path.parents for root in roots):
            raise ValueError('Python dependency is in an agent workspace')
    db = protected(Path(config['db']), roots)
    spec = importlib.util.spec_from_file_location('gc_host_identity', bundle / '_gc_session_identity.py')
    identity = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(identity)
    return bundle, db, roots, identity


def host_binding(event, bundle, roots):
    native = small_text(event.get('session_id'), 120, 'host conversation')
    if not re.fullmatch(r'[A-Za-z0-9._-]+', native):
        raise ValueError('Invalid host conversation')
    cwd = Path(small_text(event.get('cwd'), 4096, 'host cwd')).resolve(strict=True)
    workspace = next((p for p in roots if p == cwd or p in cwd.parents), None)
    if workspace is None:
        raise ValueError('Host cwd is outside configured pilot workspaces')
    result = subprocess.run(['/bin/bash', '--noprofile', '--norc', '-c',
                             'source "$1"; gc_resolve_project "$2"', 'gc-host',
                             str(bundle / '_gc_project.sh'), str(cwd)],
                            env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'},
                            capture_output=True, text=True, check=True, timeout=10)
    project = small_text(result.stdout, 256, 'resolved project')
    key = hashlib.sha256(json.dumps([project, native]).encode()).hexdigest()
    return project, native, workspace / f'.gc-handoff-{key}.json'


def bound_row(conn, resolver, project, native, register=False):
    owner = 'codex:' + native
    # Existing resolver's newest-native behavior is not acceptable for ambiguous
    # host identities: two rows owned by one conversation is corruption.
    # A row carrying the BARE native ID is ignored, not adopted and not an error.
    # log-prompt.sh wrote those for Codex before it learned the `codex:` prefix;
    # no such row was ever handed to an agent by this hook, so no request can name
    # it, and the bare namespace belongs to Claude. It stays as history.
    rows = conn.execute('SELECT * FROM sessions WHERE project=? AND claude_session_id=?',
                        (project, owner)).fetchall()
    if len(rows) > 1:
        raise ValueError('Inconsistent conversation identity; human review required')
    binding = conn.execute('SELECT session_id FROM session_identity_bindings WHERE project=? AND identity=?',
                           (project, owner)).fetchone()
    if binding and (not rows or binding[0] != rows[0]['id']):
        raise ValueError('Inconsistent conversation binding')
    row = resolver.register(conn, project, owner) if register else resolver.resolve(conn, project, owner)
    if row is None:
        raise ValueError('Missing host session identity')
    started_at = small_text(row['started_at'], 32, 'stored session start')
    datetime.strptime(started_at, '%Y-%m-%d %H:%M:%S')
    return row


def signature(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def read_request(path):
    # Walk directories using descriptors: no symlink in any path component.
    fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        handle = os.open(path.name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=fd)
        try:
            before = os.fstat(handle)
            if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid()
                    or before.st_nlink != 1 or before.st_mode & 0o022 or before.st_size > MAX_REQUEST):
                raise ValueError('Unsafe or oversized request file')
            data = b''
            while len(data) <= MAX_REQUEST:
                chunk = os.read(handle, min(16384, MAX_REQUEST + 1 - len(data)))
                if not chunk:
                    break
                data += chunk
            after = os.fstat(handle)
            named = os.stat(path.name, dir_fd=fd, follow_symlinks=False)
            if len(data) > MAX_REQUEST or signature(before) != signature(after) or signature(after) != signature(named):
                raise ValueError('Request changed during read')
            return data, signature(after)
        finally:
            os.close(handle)
    finally:
        os.close(fd)


def validate_request(data, project, native, row):
    request = decode(data)
    exact(request, ('version', 'request_id', 'project', 'conversation_id', 'session_id',
                    'started_at', 'summary', 'commits'))
    if type(request['version']) is not int or request['version'] != 1:
        raise ValueError('Unsupported request version')
    rid = request['request_id']
    if not isinstance(rid, str) or str(uuid.UUID(rid)) != rid:
        raise ValueError('Request ID must be a canonical UUID')
    if (type(request['session_id']) is not int or request['session_id'] != row['id']
            or request['project'] != project or request['conversation_id'] != native
            or request['started_at'] != row['started_at']):
        raise ValueError('Request does not belong to this project and conversation session')
    small_text(request['summary'], 16384, 'summary')
    commits = request['commits']
    if not isinstance(commits, list) or len(commits) > 256:
        raise ValueError('Invalid commit list')
    hashes = set()
    for commit in commits:
        exact(commit, ('hash', 'message', 'timestamp'))
        sha = commit['hash']
        if not isinstance(sha, str) or not re.fullmatch(r'(?:[0-9a-f]{40}|[0-9a-f]{64})', sha) or sha in hashes:
            raise ValueError('Invalid or duplicate commit hash')
        hashes.add(sha)
        small_text(commit['message'], 4096, 'commit message')
        if type(commit['timestamp']) is not int or not 0 <= commit['timestamp'] <= 253402300799:
            raise ValueError('Invalid UTC commit timestamp')
    return request


def initialize(conn, resolver):
    resolver.initialize(conn)
    conn.execute('''CREATE TABLE IF NOT EXISTS hook_bookkeeping_requests (
        request_id TEXT PRIMARY KEY, project TEXT NOT NULL, conversation_id TEXT NOT NULL,
        session_id INTEGER NOT NULL, digest TEXT NOT NULL, receipt TEXT NOT NULL,
        emitted_turn TEXT)''')


def intents(event):
    message = event.get('last_assistant_message')
    if not isinstance(message, str):
        return [], 0
    return (re.findall(r'GC_REQUEST=([0-9a-f-]{36}):([0-9a-f]{64})(?![0-9a-f])', message),
            message.count('GC_REQUEST='))


def save(conn, request, digest, project, native, row, event):
    prior = conn.execute('SELECT * FROM hook_bookkeeping_requests WHERE request_id=?',
                         (request['request_id'],)).fetchone()
    if prior:
        if (prior['digest'], prior['project'], prior['conversation_id'], prior['session_id']) != (
                digest, project, native, row['id']):
            raise ValueError('Request ID was already used with different content or ownership')
        return json.loads(prior['receipt']), prior['emitted_turn']
    markers, count = intents(event)
    if len(markers) != 1 or count != 1 or markers[0] != (request['request_id'], digest):
        raise ValueError('Missing or inconsistent host conversation request intent')
    inserted = 0
    for commit in request['commits']:
        # Global hash identity, compatible with commits_hash from issue #57.
        # BEGIN IMMEDIATE serializes this check even before that index is installed.
        if conn.execute('SELECT 1 FROM commits WHERE hash=? LIMIT 1', (commit['hash'],)).fetchone():
            continue
        conn.execute("INSERT INTO commits(hash,message,timestamp,session_id) VALUES(?,?,datetime(?,'unixepoch'),?)",
                     (commit['hash'], commit['message'], commit['timestamp'], row['id']))
        inserted += 1
    conn.execute("UPDATE sessions SET summary=?, ended_at=datetime('now') WHERE id=? AND project=?",
                 (request['summary'], row['id'], project))
    receipt = dict(status='saved', request_id=request['request_id'], project=project,
                   conversation_id=native, session_id=row['id'], started_at=row['started_at'],
                   commits_inserted=inserted)
    conn.execute('''INSERT INTO hook_bookkeeping_requests
        (request_id,project,conversation_id,session_id,digest,receipt) VALUES(?,?,?,?,?,?)''',
                 (request['request_id'], project, native, row['id'], digest, json.dumps(receipt, sort_keys=True)))
    return receipt, None


def emit(value):
    print(json.dumps(value), flush=True)


def run(event, host, output=emit):
    bundle, db, roots, resolver = host
    kind = event.get('hook_event_name')
    if kind not in ('SessionStart', 'UserPromptSubmit', 'Stop'):
        raise ValueError('Unsupported hook event')
    project, native, path = host_binding(event, bundle, roots)
    turn = small_text(event.get('turn_id'), 160, 'host turn') if kind == 'Stop' else None
    conn = sqlite3.connect(f'{db.as_uri()}?mode=rw', uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute('BEGIN IMMEDIATE')
        initialize(conn, resolver)
        row = bound_row(conn, resolver, project, native, register=kind != 'Stop')
        if kind != 'Stop':
            identity = dict(project=project, conversation_id=native, session_id=row['id'],
                            started_at=row['started_at'], request_path=str(path))
            conn.commit()
            context = f"Session: {row['id']}|{row['started_at']}\nGC_IDENTITY=" + json.dumps(identity, sort_keys=True)
            output({'hookSpecificOutput': {'hookEventName': kind, 'additionalContext': context}})
            return
        try:
            data, snapshot = read_request(path)
        except FileNotFoundError:
            if 'GC_REQUEST=' in str(event.get('last_assistant_message', '')):
                raise ValueError('Queued request is missing') from None
            conn.rollback()
            output({})  # No request is not a successful save.
            return
        request = validate_request(data, project, native, row)
        digest = hashlib.sha256(data).hexdigest()
        result, emitted_turn = save(conn, request, digest, project, native, row, event)
        if read_request(path) != (data, snapshot):
            raise ValueError('Request replaced before commit')
        conn.commit()  # Every required save, closure and replay key share this commit.
        # Deliver once. The request file stays in the workspace, so every later
        # Stop finds it; once the receipt has been emitted, only a Stop whose
        # message restates this exact intent replays it. An undelivered receipt
        # (crash before emission) is still delivered on the next Stop.
        if emitted_turn == turn or (emitted_turn is not None
                                    and (request['request_id'], digest) not in intents(event)[0]):
            output({})
            return
        output({'decision': 'block', 'reason': 'GC_RECEIPT=' + json.dumps(result, sort_keys=True)})
        # Delivery bookkeeping follows stdout flush. A crash before emission can
        # retry from the durable receipt; a crash here can only repeat a receipt.
        with conn:
            conn.execute('UPDATE hook_bookkeeping_requests SET emitted_turn=? WHERE request_id=?',
                         (turn, request['request_id']))
    finally:
        conn.close()  # Rolls back every pre-commit failure.


def main():
    event = {}
    try:
        raw = sys.stdin.buffer.read(MAX_EVENT + 1)
        if len(raw) > MAX_EVENT:
            raise ValueError('Oversized hook event')
        decoded = decode(raw)
        if not isinstance(decoded, dict):
            raise ValueError('Invalid hook event')
        event = decoded
        run(event, load_host())
        return 0
    except (ValueError, OSError, sqlite3.Error, subprocess.SubprocessError) as exc:
        # Error details never echo request prose, raw SQL, or arbitrary JSON.
        message = f'Bookkeeping failed ({type(exc).__name__}): {exc}. No save receipt; status pending.'
        print(message, file=sys.stderr)
        if event.get('hook_event_name') == 'Stop' and not event.get('stop_hook_active'):
            emit({'decision': 'block', 'reason': message})
            return 0
        # Repeated failed Stop must exit without blocking forever, but not silently.
        emit({'systemMessage': message})
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
