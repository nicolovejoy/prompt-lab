# Project alias mapping layer — plan

**Status:** implemented (2026-05-11). Steps 1–7 landed in a single session; five operator renames applied locally and synced to Turso. Kept as the design record.
**Goal:** make project renames a single non-destructive operation (`INSERT INTO project_aliases`) that all readers honor transparently across SQLite (local) and Turso (cloud).
**Why now:** directory `offer-builder` is now `byside`; `frontend` rows in Turso belong to `musicforge`. Renames will keep happening (the Next Steps already lists `MusicForge → musicforge`, `pianohouse → selected-projects`, `dashboard → sentiment-arbitrage`). One-off SQL each time is error-prone — there are 8+ tables holding a project name and 9+ read sites that filter on one.

---

## 1. Design decision (the thing to review)

**Canonicalize on read, not on write.** Rows keep whatever name they were inserted with. Every read that filters by project expands the input through `project_aliases` and queries `WHERE project IN (canonical, alias1, alias2, …)`. Every aggregation that groups by project folds alias buckets into the canonical bucket.

Rejected: canonicalize-on-write + one-time backfill. Simpler reads, but requires touching the hook (lives outside this repo at `~/.claude/hooks/log-prompt.sh`), is harder to reverse, and we already started building the read-side resolver — finish the design we picked, don't switch.

Rejected: destructive `UPDATE` rename script. Cheaper today, but loses reversibility/audit and re-creates the same problem for every future rename. Use only when we genuinely want to merge same-key rows (see §6 edge cases).

### 1.1 What is local SQLite vs Turso?

Calling this out so reviewers don't waste cycles on it:

- **Local SQLite (`~/.claude/prompt-history.db`) is the primary, source-of-truth store.** It captures raw prompts via the `~/.claude/hooks/log-prompt.sh` hook, holds `prompts` / `sessions` / `commits` (never synced to cloud, per the "no raw prompts" rule in CLAUDE.md), and is what the synthesizer, `/handoff`, `/readup`, `/ask`, and the local Flask dashboard read from.
- **Turso is a published, curated subset** — only derived/processed tables (`daily_summaries`, `weekly_rollups`, `intentions`, `project_aliases`, `public_*`). It exists to power the cloud dashboard and external consumers like `selected-projects`.

We are not eliminating local SQLite. The alias layer must work on both, with local as primary and Turso as downstream mirror via `sync_to_turso.py`.

---

## 2. Current state (what already exists, what's missing)

**Schema (✓ defined, ✗ not deployed locally):**
- ✓ `store/sqlite_store.py:139` — `project_aliases(alias PK, canonical NOT NULL)`
- ✓ `store/turso_store.py:186` — same
- ✓ `dashboard/server.py:79` — same as migration `007`
- ✗ Local SQLite does **not** have the table yet. `migrate()` is failing at line 130 (`CREATE UNIQUE INDEX idx_intentions_project_intention`) because of 22 duplicate `(project, intention)` pairs. The `project_aliases` block (line 139) is in the same `executescript()` so never runs.

**Helpers (✓ partial):**
- ✓ `web/turso_helper.py:resolve_project_names(name) -> [canonical, …aliases]` — Turso only
- ✓ `store/base.py:get_project_aliases() -> dict[alias, canonical]` — both stores implement
- ✗ No equivalent expand-helper in `store/` (only the flat dict). Local resolution has to assemble its own.

**Read sites resolving aliases today (2 of ~13):**
- ✓ `web/api/project.py` — uses `resolve_project_names()` + `IN (placeholders)`
- ✓ `web/api/overview.py` — uses `_load_alias_map()` and folds aggregation buckets

**Read sites NOT yet resolving:**
- `web/api/intentions.py:26`
- `web/api/rollups.py:26`
- `web/api/summaries.py:28`
- `web/api/public_history.py:47, 53`
- `store/sqlite_store.py` — `get_daily_summaries`, `get_weekly_rollups`, `get_intentions`, `get_project_snapshot`, `get_raw_sessions`, `get_day_data`, `get_project_detail`, `get_prompts`
- `store/turso_store.py` — same set of methods
- Distinct-project aggregators (need de-aliasing): `sqlite_store.py:571-573`, `turso_store.py:479-481`
- `dashboard/server.py` — uses `get_store()` so inherits store-level behavior; route handlers don't filter by project directly. Confirms scope = store methods, not separate route work.
- `mobile/serve.py` — does not filter by project (static PWA shell + Turso creds endpoint).

