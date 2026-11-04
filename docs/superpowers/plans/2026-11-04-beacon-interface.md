# Beacon interface: nav event, path scrubbing, versioned script

Spec: none separate. The decisions below were agreed with Nico in session
2026-11-04 (prompt-lab session 1229) and are binding.

## Goal

Make `POST /api/beacon` the documented contract that any site can call
directly. `beacon.js` becomes one client of it. Concretely:

1. Accept a new event, `nav`, for client-side route changes. It is stored
   coarsened (see Global Constraints) so it cannot rebuild a visitor's path
   through a site.
2. Replace ID-like path segments with `:id` before storage, for every event.
3. The Visitors page keeps page loads as the headline number and shows in-app
   views separately.
4. Publish an immutable, versioned `beacon-v1.js` that sites load with an SRI
   integrity hash, plus a doc with the contract and a copy-in snippet.
5. A one-shot script that applies the same path scrubbing to rows already
   stored (dry run by default).

Why: prntd is replacing `beacon.js` with its own call to `/api/beacon` so that
no third-party code runs on `/checkout` and `/admin`. It sends
`{"path","ref","wd"}` as `text/plain` and will add `"event":"nav"` on in-app
route changes. Issue #109 is the question `nav` answers: which pages do
visitors of client-routed apps actually see.

## Global Constraints

- Worktree: `/Users/nico/src/prompt-lab/.claude/worktrees/beacon-interface`,
  branch `claude/beacon-interface`. Commit there. Never push, never deploy,
  never touch `main`.
- Python: the worktree has no venv. Use
  `/Users/nico/src/prompt-lab/.venv/bin/python` (and `.../.venv/bin/ruff`).
- Tests are standalone runners, NOT pytest. Run e.g.
  `/Users/nico/src/prompt-lab/.venv/bin/python scripts/test_web_api.py` from
  the worktree root. `ruff check . --exclude .venv` must pass (CI pins ruff
  0.15.22).
- **The repo is public: tests and fixtures use synthetic data only.** Never
  copy a real path, ID or hostname from production data into a test. Use made-up
  IDs like the ones in this plan.
- No test or script may write to the real Turso database. Turso calls in tests
  are stubbed (follow the existing stubs in `scripts/test_web_api.py`).
- `nav` rows are coarsened at write time, in `parse_event`: `visitor_hash` is
  `""` (the column is NOT NULL), `ts` is the UTC date at midnight
  (`YYYY-MM-DDT00:00:00Z`), and `country`, `device` and `referrer` are `None`.
  `site`, `path` (scrubbed), `event` and `agent` are kept. A `nav` hit does not
  need `BEACON_SALT`. Reason: docs/measurement-policy.md point 2 — on small-N
  sites, per-visitor timestamped navigations would be a session path.
- The accepted body is a fixed interface: JSON (any request content type,
  including `text/plain`), fields `path` (required, starts with `/`), `ref`,
  `wd` or `agent`, and optional `event` (default `pageview`). Site comes from
  the Origin header. Nothing about it may change.
- Path scrubbing rule (function `scrub_path` in `web/beacon_helper.py`), applied
  per `/`-separated segment, after the existing query/hash strip and before the
  `MAX_PATH` truncation. A segment becomes `:id` when it is:
  - a UUID: `^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$`
  - all digits: `^[0-9]+$`
  - a token: `^[A-Za-z0-9_]{16,}$` AND it contains at least two of the three
    classes lowercase letter, uppercase letter, digit.
  Empty segments (leading `/`, trailing `/`, `//`) stay empty, so `/` stays `/`
  and a trailing slash survives.
- Reader-facing copy on the dashboard: plain English, no issue numbers, no
  jargon ("in-app views", not "SPA navigations").
- Commit messages end with a blank line then
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Task 1: Server — `nav` event, path scrubbing, contract tests

Files: `web/beacon_helper.py`, `scripts/test_web_api.py`,
`docs/measurement-policy.md`.

1. `ALLOWED_EVENTS = {"pageview", "login", "nav"}`.
2. Add `scrub_path(path: str) -> str` implementing the rule in Global
   Constraints. Use it in `parse_event` for every event.
3. In `parse_event`, coarsen `nav` rows exactly as Global Constraints says.
   Keep `pageview` and `login` behaviour unchanged apart from scrubbing.
