# Review Jobs → Processed Tables (Turso) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `send-review.py` and `generate-report.py` compose from processed
tables read from Turso, so their output covers every machine's work regardless
of which machine runs them.

**Architecture:** Both scripts currently read `get_raw_sessions()` (and the
report also `get_period_stats()`) from the machine-local raw tier — which is
why the mini's email said "no new work" on days full of laptop work
(diagnosed with data 2026-08-13; see CLAUDE.md's review-email entry). The
fix: reads go through `get_store("turso")` — daily summaries + weekly
rollups, which both machines already push (verified complete in Turso for
Aug 10–12) — while the review-snapshot **writes stay local** (`get_store()`
default), preserving the existing write topology and its sync leg. Turso's
store *raises* `NotImplementedError` on all raw-tier methods, so every raw
call must be removed, and a source grep pins them out permanently.

**Tech Stack:** Python 3 stdlib + existing repo modules only (`store/`,
`claude_api.py`, `web/day_helper.py`). No new dependencies.

**Spec:** Inline — the Context section below plus CLAUDE.md's "nightly review
email" and "what runs where" Open entries (commit `c77d832` state). No
separate spec doc exists.

## Context (read before executing)

- Three-tier data model: raw (`prompts`/`sessions`/`commits`) is
  machine-local SQLite and **never syncs** — Turso physically has no such
  tables (`store/turso_store.py:700-709` raises on them). Processed tables
  (`daily_summaries`, `weekly_rollups`, `review_snapshots`) exist in both
  local SQLite and Turso; each machine pushes its own via `sync_to_turso.py`.
- `get_store()` (`store/__init__.py`) picks the backend from
  `GROUND_CONTROL_STORE` (default `sqlite`). The nightly plists set only
  `PATH` — deliberately: choosing the backend **in-script** means the staged
  plists at `~/mini-staging/prompt-lab/` restore onto the rebuilt mini
  completely unchanged.
- The mini is wiped (2026-08-13); `com.promptlab.review` and
  `com.promptlab.report` are gated on this refactor in the mini-decommission
  repo's WIPE-CHECKLIST.md section D2 — message that agent when this merges.
- Both scripts already `sys.path.insert` (or must) the `web/` dir for
  `day_helper`.
- `get_daily_summaries(since=…, until=…)`: both operators are **inclusive**
  (`date >= since AND date <= until` — `store/sqlite_store.py:313-318`,
  `store/turso_store.py:323+`).

## Global Constraints

- Tests are standalone runners, NOT pytest: run `.venv/bin/python scripts/test_<name>.py`; `python -m pytest` fails at collection.
- ruff `0.15.22` must pass: `.venv/bin/ruff check <changed files>` (CI pins this version; an F401 turned CI red on 2026-08-12).
- Timestamps UTC at rest, calendar days Pacific on display: date windows come from `web/day_helper.py` (`lab_today`, `lab_days_ago`), never `datetime.now().strftime(...)` arithmetic.
- No new dependencies; no plist changes; no changes under `workflow/` (so no installed-copy sweep needed).
- `sqlite_store`/`turso_store`/`base.py` keep `get_raw_sessions` and `get_period_stats` unchanged — this plan removes their *consumers*, not the store surface (three-home churn out of scope; the overlap-selection tests in `scripts/test_send_review.py` continue to pin store behavior).
- Non-goal, do not drift into it: distinguishing composition-vs-delivery in `review_snapshots` (known open item, deliberately out of scope).
- Commit after each task; commit messages in this repo are short narrative sentences (see `git log`), each ending with the `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` trailer.

---

### Task 1: `get_store()` accepts an explicit backend

**Files:**
- Modify: `store/__init__.py`
- Test: `scripts/test_send_review.py` (append one test)

**Interfaces:**
- Produces: `get_store(backend: str | None = None) -> KnowledgeStore` — explicit arg wins over `GROUND_CONTROL_STORE`; `None` preserves today's env-then-sqlite behavior exactly. Tasks 2 and 3 call `get_store("turso")` for reads and bare `get_store()` for local writes.

- [ ] **Step 1: Write the failing test**

Append to `scripts/test_send_review.py` (before the `if __name__ == "__main__":` block; the `@test` decorator and imports already exist in the file):

```python
@test("get_store honors an explicit backend argument over the env default")
def _():
    import os

    from store import get_store

    # turso: constructor only reads env, no connection made — safe to build
    had_url = os.environ.get("TURSO_DATABASE_URL")
    had_tok = os.environ.get("TURSO_AUTH_TOKEN")
    os.environ["TURSO_DATABASE_URL"] = "libsql://test.invalid"
    os.environ["TURSO_AUTH_TOKEN"] = "test-token"
    try:
        s = get_store("turso")
        assert type(s).__name__ == "TursoKnowledgeStore", type(s).__name__
    finally:
        if had_url is None:
            del os.environ["TURSO_DATABASE_URL"]
        else:
            os.environ["TURSO_DATABASE_URL"] = had_url
        if had_tok is None:
            del os.environ["TURSO_AUTH_TOKEN"]
        else:
            os.environ["TURSO_AUTH_TOKEN"] = had_tok

    # unknown backend still raises, same as the env path
    try:
        get_store("nope")
        raise AssertionError("unknown backend must raise ValueError")
    except ValueError:
        pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python scripts/test_send_review.py`
Expected: FAIL on the new test — `TypeError: get_store() takes 0 positional arguments but 1 was given`

- [ ] **Step 3: Write minimal implementation**

In `store/__init__.py`, change the signature and first line of `get_store` (rest of the function body is unchanged):

```python
def get_store(backend: str | None = None) -> KnowledgeStore:
    """Return a KnowledgeStore instance.

    `backend` overrides the GROUND_CONTROL_STORE env var; None falls back to
    the env var, then to 'sqlite'. Supported: 'sqlite', 'turso'.
    """
    backend = backend or os.environ.get("GROUND_CONTROL_STORE", "sqlite")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python scripts/test_send_review.py`
Expected: all PASS (6/6)

- [ ] **Step 5: Ruff, then commit**

Run: `.venv/bin/ruff check store/__init__.py scripts/test_send_review.py`

```bash
git add store/__init__.py scripts/test_send_review.py
git commit -m "get_store learns to take direction

An explicit backend argument, overriding the env var: the two reader
scripts are about to declare in code that they need the merged store,
instead of hoping every machine's plist remembers to say so.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: `send-review.py` composes from processed tables only

**Files:**
- Modify: `send-review.py`
- Test: `scripts/test_send_review.py`

**Interfaces:**
- Consumes: `get_store("turso")` from Task 1; `day_helper.lab_days_ago` (already imported).
- Produces: `review_windows() -> {"review_day": str, "week_since": str}` (the UTC-bounds keys are removed — nothing consumes them once raw-session overlap selection is gone); `build_prompt(daily_summaries_1d, weekly_summaries, weekly_rollups, is_weekly) -> (system, user_msg)`.

- [ ] **Step 1: Update the window test and greps to the new contract (failing first)**

In `scripts/test_send_review.py`, replace the body of the test named `review window: 'today' is yesterday's completed lab-day, week reaches 7 back` with:

```python
    mod = _load_send_review()
    w = mod.review_windows()
    yesterday = (lab_today() - timedelta(days=1)).isoformat()
    week_since = (lab_today() - timedelta(days=7)).isoformat()
    assert w["review_day"] == yesterday, f"review_day={w['review_day']}, want {yesterday}"
    assert w["week_since"] == week_since, f"week_since={w['week_since']}, want {week_since}"
    assert "day_start_utc" not in w, "UTC bounds should be gone with the raw-session read"
```

Replace the body of the test named `send-review no longer queries daily summaries with the run date` with:

```python
    src = (ROOT / "send-review.py").read_text()
    assert "get_daily_summaries(since=today_str)" not in src, \
        "the 2:30am bug is back: daily summaries fetched with the run date"
    assert "get_raw_sessions" not in src, \
        "send-review must not read the raw tier: it is machine-local, and " \
        "reading it is why the email said 'no new work' on busy days"
    assert 'get_store("turso")' in src, \
        "reads must go through the merged (Turso) store"
    assert 'until=w["review_day"]' in src, \
        "the Today window must be closed on both ends (until is inclusive)"
```

Add one new behavior test:

```python
@test("build_prompt composes from summaries and rollups, with counts inline")
def _():
    mod = _load_send_review()
    daily = [{"date": "2026-08-12", "project": "raconte", "summary": "Shipped the exporter.",
              "prompt_count": 24, "session_count": 3}]
    weekly = daily + [{"date": "2026-08-10", "project": "musicforge",
                       "summary": "Fixed the mixer.", "prompt_count": 10, "session_count": 1}]
    rollups = [{"project": "raconte", "week_start": "2026-08-03", "narrative": "A big week."}]
    system, user_msg = mod.build_prompt(daily, weekly, rollups, is_weekly=False)
    assert "raconte" in user_msg and "musicforge" in user_msg
    assert "24 prompts" in user_msg, "per-day counts must reach the model"
    assert "A big week." in user_msg
    assert "Session summaries" not in user_msg, "raw-session sections must be gone"
```

- [ ] **Step 2: Run tests to verify the new/changed ones fail**

Run: `.venv/bin/python scripts/test_send_review.py`
Expected: FAIL on the three touched tests (old keys present, greps unmet, old `build_prompt` signature takes 6 args)

- [ ] **Step 3: Rewrite the data plumbing in `send-review.py`**

Replace `review_windows()` (keep the docstring's first paragraph, drop the overlap sentence):

```python
def review_windows():
    """The email's two windows, on the lab's clock.

    "Today" is *yesterday's completed lab-day*, never the run date: the job
    fires at 2:30am, when the run date structurally has no summaries yet —
    asking for "today" is how the email said "no new work" on days with 25
    prompts across 4 projects.
    """
    return {
        "review_day": lab_days_ago(1),
        "week_since": lab_days_ago(7),
    }
```

Update the `day_helper` import to drop the now-unused name:

```python
from day_helper import lab_days_ago  # noqa: E402
```

Replace `build_prompt` — signature, one formatter, and the user message
(`format_rollups`, the rollup section, the system prompt, and the return are
unchanged from the current file):

```python
def build_prompt(daily_summaries_1d, weekly_summaries, weekly_rollups, is_weekly):
    def format_summaries(summaries):
        lines = []
        for ds in summaries:
            counts = f" ({ds.get('prompt_count') or 0} prompts, {ds.get('session_count') or 0} sessions)"
            lines.append(f"[{ds['date']}] {ds['project']}{counts}: {ds['summary']}")
        return chr(10).join(lines) or "(none)"
```

and the user message becomes:

```python
    user_msg = f"""Date: {datetime.now().strftime('%Y-%m-%d')}

== Last 24 hours ==

Daily summaries ({len(daily_summaries_1d)}):
{format_summaries(daily_summaries_1d)}

== This week (7 days) ==

Daily summaries ({len(weekly_summaries)}):
{format_summaries(weekly_summaries)}{rollup_section}"""
```

In `main()`, replace the store-read block (lines currently reading
`store = get_store()` through `store.close()`) with:

```python
    # Reads come from the merged store: processed tables in Turso carry every
    # machine's summaries, so the email covers all work no matter which
    # machine sends it. The raw tier is machine-local by invariant and must
    # never be read here — that's how the email said "no new work" on busy
    # days. Turso being unreachable raises and kills the run: no email, a
    # stale artifact, and the #45 heartbeat catches it — never a confidently
    # empty email.
    store = get_store("turso")
    daily_summaries_1d = store.get_daily_summaries(
        since=w["review_day"], until=w["review_day"])
    weekly_summaries = store.get_daily_summaries(since=w["week_since"])
    weekly_rollups = store.get_weekly_rollups(since=w["week_since"])
    store.close()

    if not weekly_summaries and not weekly_rollups:
        print("No summaries or rollups found for the period.")
        return
```

and the compose call becomes:

```python
    system, user_msg = build_prompt(daily_summaries_1d, weekly_summaries,
                                     weekly_rollups, is_weekly)
```

The snapshot-persist block later in `main()` stays exactly as is — bare
`get_store()` — so the snapshot writes locally and reaches Turso through the
existing sync leg, unchanged.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python scripts/test_send_review.py`
Expected: all PASS

- [ ] **Step 5: Live dry run against real Turso**

Run: `.venv/bin/python send-review.py --dry-run`
(Costs one Sonnet call, ~$0.02; prints the email text, sends nothing, writes
no snapshot.) Expected: the Today section names yesterday's actual work from
BOTH machines' summaries — compare against the dashboard's day page. This is
the proof the mini's "no new work" email could not have produced.

- [ ] **Step 6: Ruff, then commit**

Run: `.venv/bin/ruff check send-review.py scripts/test_send_review.py`

```bash
git add send-review.py scripts/test_send_review.py
git commit -m "The review email reads the merged store

Daily summaries and rollups from Turso, raw sessions from nowhere:
the email now sees every machine's day, and the machine that sends it
stops mattering. Snapshot writes stay local, synced as before.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: `generate-report.py` composes from processed tables only

**Files:**
- Modify: `generate-report.py`
- Create: `scripts/test_generate_report.py`

**Interfaces:**
- Consumes: `get_store("turso")` from Task 1; `day_helper.lab_days_ago`.
- Produces: module function `derive_stats(daily_summaries: list[dict]) -> dict` returning `{"total_prompts": int, "total_sessions": int, "total_projects": int, "projects": [{"name": str, "prompts": int, "active_days": int}]}` (same shape `format_stats` already consumes, projects sorted by prompts descending); `build_prompt(daily_summaries, weekly_rollups, stats, days)` (the `sessions` parameter is removed).

- [ ] **Step 1: Write the failing tests**

Create `scripts/test_generate_report.py`:

```python
"""Regression tests for the bi-monthly report's data sourcing.

The report read get_raw_sessions()/get_period_stats() from the machine-local
raw tier, so a report generated on one machine silently omitted every other
machine's work (same defect as the review email, found 2026-08-13 minutes
before its Aug 15 run would have shipped a two-week report blind to the
laptop). Pinned here: reads come from processed tables via the merged store,
stats derive from daily summaries, and windows are lab-days.

Run: .venv/bin/python scripts/test_generate_report.py
No pytest. Prints PASS/FAIL per test, exits 1 if any fail.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

_results: list[tuple[str, bool, str]] = []


def test(name: str):
    def deco(fn):
        try:
            fn()
            _results.append((name, True, ""))
        except AssertionError as e:
            _results.append((name, False, str(e) or "assertion failed"))
        except Exception as e:  # noqa: BLE001
            _results.append((name, False, f"{type(e).__name__}: {e}"))
        return fn

    return deco


def _load_generate_report():
    spec = importlib.util.spec_from_file_location(
        "generate_report", ROOT / "generate-report.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@test("derive_stats aggregates daily summaries into the period-stats shape")
def _():
    mod = _load_generate_report()
    rows = [
        {"project": "raconte", "date": "2026-08-11", "prompt_count": 20,
         "session_count": 2, "commit_count": 1},
        {"project": "raconte", "date": "2026-08-12", "prompt_count": 4,
         "session_count": 1, "commit_count": 0},
        {"project": "musicforge", "date": "2026-08-12", "prompt_count": 27,
         "session_count": 3, "commit_count": 2},
        # NULL-ish counts must not crash the sums
        {"project": "byside", "date": "2026-08-12", "prompt_count": None,
         "session_count": None, "commit_count": None},
    ]
    st = mod.derive_stats(rows)
    assert st["total_prompts"] == 51, st
    assert st["total_sessions"] == 6, st
    assert st["total_projects"] == 3, st
    by_name = {p["name"]: p for p in st["projects"]}
    assert by_name["raconte"] == {"name": "raconte", "prompts": 24, "active_days": 2}
    assert by_name["musicforge"]["active_days"] == 1
    # ordered by prompts descending, so the report leads with the big work
    assert st["projects"][0]["name"] == "musicforge", st["projects"]


@test("derive_stats of nothing is zeros, not a crash")
def _():
    mod = _load_generate_report()
    st = mod.derive_stats([])
    assert st == {"total_prompts": 0, "total_sessions": 0,
                  "total_projects": 0, "projects": []}, st


@test("report reads the merged store and never the raw tier")
def _():
    src = (ROOT / "generate-report.py").read_text()
    assert "get_raw_sessions" not in src, \
        "the report must not read machine-local raw sessions"
    assert "get_period_stats" not in src, \
        "period stats must derive from daily summaries, not raw prompts"
    assert 'get_store("turso")' in src, \
        "reads must go through the merged (Turso) store"
    assert "lab_days_ago" in src, \
        "the window must be a lab-day, not naive datetime arithmetic"


@test("neither reader script touches the raw tier (cross-file pin)")
def _():
    for fname in ("send-review.py", "generate-report.py"):
        src = (ROOT / fname).read_text()
        assert "get_raw_sessions" not in src, f"{fname} reads raw sessions"


if __name__ == "__main__":
    failed = 0
    for name, ok, msg in _results:
        print(f"{'PASS' if ok else 'FAIL'}: {name}" + (f" — {msg}" if msg else ""))
        failed += 0 if ok else 1
    print(f"\n{len(_results) - failed}/{len(_results)} passed")
    sys.exit(1 if failed else 0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python scripts/test_generate_report.py`
Expected: FAIL — `derive_stats` doesn't exist; the source greps find `get_raw_sessions`/`get_period_stats`

- [ ] **Step 3: Rewrite the data plumbing in `generate-report.py`**

Add the `web/` path insert and import after the existing imports (mirroring `send-review.py`):

```python
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "web"))
from day_helper import lab_days_ago  # noqa: E402
```

Add the stats derivation as a module-level function:

```python
def derive_stats(daily_summaries):
    """Period stats from daily summaries — the processed-tier equivalent of
    the old get_period_stats(), which counted machine-local raw prompts and
    therefore saw only one machine's work."""
    per_project: dict[str, dict] = {}
    for ds in daily_summaries:
        p = per_project.setdefault(ds["project"], {"prompts": 0, "days": set()})
        p["prompts"] += ds.get("prompt_count") or 0
        p["days"].add(ds["date"])
    projects = sorted(
        ({"name": name, "prompts": v["prompts"], "active_days": len(v["days"])}
         for name, v in per_project.items()),
        key=lambda p: p["prompts"], reverse=True)
    return {
        "total_prompts": sum(p["prompts"] for p in projects),
        "total_sessions": sum(ds.get("session_count") or 0 for ds in daily_summaries),
        "total_projects": len(projects),
        "projects": projects,
    }
```

In `main()`, replace the store-read block with:

```python
    # Merged store: processed tables in Turso carry every machine's
    # summaries. The raw tier is machine-local and must never be read here —
    # a report composed from it silently omits every other machine's work
    # while looking authoritative. Turso unreachable raises and kills the
    # run; the #45 heartbeat catches the stale artifact.
    store = get_store("turso")
    since_date = lab_days_ago(days)
    daily_summaries = store.get_daily_summaries(since=since_date)
    weekly_rollups = store.get_weekly_rollups(since=since_date)
    store.close()

    if not daily_summaries and not weekly_rollups:
        print("No summaries or rollups found for the period.")
        return

    stats = derive_stats(daily_summaries)
```

Update `build_prompt`: remove the `sessions` parameter and the
`format_sessions` helper, delete the `== Session summaries (…) ==` block from
`user_msg`, and change the call site to
`build_prompt(daily_summaries, weekly_rollups, stats, days)`. In the system
prompt, change the line
`- If multiple sessions exist for a project, walk through them chronologically`
to
`- If multiple days exist for a project, walk through them chronologically`.
Update the dry-run block to drop the sessions line:

```python
    if dry_run:
        print(f"Would generate {days}-day report")
        print(f"  Daily summaries: {len(daily_summaries)}")
        print(f"  Weekly rollups: {len(weekly_rollups)}")
        print(f"  Stats: {stats['total_prompts']} prompts, {stats['total_sessions']} sessions")
        print(f"\nPrompt length: {len(user_msg)} chars")
        return
```

Delete the now-unused `timedelta` import if nothing else in the file uses it
(check before deleting — ruff will flag it either way).

The report-file write and snapshot-persist blocks stay exactly as is (bare
`get_store()`, local).

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python scripts/test_generate_report.py`
Expected: all PASS (4/4)

- [ ] **Step 5: Live dry run against real Turso**

Run: `.venv/bin/python generate-report.py --dry-run 14`
(No API call in dry-run — it stops before the Claude call.) Expected: summary
and rollup counts consistent with the dashboard's last two weeks, prompt
total in the hundreds — not a near-zero count, which would mean it's somehow
still reading a machine-local view.

- [ ] **Step 6: Ruff, then commit**

Run: `.venv/bin/ruff check generate-report.py scripts/test_generate_report.py`

```bash
git add generate-report.py scripts/test_generate_report.py
git commit -m "The bi-monthly report reads the merged store

Same defect as the review email, found two days before its Aug 15 run
would have shipped a two-week report blind to the laptop: raw-tier
reads replaced with Turso summaries and rollups, stats derived from
what both machines actually pushed.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Full sweep, docs, and the gate release

**Files:**
- Modify: `CLAUDE.md`
- (No code changes — verification and communication)

**Interfaces:**
- Consumes: everything above, merged and pushed.

- [ ] **Step 1: Full test sweep**

Run: `for f in scripts/test_*.py; do .venv/bin/python "$f" || echo "FAIL: $f"; done`
Expected: zero FAIL lines (~247 tests across 8 files after this plan).

- [ ] **Step 2: Ruff over everything changed**

Run: `.venv/bin/ruff check store/__init__.py send-review.py generate-report.py scripts/test_send_review.py scripts/test_generate_report.py`
Expected: `All checks passed!`

- [ ] **Step 3: Update CLAUDE.md**

In the review-email Open entry: mark the Turso refactor DONE with the date,
and note the report was covered by the same change. In the what-runs-where
entry: note the gate condition is met. In the Architecture section, update
the `send-review.py` and `generate-report.py` bullets to say "reads processed
tables from Turso (`get_store(\"turso\")`); snapshot writes stay local and
sync as before." Trim rather than append — the diagnosis prose can compress
to one line now that the fix is in.

- [ ] **Step 4: Commit and push**

```bash
git add CLAUDE.md
git commit -m "The readers stop caring where they run

Refactor recorded: both nightly composers read the merged store now,
so the reconstitution gate is met.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git push
```

Then confirm CI goes green: `gh run list --branch main --limit 1`

- [ ] **Step 5: Release the gate**

Message the mini-decommission agent (SendMessage, name `mini-decommission`):
the refactor is merged at `<commit sha>`; `com.promptlab.review` and
`com.promptlab.report` may be bootstrapped; the staged plists need **no
edits** (backend selection is in-script); the mini's `.env.local` already
carries `TURSO_DATABASE_URL`/`TURSO_AUTH_TOKEN` (its sync leg used them).
Remind them verification is by artifact after the first overnight (checklist
D2 step 7): email in inbox naming the previous lab-day's work from both
machines, new `review_snapshots` row, heartbeats green in the 8am email.

---

### Task 5: Same-day clobber fix — per-machine parts, merged deterministically

*Independent of the Task 4 gate release — the reconstitution does not wait on
this task, but landing it in the same dark window means the mini returns to a
federation with no known lying edge.*

**Why:** `daily_summaries` is keyed `(project, date)` and synced with a blind
upsert, so two machines working the same project the same day clobber each
other in Turso — last sync wins (CLAUDE.md, DB-ownership entry). The fix
keeps local schemas and every reader untouched: each machine pushes its rows
into a new Turso-only parts table keyed `(project, date, machine)` (a pure,
idempotent upsert), and the merged `daily_summaries` row is deterministically
rebuilt from all parts. Readers keep reading `daily_summaries` exactly as
today; on genuine collision days the merged summary carries `[machine]`
prefixes and summed counts. `weekly_rollups` has the same clobber shape and
is **deliberately deferred** — post-reconstitution the mini generates rollups
only from its own (near-idle) summaries, so collisions there stay rare;
adopt this same pattern if it ever bites.

**Files:**
- Modify: `store/turso_store.py` (DDL in `migrate()`, two new methods)
- Modify: `sync_to_turso.py` (machine label, merge function, dedicated daily-summaries leg)
- Create: `scripts/test_sync_clobber.py`

**Interfaces:**
- Produces: `machine_label() -> str` (env `GROUND_CONTROL_MACHINE`, else short
  hostname lowercased); `merge_summary_parts(parts: list[dict]) -> dict`
  (pure; input any order → identical output; keys `project, date, summary,
  key_decisions (list), prompt_count, session_count, commit_count, model`);
  `TursoKnowledgeStore.upsert_daily_summary_part(...)` and
  `.get_daily_summary_parts(since: str, until: str) -> list[dict]`.
- Consumes: `remote._execute_many` / `_rows_to_dicts` idioms
  (`store/turso_store.py:82-101`), existing `upsert_daily_summary`.

- [ ] **Step 1: Write the failing tests**

Create `scripts/test_sync_clobber.py`:

```python
"""Tests for the same-day clobber fix (per-machine daily-summary parts).

daily_summaries is keyed (project, date); before this fix, two machines
syncing the same project-day clobbered each other in Turso — last sync wins.
Now each machine upserts into daily_summaries_machine (keyed +machine) and
the merged row is rebuilt deterministically from all parts.

Run: .venv/bin/python scripts/test_sync_clobber.py
No pytest. Prints PASS/FAIL per test, exits 1 if any fail.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import sync_to_turso  # noqa: E402

_results: list[tuple[str, bool, str]] = []


def test(name: str):
    def deco(fn):
        try:
            fn()
            _results.append((name, True, ""))
        except AssertionError as e:
            _results.append((name, False, str(e) or "assertion failed"))
        except Exception as e:  # noqa: BLE001
            _results.append((name, False, f"{type(e).__name__}: {e}"))
        return fn

    return deco


@test("single-machine part passes through unmerged (the common case)")
def _():
    part = {"project": "raconte", "date": "2026-08-12", "machine": "laptop",
            "summary": "Shipped the exporter.",
            "key_decisions": '["ship it"]',
            "prompt_count": 24, "session_count": 3, "commit_count": 2,
            "model": "claude-code"}
    m = sync_to_turso.merge_summary_parts([part])
    assert m["summary"] == "Shipped the exporter.", m
    assert "[laptop]" not in m["summary"], "no machine prefix when only one machine"
    assert m["key_decisions"] == ["ship it"], "JSON-string key_decisions must decode"
    assert m["prompt_count"] == 24 and m["model"] == "claude-code", m
    assert "machine" not in m, "merged rows carry no machine column"


@test("two machines merge deterministically: prefixed prose, summed counts")
def _():
    a = {"project": "prompt-lab", "date": "2026-08-12", "machine": "mini",
         "summary": "Nightly jobs ran.", "key_decisions": ["keep jobs"],
         "prompt_count": 3, "session_count": 1, "commit_count": 0,
         "model": "claude-code"}
    b = {"project": "prompt-lab", "date": "2026-08-12", "machine": "laptop",
         "summary": "Fixed the review email.", "key_decisions": ["keep jobs", "fix window"],
         "prompt_count": "12", "session_count": "2", "commit_count": "5",
         "model": "claude-code"}  # string counts: Turso returns aggregates as strings
    m1 = sync_to_turso.merge_summary_parts([a, b])
    m2 = sync_to_turso.merge_summary_parts([b, a])
    assert m1 == m2, "merge must be order-independent"
    assert m1["summary"] == "[laptop] Fixed the review email.\n[mini] Nightly jobs ran.", m1["summary"]
    assert m1["prompt_count"] == 15 and m1["session_count"] == 3 and m1["commit_count"] == 5, m1
    assert m1["key_decisions"] == ["keep jobs", "fix window"], "dedup preserves first-seen order"
    assert m1["model"] == "merged", m1


@test("machine_label: env override wins, fallback is short lowercase hostname")
def _():
    import os
    import socket
    had = os.environ.get("GROUND_CONTROL_MACHINE")
    os.environ["GROUND_CONTROL_MACHINE"] = "testbox"
    try:
        assert sync_to_turso.machine_label() == "testbox"
    finally:
        if had is None:
            del os.environ["GROUND_CONTROL_MACHINE"]
        else:
            os.environ["GROUND_CONTROL_MACHINE"] = had
    if os.environ.get("GROUND_CONTROL_MACHINE") is None:
        expect = socket.gethostname().split(".")[0].lower()
        assert sync_to_turso.machine_label() == expect


@test("the daily leg goes through parts, not a blind whole-row upsert")
def _():
    src = (ROOT / "sync_to_turso.py").read_text()
    assert "daily_summaries_machine" in src, "parts table never written"
    assert "sync_daily_summaries(" in src, "dedicated daily leg missing"
    assert "merge_summary_parts" in src, "merged rebuild missing"


if __name__ == "__main__":
    failed = 0
    for name, ok, msg in _results:
        print(f"{'PASS' if ok else 'FAIL'}: {name}" + (f" — {msg}" if msg else ""))
        failed += 0 if ok else 1
    print(f"\n{len(_results) - failed}/{len(_results)} passed")
    sys.exit(1 if failed else 0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python scripts/test_sync_clobber.py`
Expected: FAIL — `sync_to_turso` has no `merge_summary_parts` / `machine_label`

- [ ] **Step 3: Add the parts table and accessors to `store/turso_store.py`**

In `migrate()`, append to the DDL `self._pipeline([...])` list, directly
after the existing `daily_summaries` entry (mirror its column types exactly
as they appear there):

```python
            {"sql": """
                CREATE TABLE IF NOT EXISTS daily_summaries_machine (
                    project TEXT NOT NULL,
                    date TEXT NOT NULL,
                    machine TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    key_decisions TEXT,
                    prompt_count INTEGER DEFAULT 0,
                    session_count INTEGER DEFAULT 0,
                    commit_count INTEGER DEFAULT 0,
                    model TEXT,
                    synced_at TEXT DEFAULT (datetime('now')),
                    PRIMARY KEY (project, date, machine)
                )
            """},
```

Add two methods next to `get_daily_summaries` (these are Turso-only helpers,
deliberately NOT on the ABC — the local store is single-machine by
construction and has no parts concept):

```python
    def upsert_daily_summary_part(self, *, project, date, machine, summary,
                                   key_decisions, prompt_count, session_count,
                                   commit_count, model):
        """One machine's contribution to a project-day. Pure idempotent
        upsert on (project, date, machine) — re-syncing is a no-op."""
        self._execute(
            "INSERT OR REPLACE INTO daily_summaries_machine "
            "(project, date, machine, summary, key_decisions, prompt_count, "
            " session_count, commit_count, model) VALUES (?,?,?,?,?,?,?,?,?)",
            [project, date, machine, summary,
             json.dumps(key_decisions or []), prompt_count, session_count,
             commit_count, model])

    def get_daily_summary_parts(self, *, since, until):
        result = self._execute(
            "SELECT project, date, machine, summary, key_decisions, "
            "prompt_count, session_count, commit_count, model "
            "FROM daily_summaries_machine WHERE date >= ? AND date <= ?",
            [since, until])
        return self._rows_to_dicts(result)
```

- [ ] **Step 4: Add label, merge, and the dedicated leg to `sync_to_turso.py`**

Add near the top (after the imports; add `import socket`):

```python
def machine_label():
    """Stable label naming this machine in merged summaries.

    GROUND_CONTROL_MACHINE (set it in each machine's .env.local: `laptop`,
    `mini`) wins; the fallback is the short hostname lowercased. The override
    exists because hostnames change — the mini was renamed at its 2026-08
    re-purposing — and a renamed machine must not fork its own history into
    two part rows.
    """
    return os.environ.get("GROUND_CONTROL_MACHINE") or \
        socket.gethostname().split(".")[0].lower()


def merge_summary_parts(parts):
    """Deterministically merge per-machine parts for one (project, date).

    Pure function: the same set of parts in any order produces an identical
    row. Counts are int()-coerced — Turso returns numbers as strings.
    """
    def kd(p):
        v = p.get("key_decisions") or []
        return json.loads(v) if isinstance(v, str) else v

    parts = sorted(parts, key=lambda p: p["machine"])
    if len(parts) == 1:
        p = parts[0]
        return {
            "project": p["project"], "date": p["date"],
            "summary": p["summary"], "key_decisions": kd(p),
            "prompt_count": int(p.get("prompt_count") or 0),
            "session_count": int(p.get("session_count") or 0),
            "commit_count": int(p.get("commit_count") or 0),
            "model": p.get("model") or "unknown",
        }
    decisions = []
    for p in parts:
        for d in kd(p):
            if d not in decisions:
                decisions.append(d)
    return {
        "project": parts[0]["project"], "date": parts[0]["date"],
        "summary": "\n".join(f"[{p['machine']}] {p['summary']}" for p in parts),
        "key_decisions": decisions,
        "prompt_count": sum(int(p.get("prompt_count") or 0) for p in parts),
        "session_count": sum(int(p.get("session_count") or 0) for p in parts),
        "commit_count": sum(int(p.get("commit_count") or 0) for p in parts),
        "model": "merged",
    }


def sync_daily_summaries(local, remote, since, dry_run):
    """Push this machine's summaries as parts, then rebuild merged rows.

    Replaces the blind whole-row upsert that let two machines clobber each
    other on shared project-days. Parts go up first (idempotent on
    project+date+machine), then every (project, date) pair with parts in the
    synced window is rebuilt from ALL machines' parts — rebuilding a pair is
    always safe because the merge is a pure function of its parts.
    Historical days with no parts yet keep their existing merged rows; a full
    sync (no --days) from each machine backfills parts for all history.
    """
    rows = local.get_daily_summaries(since=since)
    if not rows:
        print("  daily_summaries: 0 rows (skip)")
        return 0
    if dry_run:
        print(f"  daily_summaries: {len(rows)} rows (dry run)")
        return len(rows)

    machine = machine_label()
    buffer = []
    orig_execute = remote._execute
    remote._execute = lambda sql, args=None: buffer.append((sql, args or []))
    try:
        for row in rows:
            kd = row["key_decisions"]
            remote.upsert_daily_summary_part(
                project=row["project"], date=row["date"], machine=machine,
                summary=row["summary"],
                key_decisions=json.loads(kd) if isinstance(kd, str) else (kd or []),
                prompt_count=row.get("prompt_count", 0) or 0,
                session_count=row.get("session_count", 0) or 0,
                commit_count=row.get("commit_count", 0) or 0,
                model=row.get("model", "unknown"))
    finally:
        remote._execute = orig_execute
    for i in range(0, len(buffer), 100):
        remote._execute_many(buffer[i:i + 100])
    print(f"  daily_summaries: {len(rows)} parts synced as '{machine}'")

    dates = sorted({r["date"] for r in rows})
    parts = remote.get_daily_summary_parts(since=dates[0], until=dates[-1])
    grouped = {}
    for p in parts:
        grouped.setdefault((p["project"], p["date"]), []).append(p)

    buffer = []
    remote._execute = lambda sql, args=None: buffer.append((sql, args or []))
    try:
        for pair_parts in grouped.values():
            remote.upsert_daily_summary(**merge_summary_parts(pair_parts))
    finally:
        remote._execute = orig_execute
    for i in range(0, len(buffer), 100):
        remote._execute_many(buffer[i:i + 100])
    print(f"  daily_summaries: {len(grouped)} merged rows rebuilt")
    return len(rows)
```

In `main()`, replace the existing daily-summaries `sync_table(...)` call
(the first sync leg) with:

```python
    # Daily summaries — per-machine parts + deterministic merge, NOT the
    # generic blind upsert: two machines on one project-day must both survive.
    total += sync_daily_summaries(local, remote, since, dry_run)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python scripts/test_sync_clobber.py`
Expected: all PASS (4/4)

- [ ] **Step 6: Live verification**

Add `GROUND_CONTROL_MACHINE=laptop` to the laptop's `.env.local` (append the
single line; never regenerate the file via `op inject` — see CLAUDE.md
traps). Then run a windowed sync and check the shape:

Run: `.venv/bin/python sync_to_turso.py --days 3`
Expected output includes `daily_summaries: N parts synced as 'laptop'` and
`N merged rows rebuilt`. Then confirm no visible regression: the dashboard's
recent days (https://prompt-labs.org) show the same counts as before the
sync, and `scripts/check_public_allowlist.py` still exits 0 (it runs
automatically at the end of the sync).

A full-history backfill (`.venv/bin/python sync_to_turso.py`, no `--days`)
runs past 120s — run it in the background or raise the timeout. Do it once
from the laptop; the mini does the same once at reconstitution (with
`GROUND_CONTROL_MACHINE=mini` in its `.env.local` — add that to the D2
message in Task 4's gate release if this task lands first).

- [ ] **Step 7: Ruff, docs, commit**

Run: `.venv/bin/ruff check store/turso_store.py sync_to_turso.py scripts/test_sync_clobber.py`

Update CLAUDE.md's DB-ownership entry: the `daily_summaries` clobber bullet
becomes "FIXED <date>: per-machine parts table + deterministic merge at sync
time; `weekly_rollups` still has the shape, deferred until it bites; machine
labels come from `GROUND_CONTROL_MACHINE` in each `.env.local`."

```bash
git add store/turso_store.py sync_to_turso.py scripts/test_sync_clobber.py CLAUDE.md
git commit -m "Two machines stop overwriting each other's days

daily_summaries syncs as per-machine parts now, merged
deterministically in Turso: prefixed prose, summed counts, and a
re-sync that is a no-op instead of a coin flip over whose work
survives. Local schemas and every reader untouched.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git push
```

---

## Self-Review (completed at planning time)

- **Spec coverage:** raw-read removal (Tasks 2, 3), merged-store reads (2, 3),
  stats replacement (3), lab-day windows (3; send-review already had them),
  unchanged write topology (2, 3 explicitly), plists untouched (in-script
  backend, Task 1), gate release (4), same-day clobber fix (5 — independent
  of the gate; weekly_rollups deferral is explicit and reasoned). Gaps: none
  known.
- **Placeholder scan:** all code steps carry full code; the two "stays exactly
  as is" statements name the precise blocks and why.
- **Type consistency:** `get_store("turso")` (Task 1 signature) used
  identically in Tasks 2/3; `derive_stats` shape matches `format_stats`'s
  existing consumption (`total_prompts`, `total_sessions`, `total_projects`,
  `projects[].name/prompts/active_days`); `build_prompt` arities match their
  call sites and tests.
