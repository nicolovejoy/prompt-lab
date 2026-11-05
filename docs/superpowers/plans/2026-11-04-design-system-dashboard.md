# Design system, dashboard pass 1 (plan)

Spec: `docs/design-review/review.md` (rulings R1 to R19, all accepted 2026-11-04)
with measurements in `docs/design-review/facts.md`. This plan covers the dashboard
items that preserve the look: R1, R2, R3, R4, R5, R6, R7, R13, R15, R16, R17, R18 and
the error-banner part of R18. It does NOT cover R8, R9, R14 (mocks first) or R10, R11,
R12 (emails, separate plan).

Branch: `claude/design-system-1`, one PR at the end. Every task is one commit or a
few, on that branch.

## Global constraints (bind every task)

- The dashboard is ONE file, `web/index.html`, no build step. CSS tokens live in
  `:root` (dark, the default), with the light palette written TWICE: once inside
  `@media (prefers-color-scheme: light) { :root:not([data-theme]) {…} }` and once
  under `:root[data-theme="light"]`. Any token added or changed in one light block
  is added or changed identically in the other.
- Font sizes are already tokens (`--fs-*`); never write a raw font-size.
- Pure helpers live between `// <pure>` and `// </pure>` and must stay free of
  `window`, `document` and `html`. `node scripts/test_frontend_pure.mjs` lifts and
  tests that block, and also runs source-level guards over the whole file.
- The look is preserved unless the task says otherwise. "Preserved" means the
  rendered sizes, spacing and colours in DARK mode do not change except where a
  task names a value change; LIGHT mode changes only in the colours a task names.
- Tests: after every task run `node scripts/test_frontend_pure.mjs` (must pass) and
  `node scripts/phone/check.mjs` (must report 0 failed; it needs
  `scripts/phone/node_modules`, already installed, and writes screenshots to the
  gitignored `.playwright-mcp/phone/`). Never use a headed browser.
- Fixtures are synthetic (`scripts/phone/fixtures.mjs`); never read the real
  history DB; never commit screenshots. Screenshots for Nico go under
  `~/.claude/state/prompt-lab/design-review/after/` (outside the repo).
- Ruff is not involved (no Python in this plan) but if a `.py` is touched,
  `ruff check . --exclude .venv` must pass with ruff 0.15.22.
- Commit messages: imperative subject, a short body saying what changed visually
  (or "no visible change"), ending with the attribution line
  `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Do not touch `web/api/`, the emails, or any other file than `web/index.html`,
  `scripts/test_frontend_pure.mjs`, `scripts/phone/*.mjs` and
  `scripts/design-review/*` unless a task names it.

## Contrast reference (WCAG 2.x, computed 2026-11-04)

Light bg `#fafafa`, light card `#fff`, dark bg `#111`, dark card `#1a1a1a`.

- light green `#14743a`: 5.61 on bg, 5.85 on card; on its own 10% tint over white about 5.0.
- light yellow `#8a5a06`: 5.67 on bg, 5.92 on card; on tint about 5.2.
- dark muted `#9a9a9a`: 6.71 on bg, 6.19 on card. light muted `#5c5c5c`: 6.41 / 6.69.
- dark accent fill `#5558e6`: white on it 5.35; against bg 3.53 (UI floor is 3).
- dark link `#818cf8` (= today's dark accent-light): 6.33 on bg, 5.83 on card.
- light accent-light `#4338ca`: about 7.5 on bg.

---

## Task 1: Light status colours, `--bg-elevated`, smallest type step (R2, R3, R15)

File: `web/index.html`.

1. In BOTH light blocks change `--green: #16a34a` to `--green: #14743a` and
   `--yellow: #ca8a04` to `--yellow: #8a5a06`. Leave `--green-dim` and
   `--yellow-dim` as they are. Dark block unchanged.
2. Add `--bg-elevated` to the dark `:root` block with value `#222` (place it right
   after `--card-hover`), and to BOTH light blocks with value `#fff`. Add a one-line
   comment above the dark one: `/* raised surface inside a card: table header,
   note box */`.
3. Replace every `var(--bg-elevated, var(--card))` with `var(--bg-elevated)` (three
   inline styles, around lines 2819, 3024, 3398). The two bare uses (around 4338,
   4467) stay as they are.
4. Change `--fs-2xs: 0.61rem` to `--fs-2xs: 0.7rem`. Update the comment in
   `scripts/test_frontend_pure.mjs` only if it quotes the old value (it should not).
5. Run both test commands. Commit: "Light green and yellow pass as text; define
   --bg-elevated; smallest type step 11px".

Visible change: light-mode green/yellow text and badges darker; two formerly
transparent boxes (cost table header, project cost note) get the elevated
background; header meta text one pixel larger.

## Task 2: `--text-muted` replaces opacity-as-colour (R4)

File: `web/index.html`.

1. Add `--text-muted: #9a9a9a;` to the dark `:root` block after `--text-secondary`,
   and `--text-muted: #5c5c5c;` to BOTH light blocks in the same position.