4. Tests (add to `scripts/test_web_api.py`, near the existing `# === beacon.py ===`
   tests, same `@test` style):
   - `scrub_path` table test. Must become `:id`:
     `/offer/status/0b7c1e2a-4d3f-4a1b-9c8d-7e6f5a4b3c2d` → `/offer/status/:id`;
     `/setlist/Xq7RkL2mNp9TzW4vBc1D` → `/setlist/:id`;
     `/projects/QwErTyUiOpAsDfGhJkLz` → `/projects/:id` (mixed case, no digit);
     `/orders/42` → `/orders/:id`;
     `/d/8f3a2b1c9d0e4f5a6b7c` → `/d/:id` (hex);
     `/blog/2026/` → `/blog/:id/`.
     Must stay unchanged: `/`, `/fr/about`, `/song/smoke-723`,
     `/projects/piano-backing-tracks-theory`, `/join/summer-camp-2026`,
     `/studio/presentation/homePage/homePage`, `/review/country-book.html`,
     `/notes/abcdefghijklmnopqrst` (20 lowercase letters, one class only).
   - Contract test, named so it reads as the interface: POST to `/api/beacon`
     with header `Content-Type: text/plain`, Origin `https://shop.example.com`,
     body `{"path": "/shop", "ref": "https://www.example.org/x", "wd": 0}` →
     one INSERT with event `pageview`, path `/shop`, referrer
     `www.example.org`. Same with `"event": "nav"` and
     `"ref": "https://shop.example.com/shop"` → one INSERT with event `nav`.
   - `nav` coarsening: the row has `visitor_hash == ""`, `ts` ending in
     `T00:00:00Z` with today's UTC date, and `country`, `device`, `referrer`
     all `None`, while `agent` still follows `wd`. A `nav` hit is stored even
     with `BEACON_SALT` unset; a `pageview` hit with it unset is still dropped.
   - The existing "drops unknown event types" test still passes and must not
     list `nav` as an unknown event; add an unknown one like `"navigate"` if
     the list doesn't already have one.
5. `docs/measurement-policy.md`: update the allowlist paragraph. Add `nav`, the
   question it answers (which pages visitors of client-routed apps actually
   see, issue #109), and the coarsening (no visitor hash, day-level timestamp,
   no country/device/referrer), and the reason (a per-visitor timestamped trail
   is a session path, point 2). Mention that every event's path is scrubbed of
   ID-like segments before storage.

## Task 2: Visitors API — in-app views alongside loads

Files: `web/api/visitor_overview.py`, `scripts/test_web_api.py`.

1. `daily`: filter `event IN ('pageview','nav')` (plus `agent = 0` and the date
   bounds, as now). Select per date and site:
   `SUM(CASE WHEN event = 'pageview' THEN 1 ELSE 0 END) AS views`,
   `SUM(CASE WHEN event = 'nav' THEN 1 ELSE 0 END) AS navs`,
   `COUNT(DISTINCT CASE WHEN event = 'pageview' THEN visitor_hash END) AS uniques`.
   Coerce `navs` to int like the others, and fold it in `_fold` with `views`
   and `uniques`.
2. `paths`: filter `event IN ('pageview','nav')` so the top pages count every
   page seen. The key stays `views`.
3. `referrers` and `countries`: unchanged, `pageview` only.
4. Login queries: unchanged.
5. Add `"navs_total"` to the payload: the sum of `navs` over the folded daily
   rows.
6. Update the existing `visitor_overview: 200 shape…` test (or add a sibling)
   so the stub returns `navs` as a JSON string (Turso returns aggregates as
   strings) and the test asserts int coercion, folding of `navs` across two
   preview hosts into `previews`, and `navs_total`. Use synthetic hostnames.

## Task 3: Dashboard — show in-app views without mixing them into totals

Files: `web/index.html` (the `VisitorsOverview` component, around the
`<PageNote>` intro and the "By site" list), `scripts/phone/fixtures.mjs`.

1. The headline total, the stacked chart and the By-site bar lengths stay page
   loads (`views`) only.
2. In each By-site row, when that site's summed `navs` > 0, append
   ` · N in-app` (N with `toLocaleString()`) to the row's value text. Rows with
   no navs look exactly as today.
3. When `data.navs_total` > 0, the top-pages section shows a short muted note
   under its title: `Includes in-app views.`
4. Replace the intro's first sentence, currently
   `Anonymous page views, counted by Prompt Lab's own script on each site.`,
   with:
   `Anonymous page loads, counted by Prompt Lab on each site. Some sites also
   report moves between pages inside the app; those show as in-app views beside
   the site, and aren't in the totals or the chart.`
   Keep the rest of the intro (cookies, IP addresses, daily visitor IDs,
   "Only sites with the script installed appear here") as is.
