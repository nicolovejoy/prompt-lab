# Dashboard redesign plan — hybrid "triage-over-stream"

Status: proposed (2026-06-24). No code yet. Supersedes the ad-hoc "header + heatmap + cost + timeline + intentions stack" that CLAUDE.md flags as having "no clear above-the-fold frame."

## Problem

The cloud dashboard (`web/index.html`, single-file Preact+HTM) is a **passive log viewer** with two organizing axes fighting each other — *by-project* (home grid, project detail) and *by-time* (the now-removed Reviews tab, the per-project timeline) — and **no "what needs me?" frame**. For a tool that's glanced at, not worked in, the front door should answer attention first and browsing second.

## Mental model: A-over-B, project pages as refined-C

- **A — triage (status-first):** a thin attention band answering "what needs me right now?"
- **B — stream (time-first):** a unified reverse-chron feed of activity across all projects (this is what `/review` synthesized but had nowhere to live).
- **C — portfolio (refined):** project pages stay project-primary, reorganized into a coherent README-like view.

Home = **thin A band over a B stream.** Detail = **C**. Machine-voice marker on all AI-authored text throughout (tenet #1).

## Data we already have (no backend needed for Phase 1–2)

SPA calls only 6 endpoints: `login, info, overview, project, cost_timeline, ask`.
- `/api/overview` → `week` stats, `by_project` (daily summaries), `activity_by_project` (year heatmap data), `all_projects`.
- `/api/project?name=` → `snapshot` (incl. `state_summary`, the weekly Sonnet snapshot, + 7d counts, links, inception), `activity`, `summaries`, `rollups`.
- `/api/cost_timeline?project=&since=` → daily per-model spend.

Dead serverless functions (not called by the SPA, candidates to delete alongside this work): `intentions.py`, `projects.py`, `rollups.py`, `summaries.py`. Keep `public_history.py` (separate external consumer).

## Phase 1 — restructure, pure frontend (lowest risk, no new endpoints)

**Home → stream.** Replace the flat project-card grid with a recency-sorted cross-project feed built from `overview.by_project` summaries (each item: date · project · distilled phrase, expandable to summary + key_decisions + counts — generalize the existing `TimelineView`). Keep the week-stats line. Keep the dormant toggle. No LLM cost — the stream is the raw, well-ordered summaries, not a regenerated digest.

**Project detail → Now / Trajectory / Cost / History.** Reorder what already renders:
- **Now** — `state_summary` (machine-voice marked), links, 7d counts.
- **Trajectory** — year heatmap.
- **Cost** — existing CostChart.
- **History** — existing interleaved timeline (summaries + rollups).

**Machine-voice marker.** Wrap `state_summary`, rollup narratives, and daily-summary text in the italic + muted + `↳ from claude` convention already shipped on PianoHouseProject.org. Reusable inline component in `index.html`.

## Phase 2 — triage band (cheap signals, compute client-side from existing data)

Thin band at the top of home. v1 signals computable with no backend:
- **Went quiet:** project with activity in the last ~14d but no session in the last N days (from `activity_by_project` / summary dates).
- **Cost spike:** a recent day/week notably above the project's trailing baseline (from `cost_timeline`).

Healthy projects collapse below the band into the Phase-1 stream. If nothing needs attention, the band is empty/absent — the stream is the whole page.

## Phase 3 — real ops/health signals (needs backend plumbing; optional)

Signals worth surfacing that aren't in the data model yet:
- **Broken pipeline / nightly** (exactly what bit us: the review LaunchAgent failed silently for 3.5 weeks). Would need a stored health/heartbeat per nightly job.
- **Public-data drift-guard hit** — ties into the existing roadmap item "wire `check_public_allowlist.py` into `sync_to_turso.py`"; surface a hit here.
- **Open threads / next-step** — not structured today (CLAUDE.md "Next Steps" is prose; daily `key_decisions` are past-tense). Would need a captured "next" field.

## Cross-project synthesis (the killed Reviews content)

Don't bring back a nightly LLM job. If a narrative digest is wanted, make it **on-demand** (admin button, like Ask) that synthesizes the current week from summaries at click time — pay per use, not per night. Default: the Phase-1 stream replaces it entirely with zero LLM cost.

## Decisions (resolved 2026-06-24)

1. **Home priority — triage-band-thin / stream-primary.** Confirmed. Not a bigger triage dashboard; the stream is the page, the band sits thin on top.
2. **Cross-project synthesis — dropped entirely.** No nightly, no on-demand button. The Phase-1 stream replaces it at zero LLM cost.
3. **Triage band — admin-only** (gated like Ask). Read-tier viewers see the stream + project pages, not the band. Revisitable.
4. **First PR — Phase 1 only** (reorg + machine-voice + delete 4 dead endpoints), then reassess before Phase 2.

Deferred: start next session (not 2026-06-24).

## Sequencing

Phase 1 is a self-contained `index.html` PR (plus deleting the 4 dead endpoints). Phase 2 is additive client-side. Phase 3 is backend and can wait / fold into the drift-guard wiring already on the roadmap.
