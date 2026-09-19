"""Lean closeout coverage: no network, real local store, stubbed synthesis."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import synthesizer  # noqa: E402
from store.sqlite_store import SqliteKnowledgeStore  # noqa: E402

store = SqliteKnowledgeStore(':memory:')
store.migrate()
store.conn.executescript('''
CREATE TABLE sessions(id INTEGER PRIMARY KEY, project TEXT, started_at TEXT,
 ended_at TEXT, summary TEXT);
CREATE TABLE prompts(id INTEGER PRIMARY KEY, project TEXT, timestamp TEXT,
 prompt TEXT, session_id INTEGER);
CREATE TABLE commits(id INTEGER PRIMARY KEY, hash TEXT, message TEXT,
 timestamp TEXT, session_id INTEGER, prompt_id INTEGER);
INSERT INTO sessions VALUES(1,'song','2026-09-01 06:40:00','2026-09-01 07:10:00','Alpha: decision A');
INSERT INTO sessions VALUES(2,'song','2026-09-01 08:00:00','2026-09-01 08:10:00','Beta: next step B');
''')
# Start and close on different Pacific days; no prompt rows at all.
assert store.get_unsummarized_days('2026-08-31') == [('song', '2026-08-31')]
assert store.get_unsummarized_days('2026-09-01') == [('song', '2026-09-01')]
# DST transition: UTC 07:30 is still the previous Pacific calendar day.
store.conn.execute("INSERT INTO sessions VALUES(3,'dst','2026-03-08 07:30:00','2026-03-08 10:30:00','DST work')")
store.conn.commit()
assert store.get_unsummarized_days('2026-03-07') == [('dst', '2026-03-07')]
assert store.get_unsummarized_days('2026-03-08') == [('dst', '2026-03-08')]
messages = []

def respond(*args, **kwargs):
    messages.append(kwargs['user_msg'])
    return dict(parsed={'summary': f'Alpha decision A; Beta next step B (revision {len(messages)})',
                        'key_decisions': ['Keep both contributions']},
                model='claude-sonnet-4-6', input_tokens=10, output_tokens=10,
                duration_ms=1)

original = synthesizer.call_claude
synthesizer.call_claude = respond
try:
    assert synthesizer.synthesize_daily_summaries(store, None, '2026-09-01') == (1, 0)
    row = dict(store.conn.execute('SELECT * FROM daily_summaries').fetchone())
    assert row['session_count'] == 2 and row['prompt_count'] == 0
    assert 'Alpha: decision A' in messages[-1] and 'Beta: next step B' in messages[-1]
    assert store.get_unsummarized_days('2026-09-01') == []
    # A later close must invalidate a summary written earlier in the same day.
    store.conn.execute("UPDATE daily_summaries SET created_at='2026-09-01 08:05:00'")
    store.conn.commit()
    assert store.get_unsummarized_days('2026-09-01') == [('song', '2026-09-01')]
    assert synthesizer.synthesize_daily_summaries(store, None, '2026-09-01') == (1, 0)
    assert 'Prior daily prose' in messages[-1] and 'Keep both contributions' in messages[-1]
    assert store.conn.execute('SELECT count(*) FROM daily_summaries_superseded').fetchone()[0] == 1
    # A concurrent full handoff must not be overwritten by an obsolete API reply.
    store.conn.execute("UPDATE daily_summaries SET created_at='2026-09-01 08:05:00'")
    store.conn.commit()

    def race(*args, **kwargs):
        result = respond(*args, **kwargs)
        store.upsert_daily_summary(project='song', date='2026-09-01',
            summary='New peer finding', key_decisions=[], prompt_count=0,
            session_count=2, commit_count=0, model='codex')
        return result

    synthesizer.call_claude = race
    assert synthesizer.synthesize_daily_summaries(store, None, '2026-09-01') == (1, 1)
    assert store.conn.execute('SELECT summary FROM daily_summaries').fetchone()[0] == 'New peer finding'
    # An already-built completed week's rollup becomes due when its daily changes.
    store.upsert_weekly_rollup(project='song', week_start='2026-08-31',
        narrative='old week', highlights=[], daily_summary_ids=[],
        prompt_count=0, session_count=2, commit_count=0, model='test')
    store.conn.execute("UPDATE weekly_rollups SET created_at='2026-09-01 08:00:00'")
    store.conn.commit()
    assert ('song', '2026-08-31') in store.get_weeks_without_rollups()
finally:
    synthesizer.call_claude = original
    store.close()
print('PASS: prompt-free sessions, Pacific overnight coverage, stale-day refresh, preservation, race rejection, weekly refresh')
