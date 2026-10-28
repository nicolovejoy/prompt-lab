# Health email: lead with what needs attention (#98)

Spec: GitHub issue #98 (`gh issue view 98`). The grading and the checks are
right and must not change; this is presentation plus one piece of memory.

## Global Constraints

- **Grading is frozen.** Do not change `_check_target`, `_check_heartbeats`,
  `_check_nightly_run`, `_build_recent_bad`, `_apply_recent_bad`,
  `_claims_vs_remote`, `HEARTBEATS`, `STAGE_ARTIFACT`, thresholds, or the
  `?dry=1` JSON shape. Every `ok`/stale/unchecked verdict the email shows
  today it must still show; only where and how it is printed changes.
- **Nothing red below the fold, nothing green above it.** Every item the
  current email renders red (down target, stale or never-produced
  heartbeat, unchecked heartbeat, not-ok nightly run and each of its detail
  lines, each `recent_bad` night, `uptime archive: 0 rows written`) becomes a
  problem line in the attention block. Everything green or grey (uptime
  table, "all N artifacts fresh", a good nightly-run headline, recovered
  nights, "N monitors archived") goes below the separator.
- **The email must always send.** State read/write is a side quest, like
  the pause lookup and the uptime archive: wrap it, log, continue. A state
  failure never raises out of the handler and never blocks the send.
- **State lives in `health_email_state`** (cloud-direct Turso table, key/value,
  columns `key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT`). New
  key: `reported_problems`. Never add a sync leg for it.
- **Lab day, never UTC**, for every date: use `lab_today()` from
  `day_helper`.
- Tests are standalone runners, not pytest:
  `/Users/nico/src/prompt-lab/.venv/bin/python scripts/test_web_api.py`
  (run from the worktree root; the worktree has no `.venv` of its own).
  CI ruff is pinned to 0.15.22:
  `/Users/nico/src/prompt-lab/.venv/bin/ruff check web scripts` if installed,
  otherwise `uvx ruff@0.15.22 check web scripts`.
- Voice: plain language, terse, no issue numbers in email text, name the
  specific artifact or stage.

## Task 1: Problem model and its memory (web/api/health_report.py)

Pure functions plus two state helpers. No change to `_compose` or the handler
yet, so the existing suite must stay green untouched.