5. `scripts/phone/fixtures.mjs` `visitorOverview`: give one or two synthetic
   sites a nonzero `navs` per day and add `navs_total`, so the phone check
   exercises the new text.
6. Verify: `node scripts/test_frontend_pure.mjs` passes. Then run the phone
   check: `npm --prefix scripts/phone install` (if `scripts/phone/node_modules`
   is missing) and `node scripts/phone/check.mjs`. It is headless; never run a
   headed browser. If browser binaries are missing and cannot be installed,
   report DONE_WITH_CONCERNS saying so rather than skipping silently.

## Task 4: Versioned `beacon-v1.js` with SRI, and the beacon doc

Files: `web/beacon-v1.js` (new), `web/vercel.json`, `scripts/test_web_api.py`,
`docs/beacon.md` (new), `docs/README.md`.

1. `web/beacon-v1.js`: a byte-for-byte copy of the current `web/beacon.js`.
   `web/beacon.js` itself is unchanged (it stays the unversioned URL existing
   sites load).
2. `web/vercel.json`: route `/beacon-v1.js` to itself the way `/beacon.js` is
   routed (before the SPA catch-all), and give `/beacon-v(.*).js` (or the
   equivalent pattern Vercel accepts) the headers
   `Cache-Control: public, max-age=31536000, immutable` and
   `Access-Control-Allow-Origin: *` (SRI on a cross-origin script requires
   CORS).
3. Test in `scripts/test_web_api.py`: compute
   `"sha384-" + base64(sha384(web/beacon-v1.js bytes))` and assert it equals a
   constant in the test; on failure the message says versioned beacons never
   change and to publish `beacon-v2.js` instead. Also assert the
   `vercel.json` headers above exist for the versioned file and that the SPA
   catch-all is still last.
4. `docs/beacon.md` — the contract doc, written for an agent in another repo:
   - The interface: endpoint, method, body fields, content type note, Origin,
     events (`pageview`, `nav`), what gets dropped, ID scrubbing, `nav`
     coarsening, and the change promise: prompt-lab posts in the site's handoff
     channel before changing anything, and a contract test guards it.
   - Install option A, recommended where the site owns its code or has
     sensitive pages: a copy-in snippet. Provide a plain JS function
     (~20 lines, mirroring beacon.js: `wd` from `navigator.webdriver` and the
     `pl_agent` switch, sendBeacon with `text/plain` Blob, fetch no-cors
     keepalive fallback, never throws) that takes an event name; and a
     Next.js App Router client-component example that sends `pageview` on the
     first render and `nav` on each later `usePathname()` change. Advise
     skipping admin paths.
   - Option B: the versioned tag, with the real integrity value from step 3:
     `<script defer src="https://prompt-labs.org/beacon-v1.js" integrity="sha384-…" crossorigin="anonymous"></script>`.
   - Option C: the legacy unversioned `/beacon.js` tag, kept working, not
     recommended for new installs because it can change under the site.
   - Note that `beacon.js`/`beacon-v1.js` send `pageview` only, once per load.
5. `docs/README.md`: add one line linking `docs/beacon.md` in the index.

## Task 5: Scrub already-stored paths (dry run by default)

Files: `scripts/scrub_page_view_paths.py` (new),
`scripts/test_scrub_page_view_paths.py` (new), `.github/workflows/test.yml`.

1. The script imports `scrub_path` from `web/beacon_helper.py` and talks to
   Turso the way the other `scripts/create_*.py` cloud-direct scripts do
   (follow `scripts/create_page_views.py` for env loading and the Turso call).
2. It selects distinct `path` values from `page_views`, computes the scrubbed
   form, and prints each `old -> new` that differs with its row count, plus a
   total. Print paths only, never visitor hashes.
3. With `--apply` it runs `UPDATE page_views SET path = ? WHERE path = ?` for
   each changed path and prints the rows changed. Without `--apply` it writes
   nothing and says it was a dry run.
4. Tests with a stubbed Turso (no network, synthetic paths): the dry run issues
   no UPDATE; `--apply` issues exactly one UPDATE per changed path with the
   right arguments; unchanged paths produce no UPDATE.
5. Add the new test to `.github/workflows/test.yml` following the existing
   step pattern.
