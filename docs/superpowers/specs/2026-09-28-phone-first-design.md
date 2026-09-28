# Phone-first dashboard — design

Date: 2026-09-28. Status: approved in session 893 (scope, order, and the
"previews" row). Three PRs, in order: A Visitors rework, B shared phone pass,
C PWA install.

## Intent

Nico reads the dashboard at https://prompt-labs.org on an iPhone, in Chrome or
Safari, and wants to install it to the home screen. He uses the phone for
everything: glancing and exploring. The dashboard should feel natural on a
phone across every screen, not only after individual bug fixes.

Success: every view is reachable one-handed, nothing needs pinch or zoom, and
no control depends on a mouse.

## Evidence (walk at 390x844, real data, 2026-09-28)

- `#/visitors` is the only page that overflows: document width 767px in a
  390px viewport. Cause: `.two-col` collapses to `grid-template-columns: 1fr`,
  and a bare `1fr` track takes its minimum from its content, so the longest
  unwrapped row sets the page width. Trigger: Vercel preview hostnames counted
  as sites, up to 70 characters long.
- Every other route fits 390px.
- Tap targets are small everywhere: window toggles 29px tall, theme toggle
  35x25, Menu 34px tall, Todos "project" links 17px tall, home list links 23px.
- The header wraps to two lines (about 90px).
- 90d and 1y charts scroll sideways inside their panel: 2.5 and 10.3 panel
  widths, 5px bars, nothing indicating that they scroll.
- The hover tooltip is the only per-segment breakdown of a bar, and it is
  gated to hover pointers, so touch has none.
- Each page opens with one or two paragraphs of explanation above the data.
- `#/health` is 8.2 screens: twelve uptime cards fully expanded, with 72 chart
  labels at 12px.
- Not installable: no manifest, no icons.

## Constraints

- One codebase, one URL. `web/index.html` stays a single file served as-is; no
  build step, no new runtime dependency, no separately served JS module.
- Desktop must not get worse. Layout changes are gated to narrow viewports
  (`max-width: 640px`, or `600px` where an existing rule already uses it),
  except fixes that are correct at every width.
- Same data, same API shapes, except the additive changes named below.
- Follow the existing CSS-swap idiom where it fits: both markups render, CSS
  picks. Viewport state in JS is allowed only through a `matchMedia` listener
  that updates on change, so rotation cannot desync it.
- On a phone, prefer a real route or in-flow content over a fixed overlay
  (BULLETIN 2026-09-20).
- UTC at rest, Pacific on display: date buckets come from `labDay()` /
  `labDayOf()`, never `toISOString().slice(0, 10)`.
- Turso returns aggregates as strings; every count is coerced with `int()`.
- The repository is public. Test fixtures are synthetic. Screenshots of real
  data stay in the gitignored `.playwright-mcp/` directory and never go in a
  commit or a PR body.
- CI ruff stays pinned at 0.15.22. Tests are standalone runners, not pytest.

## Testing strategy

Three layers, each with a different job:

1. **Python endpoint tests** in `scripts/test_web_api.py` (CI-gated) for
   server-side behaviour.
2. **Pure JS unit tests**: pure functions live in `web/index.html` between the
   marker comments `// <pure>` and `// </pure>`. `scripts/test_frontend_pure.mjs`
   extracts that block and runs assertions with Node's built-in `assert`
   (CI-gated; Node is preinstalled on the runner). This keeps the single-file
   deploy while giving real unit tests.
3. **Phone layout check**: `scripts/phone/check.mjs` serves `web/` locally,
   stubs `/api/**` with synthetic fixtures, loads each route in Playwright
   under the `iPhone 14` device descriptor, and asserts layout properties
   (no horizontal page overflow, tap-target sizes, no overflowing chart
   scroller). It writes screenshots to `.playwright-mcp/phone/`. Local only,
   not CI-gated: it needs browser binaries and the esm.sh CDN.

## PR A — Visitors rework

1. **Preview hosts fold into one row.** `/api/visitor_overview` relabels any
   site whose hostname ends in `.vercel.app` or begins with `preview.` as the
   literal site `previews`, in `daily`, `paths` and `referrers`, re-aggregating
   rows that collide. The payload gains `preview_hosts`: the number of distinct
   hostnames folded. Real sites' numbers are unchanged.
2. **Overflow fix, every width.** `.two-col` tracks become `minmax(0, 1fr)`.
3. **By site uses the share-bar row** already used by Costs "By project":
   swatch, name, percent, count, and a thin bar under the row. The `previews`
   row carries a sub-label "N preview hosts".
4. **Pages, Referrers, Countries become tabs on a phone.** One tab bar, one
   list visible at a time, default Pages. At desktop width the tab bar is
   hidden and all three lists show in the current two-column layout.
5. **List rows wrap on a phone.** The label wraps onto as many lines as it
   needs and the site sub-label sits under it; the count stays right-aligned
   and fully visible. Desktop keeps one-line rows with ellipsis.
6. **Page explanation collapses on a phone** behind a one-line disclosure
   ("About this data"). Desktop shows the paragraphs as today. Built as a
   reusable `PageNote` component for PR B.

## PR B — shared phone pass

1. **Charts never scroll sideways on a phone.** At narrow width, 90d renders
   weekly buckets and 1y renders monthly buckets; 7d and 30d stay daily.
   Desktop is unchanged (daily bars at every window).
2. **Touch selection with a readout.** On touch, tapping or dragging across a
   chart selects a bucket; a readout under the chart shows its label, total,
   and the per-segment breakdown the hover tooltip shows on desktop. For a
   daily bucket the readout has an "Open day" button going to `#/day/<date>`;
   for a weekly or monthly bucket it lists the bucket's days as tappable chips
   going to the same route. Tapping a bar no longer navigates directly on
   touch, which closes issue #53.
3. **Tap targets are at least 44px tall** on a phone: window toggles, sub-tabs,
   theme toggle, Menu, Todos links, home list links.
4. **Header is one line** on a phone.
5. **`PageNote` on every page** that opens with explanation.
6. **Health uptime cards collapse on a phone** to one row each (name, status,
   30d ratio), expanding in place on tap.

## PR C — PWA install

1. `manifest.webmanifest` with `display: standalone`, name "Prompt Lab",
   theme and background colours from the existing tokens.
2. Icons at 180, 192 and 512px, plus `apple-touch-icon`. Design: the letters
   "PL" in white on the accent colour, generated from an SVG in the repo.
3. `mobile-web-app-capable` meta alongside the deprecated Apple one.
4. Explicit `vercel.json` rewrites for the manifest and icons, so the SPA
   catch-all cannot serve `index.html` in their place.
5. **Bottom tab bar when launched from the home screen**, phone width only:
   the primary destinations, honouring the existing admin/reader filter. In a
   browser tab the current Menu stays.
6. **No service worker.** The dashboard is auth-protected and live; an offline
   cache would show remembered state as current, which is the failure shape
   this repo keeps hitting.

## Out of scope

- A separate mobile site or native app.
- Changing what any page measures or how the API authorises.
- Refactoring the six charts into one component beyond what PR B's shared
  selection and bucketing need.
- CI-gating the phone layout check.