**Write canonicalization (∼ partial, intentional gap):**
- `synthesizer.py:142` canonicalizes for intentions specifically.
- Hook (`~/.claude/hooks/log-prompt.sh`) inserts raw directory name into `prompts`. We deliberately leave this alone — the design is read-side resolution.

**Sync (✓):**
- `sync_to_turso.py:210-231` already pushes the alias table to Turso on every sync (`INSERT OR REPLACE`). Does **not** delete removed aliases — see §6.

---

## 3. Tables that hold a project name

| Table                       | Project column          | Unique key                  | Merge risk on rename |
|-----------------------------|-------------------------|-----------------------------|----------------------|
| `prompts`                   | `project`               | none                        | none                 |
| `sessions`                  | `project`               | none                        | none                 |
| `commits`                   | (none — joined)         | —                           | none                 |
| `daily_summaries`           | `project`               | `(project, date)`           | yes if both have row |
| `weekly_rollups`            | `project`               | `(project, week_start)`     | yes                  |
| `intentions`                | `project`               | `(project, intention)` ¹    | yes                  |
| `project_snapshots`         | `project`               | `(project, snapshot_date)`  | yes                  |
| `public_session_summaries`  | `project` (PK part)     | `(project, session_id)`     | low (session_id distinct) |
| `public_weekly_rollups`     | `project` (PK part)     | `(project, week_of)`        | yes                  |
| `synthesis_log`             | `project`               | none                        | none                 |
| `themes`                    | `projects` (JSON list)  | none                        | per-list dedupe      |

¹ Currently failing to create; that's the blocker.

Canonicalize-on-read sidesteps the merge risk for queries (we just expand the IN clause). It re-emerges only if we later want **one** row per `(canonical, date)` rather than multiple rows from different aliases. Decision: live with multiple rows until proven painful. If painful, write a one-off merger using max(last_seen) / first-non-empty merging.

---

## 4. Implementation steps

### Step 1 — Unblock `migrate()` (prerequisite)
Self-healing dedupe inside `store/sqlite_store.py::migrate()`, run **before** the unique index creation. The dedupe must be **generic** — no hardcoded row IDs, no hardcoded project names. It runs unconditionally on every migrate; on a clean DB it scans, finds zero dup groups, no-ops. This matters because the repo is public: forkers should be able to clone, configure, and `migrate()` without first hand-removing dup rows they don't have.

Behavior:
- Find all `(project, intention)` groups with `COUNT(*) > 1`.
- For each group, keep the row with `MAX(last_seen)` (preserves latest status/model). Update its `first_seen` to `MIN(first_seen)` across the group. Delete the others.
- Wrap in a transaction. Do it in Python around the existing `executescript()` (we need conditional logic, not raw SQL script).
- Run the same self-heal in `turso_store.py::migrate()` unconditionally — it's a no-op on clean Turso and cheap insurance if dupes exist there too.
- Back up `~/.claude/prompt-history.db` before first run on this machine. Forkers don't need this since their DBs are presumably clean; the backup is just because we have known drift here.

Acceptance: `python -c "from store import get_store; get_store().migrate()"` runs clean locally and creates `project_aliases`. Running it a second time is a no-op.

### Step 2 — Promote `resolve_project_names` to the store layer
Add to `store/base.py`:
```
def expand_project(self, name: str) -> list[str]:
    """Return [canonical, *aliases_pointing_to_it]. If name is unknown, return [name]."""
```
Implement in both `sqlite_store.py` and `turso_store.py`. Local impl can use the existing `get_project_aliases()` dict; Turso impl mirrors `web/turso_helper.resolve_project_names` (two queries: alias→canonical, then canonical→aliases). Cache the alias map per-connection — it's tiny and read-heavy.

Acceptance: `store.expand_project("byside")` returns `["byside", "offer-builder"]` after we add the alias.

### Step 3 — Wrap store reads
Every `get_*` method that accepts `project=` should call `self.expand_project(project)` and emit `WHERE project IN ({placeholders})` instead of `WHERE project = ?`. Sites:
- `sqlite_store.py`: lines 181, 208, 288, 379-384, 458, 464, 510, 522, 546
- `turso_store.py`: lines 234, 260, 337, 416-421

Distinct-project aggregators (sqlite 571-573, turso 479-481) should subtract the alias set from the result, so the projects list shows only canonicals.

Acceptance: with an alias `offer-builder → byside`, `store.get_daily_summaries(project="byside")` returns rows where `project ∈ {byside, offer-builder}`.

### Step 4 — Wrap remaining web/api endpoints
Switch from `WHERE project = ?` to the `resolve_project_names()` pattern already used by `project.py`:
- `web/api/intentions.py:26`
- `web/api/rollups.py:26`
- `web/api/summaries.py:28`
- `web/api/public_history.py:47, 53`