1. `_problems(results, heartbeats, nightly_run, uptime_rows)` → list of
   problem dicts, each:
   `{"key": str, "severity": "down"|"stale"|"unchecked", "text": str,
   "short": str, "age_days": int|None, "since": "YYYY-MM-DD"|None}`.
   `text` is the full plain-language line WITHOUT the NEW/Day prefix;
   `short` is the subject-line fragment; `age_days` is the artifact's own age
   where one exists, else None; `since` is the artifact's own last date
   where one exists, else None. Sources and keys:
   - Down target → key `target:<name>`, severity `down`,
     text `<name> is down (<status or "unreachable">)` plus ` — <note>` when
     the result has a note, short `<name> down`, age None.
   - Heartbeat `ok is False` with a `last` → key `heartbeat:<name>`,
     severity `stale`, text
     `<name> has not landed for <age> days (last <last>)`,
     short `<name> <age>d`, age_days = `age_days`, since = `last`.
   - Heartbeat `ok is False` with no `last` (never produced, or unparseable)
     → key `heartbeat:<name>`, severity `stale`, text
     `<name>: <note>`, short `<name> never`, age None.
   - Heartbeat `ok is None` → key `heartbeat:<name>`, severity `unchecked`,
     text `could not check <name> (<note>)`, short `<name> unchecked`.
   - Nightly run `ok is None` → key `run:unchecked`, severity `unchecked`,
     text `could not check the nightly run (<note>)`,
     short `nightly run unchecked`.
   - Nightly run `ok is False` on the NEWEST row. One problem per fact,
     never a combined line:
     - no `lab_date` (never produced) → key `run:newest`, text
       `nightly run: <note>`, short `nightly run never`.
     - `age_days > NIGHTLY_RUN_MAX_AGE_DAYS` → key `run:newest`, text
       `no nightly run for <age> days (last <lab_date>)`,
       short `nightly run <age>d`, age_days/since from the entry.
     - status `running` → key `run:newest`, text
       `nightly run <lab_date> started but never finished`,
       short `nightly run died`.
     - each failed stage (outcome in `FAILED_OUTCOMES`) → key
       `stage:<stage name>`, text
       `nightly <lab_date>: <stage> <outcome>` plus ` — <detail>` when present,
       short `<stage> <outcome>`.
     - status not ok and no failed stage → key `run:newest`, text
       `nightly <lab_date>: run reported <status>`,
       short `nightly run <status>`.
     - each mismatch → key `publish:<artifact>`, text
       `<artifact>: the run made <claimed>, Turso has <remote or "nothing">
       — publish is dropping rows`, short `<artifact> not published`,
       since = remote, age_days = days from remote to `lab_today()` (None
       when remote is None).
     - unknown-claim and missing-claim notes (the `claim names an artifact…`
       and `run recorded no claim for…` fragments of `note`) → key
       `run:claims`, text = that fragment, short `run claims drift`.
       Derive them by splitting the existing `note` on `"; "` and keeping
       fragments that start with those two phrases — do NOT recompute
       `_claims_vs_remote`.
     The trailing `N bad night(s) in the last 7 days` fragment that
     `_apply_recent_bad` appends to `note` must NOT become its own line:
     each bad night is listed individually below.
   - Each `recent_bad` entry → key `night:<lab_date>`, severity `stale`,
     text `nightly <lab_date> failed: <note>`, short `bad night <lab_date
     as MM-DD>`, since = lab_date, age_days = days since lab_date.
   - `uptime_rows == 0` (not None) → key `archive:zero`, severity `stale`,
     text `uptime archive wrote 0 rows today`, short `uptime archive empty`.
   Order: severity (`down`, then `stale`, then `unchecked`), then newest
   first by `since` (None counts as today, i.e. newest), then key, so output
   is deterministic.
   Host: include ` on <host>` after the lab date in nightly lines ONLY when
   the newest row and the `recent_bad`/`recovered` rows name more than one
   distinct host. Helper: `_hosts_differ(nightly_run)`.

2. `_mark_new(problems, prior, today)` → `(problems, new_state)`. `prior` is
   the decoded state (dict `{key: first_seen_iso}`) or None when the read
   failed. For each problem: `first_seen` = `prior[key]` if present else
   `today`; `is_new` = `first_seen == today` (so a second send the same day
   still says NEW — that is deliberate); `day` = `age_days` when it is not
   None, else `(today - first_seen).days + 1`. When `prior is None` (read
   failed): `is_new = False`, `first_seen = None`, `day = age_days` (may be
   None). `new_state` = `{key: first_seen or today}` for current problems
   only, so a problem that cleared and comes back counts as new again.
   Prefix helper `_prefix(p)`: `"NEW today"` when `is_new`, else
   `f"Day {day}"` when day is not None, else `"Ongoing"`.

3. `_get_problem_state()` → dict or None. Reads
   `SELECT value FROM health_email_state WHERE key = 'reported_problems'`.
   No row → `{}` (first email ever: everything NEW). Exception or
   unparseable JSON or non-dict → None, with a `print` log line.
   `_set_problem_state(state)` → upsert of `json.dumps(state, sort_keys=True)`
   with `updated_at = _utc()`, same SQL shape as `_set_paused_until`. Never
   raises; logs on failure.

Tests (new `@test` blocks in `scripts/test_web_api.py`, next to the existing
health tests, calling the functions directly on a module from
`_health_mod()`): one per source type above asserting key/severity/short;
the NEW/Day/Ongoing prefix for (new, continuing with artifact age,
continuing without artifact age, read failed); a cleared problem dropped from
`new_state`; ordering; host shown only when hosts differ; the `bad night(s)`
fragment never becomes a line; state read returns `{}` on no row and None on
exception; state write swallows an exception.