2. Replace opacity-as-text-colour with the token. For each rule below, remove the
   `opacity` declaration and set `color: var(--text-muted)`:
   - the rule near line 290 (`opacity: 0.7; margin-right: 5px;`, header meta glyph)
   - `.header-user` (near 305, `opacity: 0.65`)
   - `.picker-caret` (near 328, `opacity: 0.7`)
   - the `max-width: 60ch` note near 461 (`opacity: 0.8`, heatmap note)
   - `.machine-mark` (near 723, `opacity: 0.6`)
   - `.dormant-chip.muted` (near 750, `opacity: 0.66`): set `color` and also
     `border-color: var(--border)`; remove opacity
   - `.is-private` (near 804, `opacity: 0.62`): same treatment as the dormant chip
   - inline `<span style="opacity: 0.7">` near 3804 and near 4321: replace the
     style with `color: var(--text-muted)`
   - the rule near 773 (`color: var(--accent-light); opacity: 0.8`): remove the
     opacity only; keep the colour (Task 4 retokens accent text).
3. Leave these opacities alone: disabled states (132, 702, 794), the spinner (316),
   heatmap cells (435-437), the 0.45 share bar (455), skeleton pulse (817-818),
   chart dimming (2465, 2737), the segment bars at 0.6 (2864, 3074, 3570, 4272).
4. Extend the font-size guard's neighbour in `scripts/test_frontend_pure.mjs` with a
   new test `opacity is not used as a text colour`: after stripping comments,
   assert that no CSS rule or inline style contains BOTH `color: var(--text` and
   an `opacity:` declaration in the same declaration block (split on `{…}` for
   CSS and on `style="…"` for inline). Keep it simple and document its limits in a
   comment.
5. Run both test commands. Commit: "--text-muted token replaces opacity on text".

Visible change: muted text is a hair lighter in dark and clearly darker in light;
otherwise none.

## Task 3: `color-scheme` and a theme-following `theme-color` (R16)

File: `web/index.html`.

1. Add `color-scheme: dark;` as the first declaration in the dark `:root` block
   and `color-scheme: light;` as the first declaration in BOTH light blocks.
2. Replace the single `<meta name="theme-color" content="#111">` with two:
   `<meta name="theme-color" content="#111" media="(prefers-color-scheme: dark)">`
   and `<meta name="theme-color" content="#fafafa" media="(prefers-color-scheme: light)">`.
3. In the head script, after a saved theme is applied, set BOTH metas' `content`
   to that theme's colour (`#111` for dark, `#fafafa` for light), so an explicit
   choice overrides the media match. Do the same where the toggle writes the theme
   (the function near line 1171 that calls `localStorage.setItem('promptlab_theme', …)`).
   Put the colour pair in one small object defined once in the head script, and
   have the toggle function read the metas and set them; do not duplicate the
   hex values a third time.
4. Run both test commands. Commit: "Native controls and the status bar follow the
   chosen theme".

Visible change: form controls and scrollbars match the theme; the home-screen
status bar is light over the light theme.

## Task 4: Semantic accent roles (R1)

File: `web/index.html`.

1. Tokens. Dark `:root`: change `--accent: #6366f1` to `--accent: #5558e6`; add
   `--link: #818cf8;` and `--on-accent: #fff;` after `--accent-light`. Both light
   blocks: keep `--accent: #4f46e5`; change `--accent-light: #6366f1` to
   `--accent-light: #4338ca`; add `--link: #4f46e5;` and `--on-accent: #fff;`.
   Comment above `--link` in the dark block: `/* accent-coloured text: links,
   "open day", inline actions. --accent is for fills and rings. */`
2. Text on accent fills: replace the colour in every rule or inline style that sets
   `color: #fff` or `color: white` on an accent background (near 116, 342, 459,
   685, 1531, 2209, 3673, 3824) with `color: var(--on-accent)`. The GitHub label
   chip (2209) keeps white on its hsl background but still uses the token.
