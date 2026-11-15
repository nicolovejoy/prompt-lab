# Project alias mapping layer — plan

**Status:** implemented (2026-05-11). Steps 1–7 landed in a single session; five operator renames applied locally and synced to Turso. Kept as the design record; the implementation steps are in this file's git history.
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
- **Hidden read sites.** Every read in `store/` and `web/api/` was wrapped when this shipped. If a future contributor adds a new method using `WHERE project = ?` directly, aliasing silently breaks for that path. Mitigation: small comment near the schema or a test that asserts known-aliased project returns both sides.
- **Hook keeps writing raw names.** By design, but means `prompts` and `sessions` accumulate aliases forever. That's the trade for read-side resolution. Acceptable.
