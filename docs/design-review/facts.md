# Design review fact base (2026-11-04)

Measured on `main` at `6c24ec4`. Fact-finding only: no recommendations. Where something looks odd it is phrased as an open question (end of doc).

## 1. Scope and how to use this doc

- Scope: the dashboard at prompt-labs.org (`web/index.html`, 4,902 lines, one file, Preact+HTM, no build) and every email the repo sends.
- Line numbers refer to `web/index.html` unless a file is named. CSS block is lines 36-839, the `:root` tokens are 37-95, module JS is 844-4900.
- Counting method: regex scans over lines 97-4900 (so the token definitions themselves are excluded). Counts are declarations, not rendered elements. They will drift as #14 merges.
- #14 (font-size scale) is PR #112, 12 named steps: 2xs .61, xs .75, sm .85, body-sm .95, body 1.06, md 1.12, prose 1.2 (running text: home timeline, project summary), lg 1.3, xl 1.43, 2xl 1.7, 3xl 1.91, 4xl 2.18 rem. Font sizes below are as on main before that migration; if #112 has merged, read sizes through the tokens.
- Screenshots live outside the repo at `~/.claude/state/prompt-lab/design-review/` (index in section 12). All are from synthetic fixtures (`scripts/phone/fixtures.mjs`), never real data. Caveat: the unsuffixed shots written by `scripts/phone/check.mjs` carry no color-scheme setting, so Playwright's default (light) applies. Explicit `-dark` and `-light` variants were added for the main routes.
- Shipped base font size is the browser default (16px; no `html { font-size }` rule), so 1rem = 16px.

## 2. Routes

Hash routes are parsed in `parseHash` (line 867). Unknown hashes fall to home; an unknown activity metric falls to `sessions`; a malformed day date falls to home. Nav is built from `NAV` (1169) and filtered by `navFor(role)` (1182). The API, not the nav, enforces the admin gate.

- `#/` (home): admin and reader. Pulse KPI tiles (sessions, prompts, commits, API spend, page views; spend and views admin-only, line 1661), 30-day stacked activity chart, "Recent activity" stream grouped by day, dormant and private project chips.
- `#/project/<name>` (+ `/cost`): admin and reader. Header with category and private badges and links, then Now, Trajectory (heatmap), Cost, History (timeline). `/cost` is a detail page. Metadata editor is admin-only.
- `#/activity[/<sessions|prompts|commits>]`: both. Stacked chart with 7/30/90/1y window, by-project list.
- `#/costs`: both. Stacked-by-project spend chart, by-project list, sort toggle.
- `#/todos`: both. Open GitHub issues grouped by repo, searchable, label chips.
- `#/day/<YYYY-MM-DD>`: both. One day's summaries, spend, counts.
- `#/about`: both; the Ask button is admin-only (`onAsk`, line 1547).
- `#/more`: both. Phone destination list (Visitors and Health listed for admin only), theme toggle, log out.
- `#/visitors`: admin only (reader gets an access message). Beacon traffic by site, page, referrer, plus sign-ins panel.
- `#/health`: admin only. Target up/down cards, heartbeats, nightly run, uptime archive with per-monitor charts.
- Login screen (not a route): shown when `/api/login` is not ok. Google button and an optional preview-password form (1074).
- Overlay: Ask modal (4761), admin only, `/` keyboard shortcut.
- Header project picker appears on project routes. Header is a stacked block on desktop, one flex row on phone.

## 3. Token inventory

### 3.1 Colors