3. Accent as text: every `color: var(--accent)` applied to TEXT (links, buttons
   without a fill, `.chart-open-day`, `.page-note-narrow summary`, Todos links,
   "details →") becomes `color: var(--link)`. `--accent` stays on backgrounds,
   borders, outlines, focus rings, heatmap cells and the KPI number colours if
   those use `--accent-light` (leave `--accent-light` text uses alone; the light
   value change in step 1 fixes their contrast).
4. Guard: in `scripts/test_frontend_pure.mjs` add a test that no `color:` (not
   `background`, not `border`) declaration uses `var(--accent)` and no `color:`
   declaration uses `#fff` or `white` (comments stripped). Also assert the two
   light blocks define `--link` and `--on-accent`.
5. Run both test commands. Commit: "--link and --on-accent roles; dark accent
   fill clears 4.5 with white text".

Visible change: dark accent fills a touch deeper; accent-coloured text in dark
is the lighter indigo already used for titles; light-mode titles slightly
deeper indigo.

## Task 5: Theme-aware chart palette (R6)

File: `web/index.html`, `scripts/test_frontend_pure.mjs`.

1. Tokens. Dark `:root`: `--chart-1: #6366f1; --chart-2: #22c55e; --chart-3: #eab308;
   --chart-4: #ef4444; --chart-5: #06b6d4; --chart-6: #ec4899; --chart-7: #f97316;
   --chart-8: #a855f7; --chart-other: #777;`. BOTH light blocks: `--chart-1: #4f46e5;
   --chart-2: #15803d; --chart-3: #a16207; --chart-4: #dc2626; --chart-5: #0e7490;
   --chart-6: #be185d; --chart-7: #c2410c; --chart-8: #7e22ce; --chart-other: #6b6b6b;`.
   Comment above the dark set: `/* chart series: order is rank order; light values
   are darkened so every band clears 3:1 on #fafafa */`.
2. Inside the pure block, `COST_PALETTE` becomes
   `['var(--chart-1)', …, 'var(--chart-8)']` and `COST_OTHER` becomes
   `'var(--chart-other)'`. These are plain strings, so the pure block stays pure.
   Every consumer already drops the value into a CSS `background:` or inline style,
   which accepts `var()`. Check each use site (segColor callers, legends, readout
   swatches, by-project list dots) and confirm none parses the string as a hex
   (search for `substring`, `slice`, `parseInt`, `rgba(` applied to a palette
   value). If one does, convert that site to use `opacity` instead and say so in
   the report.
3. The page-views sparkline (`color: '#06b6d4'` near 1677) becomes
   `color: 'var(--chart-5)'`. Check how `Spark` applies `color` (SVG `stroke`/`fill`
   attributes accept `var()` in every current browser; a `<linearGradient>` stop
   also does). If a gradient uses `stop-opacity`, nothing changes.
4. Tests: in `scripts/test_frontend_pure.mjs`, if a test asserts the palette's
   literal hex values, update it to the `var()` strings. Add a guard: no
   `#06b6d4`, `#6366f1`, `#22c55e`, `#eab308`, `#ef4444`, `#ec4899`, `#f97316`,
   `#a855f7` or `#555` literal outside the `:root` token blocks (comments
   stripped). Add an assertion that both light blocks define `--chart-1` to
   `--chart-8` and `--chart-other`.
5. Run both test commands. Also look at `.playwright-mcp/phone/costs-phone.png`
   (produced by the phone check) and confirm the bars are coloured, not black or
   transparent. Commit: "Chart palette through theme tokens".

Visible change: dark unchanged except "other" grey lighter; light-mode chart
bands darker.

## Task 6: Contrast and light-block guards (R17 and the contrast half of R2)

File: `scripts/test_frontend_pure.mjs` only.

1. Add a helper that extracts the three token blocks from the source as
   `{dark, lightMedia, lightExplicit}` maps of `--name` to value, by locating
   `:root {`, `:root:not([data-theme]) {` and `:root[data-theme="light"] {` and
   reading to the matching `}`.
2. Test `light palette is written identically in both places`: every key present
   in either light map is present in both with the same value.
3. Test `every light token has a dark definition`: the set of `--` names in the
   light map is a subset of the dark map's (fonts and layout tokens live only in
   dark, that is fine).
4. Add a small WCAG relative-luminance contrast function (hex in, ratio out; 3- and
   6-digit hex; ignore rgba tokens). Test `text tokens pass 4.5:1 on bg and card`
   for both themes over: `--text`, `--text-secondary`, `--text-muted`, `--link`,
   `--green`, `--yellow`, `--red`. Test `--on-accent on --accent passes 4.5:1` for
   both themes. Test `chart tokens pass 3:1 on bg` for `--chart-1`..`--chart-8` and
   `--chart-other` in both themes.