Acceptance: hitting `/api/intentions?project=byside` returns offer-builder intentions too (once alias exists).

### Step 5 — CLI
`scripts/alias.py`:
- `add <alias> <canonical>` — INSERT OR REPLACE local; print Turso sync hint or push directly (see §6 open question).
- `rm <alias>` — DELETE local. Same Turso question.
- `list` — print pairs.
- `check` — for each alias, count rows in each project-bearing table to surface "do we want to merge or just alias?"

Acceptance: `python scripts/alias.py add offer-builder byside` adds the row; subsequent reads return merged results.

### Step 6 — Apply the renames we already know about
After steps 1-5 land, run these as **operator commands** (one-time invocations on this machine, not committed scripts — forkers don't have these aliases):

```bash
python scripts/alias.py add offer-builder byside
python scripts/alias.py add frontend musicforge
python scripts/alias.py add MusicForge musicforge
python scripts/alias.py add pianohouse selected-projects
python scripts/alias.py add dashboard sentiment-arbitrage
python sync_to_turso.py   # push aliases to cloud
```

Then verify with the cloud dashboard that stale-name project pages now render alias-merged data.

### Step 7 — Doc updates
- Update `CLAUDE.md` Next Steps: cross off intentions-dedupe blocker; cross off the three known-rename items; add one new line documenting `scripts/alias.py`.
- One-paragraph note in `CLAUDE.md` Architecture section about the alias layer (read-side resolution, write-time names preserved).

---

## 5. Out of scope

- Merging same-key rows (e.g., two daily_summaries for the same date on canonical and alias). Defer until painful.
- UI for managing aliases. CLI is enough.
- Reverse-direction aliases (canonical → alias). Not needed.
- Chained aliases (a → b → c). Reject at insert time: `canonical` must not itself be an alias.
- Multi-canonical aliases (a → b and a → c). Prevented by `alias PRIMARY KEY`.

---

## 6. Resolved decisions + remaining open questions

**Resolved:**
- **CLI scope:** writes to local SQLite only. Propagation to Turso happens via the existing `sync_to_turso.py` path. Rationale: every other write in this repo follows local→sync; dual-writing creates a partial-failure shape (local OK, Turso 5xx) that nothing else has and no resync path exists for. Operator can run `python sync_to_turso.py` manually for "now" if they don't want to wait for nightly. Bonus: works offline.
- **Turso dedupe self-heal:** run unconditionally in `turso_store.py::migrate()`. Idempotent on clean tables. Cheap insurance.

**Open:**
1. **Should `sync_to_turso.py` mirror deletes of aliases?** Currently `INSERT OR REPLACE` only. If we `rm` an alias locally, Turso keeps it. Probably fine for renames (rare), but worth a one-line `DELETE FROM project_aliases WHERE alias NOT IN (?)` sync if the alias table grows. Defer until needed.
2. **Should we cache `expand_project` across a request?** Per-connection cache is enough for now. If the api endpoints get hot we can pre-load the full alias map into request locals.
3. **`themes.projects` (JSON list).** Three options: (a) leave as-is, accept stale names in the themes view; (b) resolve on read by mapping each list element through the alias dict; (c) update theme rows when an alias is added. Recommend (b). Cheap because themes are small.

---

## 7. Risks

- **Migration touches live data.** Back up `~/.claude/prompt-history.db` before step 1. Turso has Turso backups but verify retention before running migration there.
- **Performance.** `WHERE project IN (...)` with ≤5 aliases is negligible. If alias table grows to dozens per canonical, revisit.
- **Hidden read sites.** Step 3 lists every match grep finds in `store/` and `web/api/`. If a future contributor adds a new method using `WHERE project = ?` directly, aliasing silently breaks for that path. Mitigation: small comment near the schema or a test that asserts known-aliased project returns both sides.
- **Hook keeps writing raw names.** By design, but means `prompts` and `sessions` accumulate aliases forever. That's the trade for read-side resolution. Acceptable.

---

## 8. Order of operations summary

1. Back up DB.
2. Land Step 1 (dedupe + migrate). Verify `project_aliases` exists locally and on Turso.
3. Land Step 2 (`expand_project` on the store ABC + both impls).
4. Land Step 3 (rewrite store reads).
5. Land Step 4 (web/api endpoint fixes).
6. Land Step 5 (CLI).
7. Run `scripts/alias.py add` for the five known renames.
8. Push to Turso. Verify cloud dashboard.
9. Update CLAUDE.md.