- Tokens defined at `:root`: 15 color tokens (bg, card, card-hover, text, text-secondary, border, accent, accent-light, accent-dim, green, green-dim, yellow, yellow-dim, red, red-dim) plus layout tokens (`--safe-top`, `--safe-bottom`, `--tabbar-h`, `--radius`). The light theme overrides all 15. The light override is written twice, verbatim (lines 61-78 in the OS-preference media query, 80-95 for `data-theme="light"`).
- `var(--token)` usage: 442 references (187 in CSS, 255 in inline JS styles). Top: text-secondary 163, border 70, accent 32, text 31, accent-light 31, card 28.
- Raw literals outside `:root`: 21 hex (15 distinct) and 6 `rgba()` (3 distinct), plus 1 `hsl()` and the keyword `white` 4 times.
  - `#fff` x4 and `white` x4 for text on accent (lines 116, 342, 459, 685, 1531, 2209, 3673, 3824): bypasses any on-accent token.
  - `#6e6e6e` x2 (141, 280): the "stale" build-time color, the same value in both themes.
  - Chart palette `COST_PALETTE` (2384-2385): `#6366f1 #22c55e #eab308 #ef4444 #06b6d4 #ec4899 #f97316 #a855f7`, and `COST_OTHER` `#555` (2386). The first four duplicate the dark-theme accent/green/yellow/red values and do not follow the light overrides. `#06b6d4` is also hard-coded on the page-views sparkline (1664).
  - `#c62828` x2 (3235, 3311) as a `var(--red, #c62828)` fallback that never fires (the token exists).
  - `hsl(<hash>, 45%, 45%)` for GitHub label chips (2135), with `#fff` text (2209).
  - Shadows and overlays: `rgba(0,0,0,.4)` x4, `.28` x1, `.5` x1 (266, 321, 670, 675, 2641, 4046).
- Undefined token in use: `--bg-elevated` is referenced 5 times (2806, 3011, 3385, 4325, 4454) and is defined nowhere. Three have a `var(--card)` fallback; two (4325, 4454) have none, so they resolve to transparent.
- Opacity as a color device: 26 `opacity: 0.x` declarations (e.g. text-secondary at .65 / .6 / .7 / .8), which produce additional effective colors not in the token list (contrast numbers in section 7).

### 3.2 Font sizes (before #14)

- 228 `font-size` declarations: 70 in CSS, 158 inside inline `style=` strings in JS. All in `rem` (no px). 38 distinct values.
- Distinct values with counts, ascending: .61(2) .7(1) .72(1) .75(3) .78(1) .79(1) .8(2) .82(6) .85(18) .88(1) .89(12) .9(4) .92(1) .93(7) .95(19) .98(18) 1.02(22) 1.05(1) 1.06(23) 1.09(9) 1.12(20) 1.13(3) 1.15(1) 1.16(15) 1.2(3) 1.23(3) 1.3(6) 1.36(4) 1.43(1) 1.5(1) 1.57(1) 1.68(1) 1.7(3) 1.75(1) 1.9(1) 1.91(6) 2.18(5) 2.32(1).
- Neighbouring near-duplicates are common: .93/.95/.98, 1.02/1.05/1.06/1.09, 1.12/1.13/1.15/1.16. Origin: issue #14 was filed 2026-07-09 against 146 declarations and 24 values; a uniform ~1.36x bump (PR #15) preserved the old irregular ratios, which is why values like 1.09 and 1.23 exist.
- Smallest text: .61rem (9.8px) on the built/synced header sub-line (141) and the signed-in email (`.header-user`, 263).
- Page titles are inline `<h1>` styles: 1.91rem on Todos, Costs, Activity, Visitors, Health; 1.7rem on More, About, Day (see section 5).

### 3.3 Families and weights

- Families: system sans stack on `body` (99); `font-family: inherit` x27; mono stack `'SF Mono', ui-monospace, monospace` x48 (22 + 14 + others, spelled two ways: with and without spaces after commas; a `MONO` string constant at 2500 is used by some chart code). No webfonts.
- Mono is used for: dates, counts, header meta, KPI labels, nav build info, project meta, machine-voice mark.
- Weights: 600 x38, 700 x13, 500 x2, 400 x2, one `650` (1701). `text-transform: uppercase` x22, `letter-spacing` x22 (values .3px, .5px, .06em, .07em, others).
- Numerals: `tabular-nums` x20.

### 3.4 Spacing

- 334 padding/margin declarations, 138 distinct value strings (127 in CSS, 207 inline). Most common: `margin-bottom: 4px` 17, `margin-left: auto` 17, `margin-top: 10px` 11, `margin-top: 6px` 10, `margin-bottom: 8px` 9, `margin-bottom: 16px` 8, `margin-bottom: 12px` 8.
- 90 `gap` declarations, 21 distinct: 8px x27, 12px x15, 2px x8, 6px x10, 10px x6, 14px x6, 16px x3, also 1, 4, 5px.
- No spacing tokens or scale. Card padding alone appears as `14px 16px` (.card), `14px 15px` (.kpi-tile), `14px 16px` (.sidebar-section), `16px` (.cost-placeholder), `14px` (inline), `12px` (inline).
- Container: `max-width: 1100px`, `padding: 0 24px` (101); the same 24px is not reduced on a phone.