5. Run `node scripts/test_frontend_pure.mjs`. If a contrast test fails, do NOT
   change a token: report the failing pair and ratio as a concern (the token tasks
   chose the values; a miss is for the controller to rule on). Commit: "Guards:
   light blocks match; token contrast".

## Task 7: Radius, shadow and z-index tokens (R7, part 1)

File: `web/index.html`, `scripts/test_frontend_pure.mjs`.

1. Tokens in the dark `:root` only (theme-independent, like `--fs-*`):
   `--r-sm: 4px; --r-md: 6px; --r-lg: 8px; --r-pill: 999px;` keep `--radius: 8px`
   as is for now but add a comment `/* alias of --r-lg; retire after the spacing
   pass */`. `--shadow-pop: 0 8px 28px rgba(0,0,0,.3); --shadow-modal: 0 20px 60px
   rgba(0,0,0,.4); --shadow-tip: 0 4px 16px rgba(0,0,0,.4);`.
   `--z-tip: 5; --z-dropdown: 40; --z-bar: 50; --z-modal: 100;`.
2. `border-radius` migration: every `border-radius` value becomes a token:
   2px and 3px → `--r-sm` (a 1-2px change on tiny chips and swatches; accepted by
   R7), 4px → `--r-sm`, 5px/6px/7px → `--r-md`, 8px/9px/10px and `var(--radius)`
   → `--r-lg`, 12px and larger non-pill values → `--r-lg` (list them in the
   report), 50%/999px/104px/44px-circles → `--r-pill` where the element is a pill
   or circle (an element with equal width and height may use `50%`; keep `50%` in
   that case and note it). Compound values like `8px 8px 0 0` use the token in
   each slot.
3. `box-shadow` migration: the five literals map to the three shadow tokens by
   size (the 0.28 one is `--shadow-pop`, the two 30/40 ones at 334 and 688 are
   `--shadow-pop` and `--shadow-modal`, the two 4/16 ones are `--shadow-tip`).
4. `z-index` migration: 5 → `--z-tip`, 40 → `--z-dropdown`, 50 → `--z-bar`, 100 →
   `--z-modal`.
5. Guards in `scripts/test_frontend_pure.mjs`: no `border-radius` with a raw
   value other than `50%`; no `box-shadow` with a raw `rgba`; no `z-index` with a
   raw number. Comments stripped; the `:root` block excluded, as the font-size
   guard does.
6. Run both test commands. Commit: "Radius, shadow and z-index tokens".

Visible change: 2px and 3px corners become 4px; a few 5/7/9/10px corners move
by 1-2px. Nothing else.

## Task 8: Spacing tokens (R7, part 2)

File: `web/index.html`, `scripts/test_frontend_pure.mjs`.

1. Tokens in the dark `:root`: `--sp-1: 4px; --sp-2: 8px; --sp-3: 12px; --sp-4:
   16px; --sp-5: 24px; --sp-6: 32px;` with the comment `/* spacing scale; 2, 6,
   10, 14, 20px stay raw until a later fold */`.
2. Replace every `padding`, `margin`, `gap`, `row-gap`, `column-gap`, `top`,
   `right`, `bottom`, `left` and `inset` value that is EXACTLY 4, 8, 12, 16, 24 or
   32px with the token, in CSS and in inline styles, including inside shorthands
   (`padding: 12px 16px` → `padding: var(--sp-3) var(--sp-4)`; `margin: 0 auto`
   untouched; `padding: 8px 14px` → `padding: var(--sp-2) 14px`). Negative values
   (`-4px`) become `calc(-1 * var(--sp-1))` only if there are fewer than five; if
   more, leave negatives raw and say so. Values with `calc()` or `env()` already
   (safe-area paddings) stay as they are.
3. Do not touch `width`, `height`, `min-height`, `min-width`, `max-width`,
   `font-size`, `line-height`, `letter-spacing`, `border-width`, chart cell sizes
   (8px cells, 44px chips) or SVG attributes.
4. Guard: no raw `4px|8px|12px|16px|24px|32px` token inside a `padding`, `margin`,
   `gap`, `row-gap` or `column-gap` declaration outside `:root` (comments
   stripped). Write the regex so `14px` and `48px` do not match.
5. Run both test commands. Commit: "Spacing tokens, sizes preserved".

Visible change: none.

## Task 9: One breakpoint, phone gutter, desktop control height (R5, R13)

File: `web/index.html`, `scripts/phone/checks.mjs` (only if a check needs the new
gutter value).