## Task 2: Rewrite `_compose` and wire the state into the handler

1. New `_compose(results, joke, pause_url, heartbeats=None, uptime_rows=None,
   nightly_run=None, problems=None)`. `problems` is the marked list from
   Task 1; when None, compute `_problems(...)` and mark with `prior=None`
   (keeps callers and tests that pass no state working).
2. **Subject.**
   - No problems: `✅ nothing needs attention · <up>/<total> up`.
   - Otherwise emoji `🔴` if any `down`, else `🟡`; then
     `<n> problem(s)` (singular when 1), then ` (<k> new)` when k > 0, then
     `: ` and the `short` of the first 3 problems joined by `, `, then
     ` +<rest> more` when more than 3.
     Example: `🟡 2 problems (1 new): review email 3d, weekly rollups not published`.
3. **Body, text and HTML in the same order.**
   1. Attention block. Heading `What needs attention`. One line per problem:
      `<prefix>: <text>`. Empty → the single line `nothing needs attention`.
      In HTML: red text for `down`/`stale`, amber for `unchecked`, NEW
      lines bold.
   2. Separator: text `--- working ---`; HTML `<hr>` followed by a muted
      `Working` heading.
   3. Working section: the uptime table (all targets, as today), then
      `heartbeats: all <n> artifacts fresh` when none are stale/unchecked,
      otherwise `heartbeats: <fresh>/<n> fresh` (the failures are already
      above); then the nightly run line when ok:
      `nightly run <lab_date>: ok, <n> stages` (host only per
      `_hosts_differ`); then each recovered night
      `recovered <lab_date>: <note>`; then `<n> monitors archived` when
      uptime_rows > 0.
      If the state read failed, add the muted line
      `could not read yesterday's problems, so nothing is marked new`.
   4. Footer unchanged: pause link, tune prompt, joke.
4. **Handler.** After the pause check and only on the send path (never on
   `?dry=1`, never when paused): `prior = _get_problem_state()`, build
   problems, `_mark_new`, compose, send, and only after `_send_email`
   returns call `_set_problem_state(new_state)`. Add `"problems": [keys]` to
   the send response JSON.
5. **Remove** `_nightly_run_headline` and `_nightly_run_details` if nothing
   else uses them (grep first, including `web/index.html`).
6. **Update existing tests to the new contract without weakening intent.**
   Every existing assertion about subjects and bodies encodes a rule; keep
   the rule, change the string. Examples: "a bad run escalates an
   otherwise-clean subject" still asserts 🟡 and that the subject names the
   failing stage or run; "unchecked doesn't say stale" still asserts the
   subject does not call an unchecked item stale; "artifacts name
   themselves in the subject" still asserts `review email` appears;
   "0 rows written must be unmissable" now asserts the archive line is in the
   attention block, above the separator. Extend the `_health_mod` turso stub
   so `reported_problems` reads can return a chosen prior state and writes
   are recorded in `mod._state_writes`, keeping the pause lookup's existing
   behaviour. New tests: the green email puts nothing above the separator
   except `nothing needs attention`; a red item never appears below the
   separator; state is written only after a successful send; a send failure
   writes no state; dry run neither reads nor writes `reported_problems`;
   paused run neither reads nor writes it; a state read failure still sends
   with no NEW markers; NEW vs Day N across two consecutive sends.
7. Update the module docstring's description of the email layout in a
   short paragraph (what's above the fold, what's below, what
   `reported_problems` holds and that day counts come from artifact age).

## Task 3: Docs

`docs/current-work.md`: one short entry dated 2026-10-27 saying the health
email now leads with problems, what `reported_problems` stores, and that the
first email after deploy marks everything NEW because the memory starts
empty. No CLAUDE.md change unless an existing line is now false (grep
CLAUDE.md for "health email" and fix only false statements).