### 3.5 Radii, shadows, z-index, transitions

- Radii: 84 declarations, 14 distinct. `var(--radius)` (8px) x22; literal 2px x16, 6px x13, 4px x11, 8px x5, 3px x5, 5px, 1px, 12px (ask modal), 50%. Both `var(--radius)` and a literal `8px` occur for the same role (cards vs `.nav-more`, `.picker-menu`).
- Shadows: 5 uses, 4 distinct: `0 4px 16px` x2, `0 8px 28px`, `0 8px 30px`, `0 20px 60px`. All use black alpha; no light-theme variant.
- z-index: 5, 40, 50 (x2), 100.
- Transitions: 9, 7 distinct (.1s opacity, .15s border/background/transform, .3s max-height). Animations: `spin`, `pulse` (1.5s and 1s).

### 3.6 Breakpoints

- `max-width: 640px` x3 (172 nav collapse, 226 tab bar, 815 tap targets), `max-width: 600px` x4 (460 sub-tabs scroll, 507 two-col, 530 list rows, 545 visitor tabs/page notes), `max-width: 800px` x1 (project layout), `prefers-reduced-motion` x1 (766).
- JS also keys off 640: `NARROW_QUERY = '(max-width: 640px)'` (2478) buckets chart bars on a phone; `CAN_HOVER` (2393) gates hover behaviour.
- Consequence to verify: between 601 and 640px the nav and tap-target rules are in phone mode while list rows, two-column grids and sub-tabs are still in wide mode.

## 4. Repeated components

Shared by design (one implementation, several call sites):
- `StackedBars` (2578) + `ChartReadout` (2699) + `DateAxis` (2415): 5 callers (home 1820, costs 2821, activity 3026, visitors 3526, project cost 4345). `WindowPicker` (3333) was consolidated after five drifted copies (comment at 3330).
- `PageNote` (3322): wide inline note plus a `<details>` on phone. 3 callers (1813, 2055 and visitors/health pages).
- `MachineText` (1069): see 4.8.
- `PulseTiles` (1613) / `.kpi-tile`: home only.
- `SkeletonList`, `.loading`, `.error`, `.empty`: shared classes.

Divergent or duplicated:
- 4.1 Cards. Classes `.card` (6 uses), `.sidebar-section`, `.kpi-tile`, `.cost-placeholder`, `.timeline-expand`, `.review-card`, `.sub-tabs` track, plus 6 inline `background: var(--card)` boxes and 5 inline `border: 1px solid var(--border)` boxes. The health page builds status banners from an inline `banner()` helper (3685 region) rather than a class. Same ingredients (card bg, 1px border, radius 6 or 8, padding 12-16) with different values.
- 4.2 Chips and badges, at least eight separate styles: `.tag` (radius 3, border-colored bg), `.badge` (radius 4, outlined, uppercase), `.status-badge` (radius 3, tinted, uppercase, 3 variants), `.dormant-chip` (radius 4, outlined), `.project-link` (mono, outlined), `.ask-example` (radius 4, filled), `.chart-day-chip` (radius 6, 44px), and inline GitHub label chips (hsl bg, white text, 2209).
- 4.3 Buttons. Classes: `.header-btn`, `.win-btn`, `.sub-tab`, `.ask-btn`, `.login button`, `.nav-toggle`, `.theme-btn`, `.more-row`, `.chart-open-day`, `.review-expand`, `.uptime-toggle`. Plus inline-styled primary buttons: Retry (1531), health re-poll (3673). The "primary" look (accent bg, white text) is hand-written in 5 places (116, 342/459, 685, 1531, 3673) with different padding and font sizes (1.23, 1.16, 1.16, 1.16, 1.06rem).
- 4.4 Tabs / segmented controls. `.sub-tabs` (track with pill, 11 uses), `.win-picker`/`.win-btn` (outlined buttons), `.vis-tabs` (sub-tab reused as phone tabs), `.tab-bar` (standalone), metric switch on Activity (2919, `.sub-tab`-like inline), `.picker` (project menu). Active state differs: `.sub-tab.active` and `.win-btn[aria-pressed]` both accent fill; `.header-btn.active` is a card-colored fill; `.tab.current` is accent-light text only.
- 4.5 Disclosure. `.page-note-narrow` details/summary with CSS chevron (556-568); `.uptime-toggle` button with `aria-expanded` and a text glyph (3934); `.review-expand`; Todos repo rows with inline toggles; KPI tile cue (`▾`, 1722). Four chevron/glyph treatments.
- 4.6 Charts. Shared: StackedBars. Separate implementations: `Spark` (1577, SVG), heatmap (CSS grid of 8px cells, 1975), uptime strip and latency bars (3854-4085, inline divs), share bars in list rows (inline, `height: 3px`).
- 4.7 Lists/tables. `.list-row` and `.share-row` (shared CSS); `.row-link`; `.timeline-entry`. One real `<table>` (4454, cost detail). Project and day pages build their own rows inline.
- 4.8 Machine voice. `MachineText` (1069) wraps AI-authored text in `.machine` (italic, text-secondary) and appends `.machine-mark` "↳ from claude" (mono, .82rem, uppercase, opacity .6). Used in 5 places: home stream (1924), day page (3279), project Now (4623), timeline summary (4695), rollup narrative (4720). `mark` can be turned off. Not applied to: the Ask answer, the health email joke, the review email (see section 8).
- 4.9 Headers/nav. `Header` (1201) renders two navs always (wide row with "More" panel; phone dropdown), swapped by CSS. `TabBar` (1329) renders always and CSS shows it only in standalone. Theme button also rendered twice (`.theme-narrow`). `<h1>` page titles are inline-styled per page.