1. Add `/* Breakpoint: 640px. Nav, taps, layout and the JS chart bucketing all
   switch here. */` above the first media query and change every
   `@media (max-width: 600px)` to `@media (max-width: 640px)`. `min-width: 601px`
   (if any) becomes `min-width: 641px`. The project page's 800px single-column
   rule stays.
2. In the 640px block, `.container` side padding becomes 16px (both sides).
3. Desktop control height: add `min-height: 32px` to `.header-btn`, `.win-btn`,
   `.sub-tab`, `.theme-btn`, `.ask-btn`, `.uptime-toggle`, `.review-expand` and
   `.chart-open-day` in the base (non-media) CSS. The 44px phone rules override
   below the breakpoint as today.
4. Run both test commands. If the phone check's horizontal-overflow or header
   one-line assertions fail at the new gutter, fix the layout (not the check).
   Commit: "One breakpoint; 16px phone gutter; 32px desktop controls".

Visible change: 16px side gutter on phones; desktop buttons up to 4px taller.

## Task 10: Accessibility pass (R18)

File: `web/index.html`, `scripts/phone/checks.mjs` (may add a check).

1. Live regions: the shared loading, error and "saved" containers (`.loading`,
   `.error`, `SkeletonList`'s wrapper, the metadata editor's saved state) get
   `aria-live="polite"` on a wrapper that exists before the content changes.
2. Landmarks: the header's wide nav and the phone dropdown list become `<nav
   aria-label="Primary">`; the existing tab bar keeps "Sections". `<main>` wraps the
   routed page content if it does not already.
3. Charts: `StackedBars`' outer element gets `role="img"` and an `aria-label` built
   from the heading and the totals already computed for the readout (e.g. "Prompts
   per day, last 30 days, 930 total"). The heatmap grid, uptime strips and `Spark`
   get `role="img"` with a short label from data already at hand. Interactive
   charts keep their buttons focusable: `role="img"` goes on a sibling summary or
   on the non-interactive part, never on an element containing buttons.
4. Reduced motion: the existing `@media (prefers-reduced-motion: reduce)` block
   covers every `animation` and `transition` in the file (skeleton pulse, spin,
   max-height, timeline hover, chart opacity).
5. Keyboard: every `onClick` on a `<div>` or `<span>`, and every `<a>` without an
   `href`, either becomes a `<button type="button">` with the same classes (keep
   the look by resetting button defaults in the class) or gains `role="button"`,
   `tabindex="0"` and an `onKeyDown` for Enter and Space that calls the same
   handler. Prefer `<button>`. The logo link gets `href="#/"`. List each converted
   element in the report.
6. Error banners: the health page `banner()` helper and `.error` render text in
   `var(--text)` on the tinted background with a 3px left border in the severity
   colour; the severity colour is no longer the text colour. The up/down status
   chips (near 3749, 3790, 3905) keep their colours (they pass after Task 1).
7. Add a phone check (in `scripts/phone/checks.mjs`, same style as the 44px one)
   that every element with `onclick` behaviour is a `button`, `a[href]`, `select`,
   `input` or has `role="button"` with `tabindex="0"`, if the runner can express
   that cheaply; otherwise skip and say so.
8. Run both test commands. Commit: "Accessibility: live regions, landmarks, chart
   labels, keyboard, reduced motion; error banners in text colour".

Visible change: error and health banners show black/white text with a coloured
left border instead of coloured text.

## Task 11: After screenshots for Nico

Files: new `scripts/design-review/shots.mjs` (committed), output outside the repo.

1. Write a runner, modelled on `scripts/phone/check.mjs` (reuse its server, fixture
   stubbing and device profiles; import rather than copy where the file exports
   them, otherwise copy the minimum), that loads `#/`, `#/costs`, `#/health`,
   `#/project/alpha-app`, `#/activity`, `#/visitors`, `#/todos` and the login
   screen in four combinations: desktop (Edge 1280, `channel: 'msedge'`) and phone
   (WebKit iPhone 14), each in `colorScheme: 'dark'` and `'light'`, headless. It
   writes `<route>-<profile>-<scheme>.png` full-page to a directory given as the
   first argument.
2. Run it with output `~/.claude/state/prompt-lab/design-review/after/`. The
   "before" set already exists in `~/.claude/state/prompt-lab/design-review/dashboard/`
   with the same naming.
3. Also write `~/.claude/state/prompt-lab/design-review/after/README.md` listing
   the task-by-task visible changes (copy the "Visible change" lines from this
   plan) so Nico can compare before and after by name.
4. Commit the script only: "Design-review screenshot runner".