## 5. Phone vs desktop

Below 640px:
- Header becomes one flex row: logo, theme button, Menu button (icon only, label visually hidden). Wide nav hidden, dropdown list appears at full width. `PL` short logo beside the project picker.
- Tap targets: `.tap`, `.win-btn`, `.sub-tab`, `.picker-item`, `select` get `min-height: 44px`; selects drop native appearance (WebKit ignores height).
- Phone check (`scripts/phone/check.mjs`) enforces 44px tall on every tap target, no horizontal overflow at 390px, header one line, and more. Latest run (2026-11-04): 404 passed, 0 failed.
Below 600px:
- Sub-tabs scroll horizontally, two-col grids stack, list rows wrap (label over sub-label), Visitors' three lists collapse behind tabs, `PageNote` folds behind a one-line `<details>`, uptime cards start collapsed (48px rows), chart readout shows "Open day" and day chips instead of hover.
- Below 800px the project page goes single column.
Standalone (home-screen) mode, below 640px only:
- `data-standalone` is set by the head script (`navigator.standalone` or `display-mode: standalone`). A fixed bottom tab bar (Home, Activity, Todos, Costs, More; `--tabbar-h` 50px plus safe-area) replaces the Menu button and dropdown. Visitors, Health and About live in the More list. Project and day pages highlight no tab. No service worker by design.
- In a browser tab the tab bar exists in the DOM but is `display: none`.
Unchanged on phone: the `.container` 24px side padding; h1 sizes; chart density is JS-bucketed at 640.

## 6. Themes

- Dark is the `:root` default. Light applies via `@media (prefers-color-scheme: light)` when no explicit choice, or `:root[data-theme="light"]`. The toggle (header, More page) writes `localStorage.promptlab_theme` and sets `data-theme` synchronously in `<head>` before paint. Initial toggle state comes from the OS query (1154). `<meta name="theme-color">` is fixed `#111` for both themes. No `color-scheme` property is declared, so native controls and scrollbars follow the UA, not the theme.
- The light block is duplicated (two copies must be edited together).
- Light-theme text tokens were retuned on 2026-07-09/10 (secondary text `#777` to `#d0d0d0` in dark) after an "old eyes" readability complaint; verification then was by computed contrast, with a phone confirmation on 2026-07-10.

## 7. Contrast (WCAG 2.x relative luminance, computed 2026-11-04)

Tokens (dark: bg #111, card #1a1a1a; light: bg #fafafa, card #fff).

Dark theme:
- text on bg 14.99, on card 13.82. text-secondary on bg 12.24, on card 11.28.
- accent (#6366f1) on bg 4.23, on card 3.90. FAILS 4.5:1 for body text; meets 3:1 only. It is used for text links/buttons (`.chart-open-day`, `.page-note-narrow summary`, "Open day", Todos links) at 0.9-1.1rem.
- accent-light on bg 6.33, on card 5.83. green 8.29/7.64. yellow 9.85/9.08. red 5.02/4.62 (passes).
- white on accent (button fill, `.sub-tab.active`, `.win-btn`) 4.47. Just under 4.5 for normal text.
- `#6e6e6e` stale build text on bg 3.70, on card 3.41. FAILS (it is .61rem text).
- text-secondary at opacity .65 (`.header-user`) 5.69; .6 (`.machine-mark`) 5.05; .7 6.46; .8 8.13. All pass.
- red text on red-dim over bg (error banners) 4.33. FAILS by .17.
- Status badges (tinted bg over card): green 5.90, yellow 6.74, accent-light 5.01 (pass).
- Border on bg 1.32, on card 1.21 (decorative separators; card edges barely visible in dark).
Light theme:
- text on bg 18.09. text-secondary on bg 9.93, on card 10.37.
- accent on bg 6.02, on card 6.29 (pass). accent-light on bg 4.28, on card 4.47. FAILS narrowly; used for `.project-name` and h1 titles (large text, passes 3:1), and for small text in `.kpi-cue`, `.status-completed`, `.picker-item.active`, `.tab.current`.
- green (#16a34a) on bg 3.16, on card 3.30. FAILS body 4.5; passes large only. Used for fresh/up text at .61-.85rem (`.header-sub .fresh`, `.more-text.fresh`, `.nav-build.fresh`), `.status-active`, meta-saved.
- yellow (#ca8a04) on bg 2.81, on card 2.94. FAILS even 3:1. Used for stalled badge and health banner text.
- red on bg 4.63, on card 4.83 (pass). red on red-dim over bg 3.98 FAILS.
- Status badge pairs on tinted bg over card: green 2.96, yellow 2.66, accent-light 3.83. FAIL (uppercase .89rem bold text, not large).
- white on accent 6.29; white on accent-light 4.47.
- Effective opacity text: `.header-user` (.65) 3.73 FAILS; `.machine-mark` (.6) 3.31 FAILS; `.nav-build-label`/`.picker-caret` (.7) 4.23 FAILS; `.is-private`/`.dormant-chip.muted` (.62/.66) about 3.8 FAILS; `.heatmap-note` (.8) 5.58 passes. Machine-voice text itself (text-secondary, no opacity) passes.
- `#6e6e6e` stale on bg 4.89 (pass in light).
Chart palette (not text; WCAG 1.4.11 asks 3:1 for graphics):
- Hard-coded in both themes. On the dark bg: all >= 4.23 except `#555` (the "other" band) at 2.53. On the light bg (#fafafa): green 2.18, yellow 1.84, cyan 2.33, orange 2.69, pink 3.38, red 3.61, purple 3.79, accent 4.28; `#555` 7.14. Four of eight series fall under 3:1 on light.
- White text on the hsl label chips: 2.58 to 8.49 depending on hue (varies per label).
- Heatmap cell 0 uses `--border` as fill: 1.32 (dark) and 1.21 (light) against bg.

## 8. Emails

Exactly two emails are sent (both via Resend, plain `urllib`, no templates directory, no shared module):

1. Daily health email (`web/api/health_report.py`, `_compose` line 1187, sender `_send_email` 1269). Built by Python string concatenation. HTML: one wrapper div `font-family:-apple-system,sans-serif;font-size:15px;color:#222`; an `<h3>` at 16px; a `<table>` for the roster; inline-style `<div>`/`<p>` lines; a `<code>` tune-up prompt; an italic joke. No `<html>`, no doctype, no meta viewport, no max-width, no background. Colors are Python constants `_RED #c62828`, `_AMBER #b26a00`, `_GREEN #2e7d32`, `_MUTED #666` (1116-1119) plus literals `#222`, `#ddd`, `#666`. Subject carries emoji state (✅/🟡/🔴), count, new count, first three problem names (`_subject` 1130). A text part is also sent. Structure: "What needs attention" (problems, red/amber, bold if new), rule, "Working" (roster table, green/grey lines), pause link (default browser blue), tune prompt, joke. Dry-run: `?dry=1` returns JSON without sending.
2. Nightly review email (`send-review.py`). The HTML is not templated: Claude (Sonnet) returns `subject`, `html`, `text` through a tool schema (`REVIEW_TOOL`, line 31), guided only by a prose style spec in the system prompt (inline CSS only; `-apple-system, system-ui, sans-serif`; 600px max width, centered; headings 18px / 16px bold; body 14px, line-height 1.5; muted footer "Generated by Prompt-Labs"). Visual output therefore varies per run. Structure of the last 20 stored daily/weekly emails (aggregate scan, local DB, read-only): all 20 use a 600px container; 16 are full documents (doctype, html, head, meta), 4 are fragments; no `<style>` blocks, no tables; type sizes seen 12/13/14/16/18/20/22px (14px and 16px dominate); text colors #333 (190 uses), #111 (158), #222, #999/#888/#aaa for muted; page background #f5f5f5 with a #ffffff column in 16 of 20; 6 distinct (font-stack spelling, first text color) fingerprints across 20 emails (e.g. `#111`, `#999999`, `#1a1a1a`, `#888` as first color). Content is written in the machine-voice register (first person plural) but carries no "↳ from claude" mark.
3. Not emails but HTML responses from the API: the pause-confirmation page (`_html`, health_report.py 1433, inline `font-family:-apple-system,sans-serif;margin:3rem`) and the sign-in failure page (`web/api/callback.py` 125, an unstyled `<h1>` and `<p>`). Both are bare, unthemed.

Sharing with the dashboard: none. No token, color, font size or component is shared. The health email's green/red/amber (#2e7d32/#c62828/#b26a00) differ from the dashboard's (#22c55e/#ef4444/#eab308 dark; #16a34a/#dc2626/#ca8a04 light). Emails have no dark-mode handling (no `color-scheme`, no media query); the review email sets a light page background and the health email sets none (client default).

Other generated output: the bi-monthly report is Markdown (`~/.claude/state/prompt-lab/reports/`), not HTML.

Rendered samples (synthetic data, no network): the health email HTML for a healthy and a problem state, at 700px and 390px, plus a plain-text version. The review email could not be rendered without calling the model, so `review-MOCK-synthetic` is a hand-written mock mirroring the aggregate structure above; it is labeled MOCK and is not real output.

## 9. Conventions already decided

From CLAUDE.md and docs (treat as settled unless Nico says otherwise):
- Machine voice: AI-authored text renders italic + muted with "↳ from claude" (settled; shipped on dashboard, not in emails).
- UTC at rest, Pacific on display; no `toISOString().slice(0,10)` date buckets; use `Intl.DateTimeFormat('en-CA', {timeZone: 'America/Los_Angeles'})`.
- Phone: 44px minimum tap targets on every route (enforced by the phone check); installable to the home screen; bottom tab bar only when launched standalone; deliberately no service worker (live, auth-protected data must not look current from cache).
- Dashboard is one file with no build step; pure helpers sit between `// <pure>` and `// </pure>` for node tests.
- Both markups render and CSS picks (nav, theme icon, page notes, visitor tabs): no viewport state in JS to desync on rotate (the chart bucket query at 640 is the exception).
- Reader-facing copy should live in content/copy files, not inline in components (applies to repos that ship French; this dashboard's strings are inline today).
- Clickable bare URLs, numbered questions, self-contained smoke-test steps (agent conventions).
- Test browsers are Edge for desktop, WebKit iPhone 14 for phone; always headless.
- Fixtures are synthetic; the repo is public.
- No display names in the sign-ins panel (anonymity). `private` on project metadata is cosmetic.
- Health email: lead with what changed and how long wrong; "grading lag" is deliberate and not to be simplified; the review email is a record for the engineer (no glossary asides, no issue numbers).
- Nobody has defined: spacing scale, radius scale, shadow scale, an on-accent text token, an email style guide. (#14 covers font sizes only.)

## 10. Known pain points and history

Dated, from issues, `docs/history.md`, `docs/dashboard-redesign-plan.md` and the prompt history:
- 2026-06-24: dashboard restructured from a card grid to a home stream plus Now/Trajectory/Cost/History project pages; machine-voice marker introduced (`dashboard-redesign-plan.md`, Phase 1 shipped; later phases are historical).
- 2026-07-09: #14 filed (146 font-size declarations, 24 values, no scale). 2026-07-09/10: readability complaint ("text too small / low contrast on mobile"), four PRs (#15 uniform ~1.36x bump, #16 theme toggle plus contrast pass, #17 header meta was `display:none` on phones and the nav lacked wrap, so the theme toggle was off-screen). Verified by computed contrast only; confirmed by Nico on a phone 2026-07-10. Pattern: readability, tiny text, discoverability of the theme toggle.
- 2026-07-13: #21 Visitors and #22 Costs chart mobile passes (charts with 8px columns unusable on a phone).
- 2026-08-17: #53 iOS tapping a chart day zooms the page too far (small tap targets, 8px columns).
- 2026-08-29: #49 copy review of every user-visible string (batches 2-4 in `docs/copy-review-49.md`, 312 lines); the standard is "says what is counted, over what window, in words a reader who did not build the system can follow". Builder language (aliases, canonical name, "reconciles") was flagged repeatedly.
- 2026-09-07: heatmap month labels were on a different scale than the grid (made six months of work read as dead since March); fixed structurally.
- 2026-09-28: phone-first A/B/C (#75, #76, #77): Visitors on a phone, shared chart, one-line header, 44px targets everywhere, home-screen tab bar.
- 2026-10-27: #98 health email re-ordered to lead with problems and age; earlier (2026-09-06) a review-email style revision was accepted ("email looks great").
- 2026-11-04: Health on a phone re-checked by eye after the full phone run (404/404 pass).
- 2026-11-05: Nico's latest note proposes a thorough UX/design-system review of the whole platform (this review).
- Prompt-history DB note: the `prompts` table for this project has few UI-specific entries (the logger drops prompts under 20 characters and slash commands), so recurring complaints are better read from the history doc above than from prompt counts. Themes visible in what exists: text size/readability on a phone, emails being "wrong" (no-new-work false negatives, not styling), and wanting emails and summaries to read better, not look different.

## 11. Accessibility facts beyond contrast

- Tap targets: 44px minimum enforced on phone (13 `min-height: 44px` declarations, 48px for uptime rows, tab bar 49px). On desktop there is no minimum (several controls are 4px/10px padded, about 28px tall).
- Focus: global default browser outline is untouched except `.login input:focus { outline: none }` (border-color swap only) (114); the KPI tiles get an explicit 2px accent `:focus-visible` ring (757). Many interactive elements are `<a>` or `<div>` with `onClick` and no `href`, `role` or `tabindex` (e.g. the logo link 1261, timeline entries with `cursor: pointer`, dormant chips 1681 are `<a href>`); 0 uses of `tabindex`, 1 use of `role=` (a group, 3395).
- ARIA: 17 `aria-*` attributes: `aria-label` x7, `aria-expanded` x3, `aria-pressed` x3, `aria-current` on tab bar, `aria-hidden` on glyphs. No `aria-live` regions (loading, errors, saved states are silent to assistive tech). `<nav aria-label="Sections">` on the tab bar only; the header nav is not a `<nav>`. No `alt` text anywhere (charts are divs/SVG without `role="img"` or text alternatives, except one `aria-label` on day chips at 2723). One `<svg>` in markup (Spark) plus others built by string.
- Headings: 8 `<h1>` (one per page view, inline-styled) and 4 `<h2>`; the home page and project page use styled divs (`.section-label`, `.project-name`) instead of headings. No `<h3>`.
- Reduced motion: one media query (766) covering KPI tiles and cues only. `pulse` skeleton, `spin`, `max-height` transition, `.timeline-entry` background/margin hover and chart opacity transitions are not covered.
- Zoom and text size: the viewport meta has no `user-scalable` or `maximum-scale` (pinch zoom allowed). Sizes are rem, so browser text-size settings scale; px is used for spacing and the 8px chart cells, so charts do not scale with text. `-webkit-text-size-adjust` is not set. The 640px breakpoint is in CSS px, so enlarging text does not change layout.
- Color is sometimes the only signal: heatmap intensity (opacity steps of one accent), uptime strip green/amber/red segments (legend present on `#/health`), up/down text color in the health roster (DOWN also has an icon and text).
- Language set (`lang="en"`), `viewport-fit=cover` with safe-area insets used for the tab bar and container.
- Keyboard: `/` opens Ask (admin). Hover-only affordances are gated with `CAN_HOVER`; touch uses tap/drag readouts.

## 12. Screenshot index

Root: `~/.claude/state/prompt-lab/design-review/` (83 dashboard PNGs, 9 email files).

`dashboard/` (names are `<route>-<profile>[-<scheme>].png`; profiles: `desktop` = Edge 1280px, `phone` = WebKit iPhone 14 390px, `standalone` = iPhone 14 in home-screen mode):
- Unsuffixed-scheme baseline shots from the phone check (47): `home|activity|costs|todos|health|about|day|project` in `-desktop` and `-phone` (light, Playwright default); `cost-detail-{phone,desktop}`, `cost-detail-long-phone`, `costs-unmapped-phone`, `day-unmapped-phone`, `header-long-project-phone`, `header-menu-phone` (open phone dropdown), `header-reader-phone` (reader role, no Visitors/Health), chart interaction shots (`*-chart-phone`, `visitors-chart-{drag,empty-bucket,navigate,scroll}-phone`, `home-chart-today-phone`, `project-cost-chart{,-fine}-phone`), `visitors-{desktop,phone,old-payload-phone,no-referrers-phone}`, `health-cards-phone` (uptime cards expanded), `tabbar-*`/`more-admin-*`/`more-reader-standalone` (home-screen mode tab bar and More list).
- Explicit dark: `<route>-desktop-dark` and `<route>-phone-dark` for home, activity, costs, todos, health, visitors, project, about, day (18 files).
- Explicit light: `<route>-desktop-light` and `<route>-phone-light` for home, activity, costs, todos, health, visitors, project (14 files).
- Login: `login-desktop`, `login-phone`, `login-phone-light`, `login-desktop-light` (Google button plus preview password).
`emails/`:
- `health-healthy.html` / `-700.png`: nothing needs attention state.
- `health-problems.html` / `-700.png` / `-390.png`: one down target, one stale heartbeat, one unchecked; plus `.txt` plain-text twins of both.
- `review-MOCK-synthetic.html` / `-700.png`: labeled mock of the review layout (not real model output).

## 13. Open questions for the reviewer

1. Should the dashboard have one on-accent text token and one accent token that passes 4.5:1 for text in dark (accent is 4.23 on bg, 3.90 on card), or is accent text always large/bold by intent?
2. Light-theme green and yellow text are 3.16 and 2.81 on bg; are they meant as text colors at all, or only fills/icons? Today they carry small uppercase status text.
3. Is the `--bg-elevated` reference (five places, undefined) a token that was meant to exist, and should the two un-fallbacked uses (4325, 4454) have a background?
4. Do the opacity-reduced text treatments (.6, .62, .65, .7) belong to the same family as a muted token, given four of them fail 4.5:1 in light?
5. Is the 600/640px split intentional (nav and taps at 640, layout at 600, JS chart bucketing at 640)?
6. Is the chart palette meant to be theme-aware (four of eight series are under 3:1 on light, `#555` "other" is 2.53 on dark)?
7. Spacing, radius (14 values, 4 literal pixel values used for the same card role), shadow and z-index have no scale; is #14's approach (named steps) meant to extend to those, or only type?
8. The eight chip/badge styles and five hand-written primary buttons: one component each, or are differences deliberate (e.g. outlined versus tinted for severity)?
9. Page titles: h1 is 1.91rem on five pages and 1.7rem on three, inline-styled; home and project have no h1. Intentional hierarchy?
10. Emails: the review email's look is determined by a prose prompt, so it varies run to run (6 fingerprints in 20 sends). Is a fixed template an option, or is variability accepted?
11. Should either email share the dashboard palette (health email red/green/amber differ from the dashboard's), and should the emails respect dark mode?
12. Machine voice: the review email is machine-written and unmarked, and the Ask answer is unmarked. Is the "↳ from claude" rule meant to cover them?
13. Desktop has no tap-target floor and a 24px gutter that does not shrink on phone. Is that a reading-width decision or an oversight?
14. Home-screen mode hides the Menu and shows five tabs; Visitors, Health and About sit under More. Is that discoverability acceptable for the admin's most-checked page (Health)?
15. #14 (PR #112) settles the type scale's mechanics, not its values: the 12 steps preserve today's sizes. Should the review change any step's value, or the number of steps?
16. `color-scheme` is not declared and `theme-color` is fixed `#111`: are native controls and the status bar meant to follow the app theme?
