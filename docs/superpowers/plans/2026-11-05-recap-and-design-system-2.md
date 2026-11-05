# Plan: `recap` shell command, and design system pass 2 (R8, R9, R14)

Date: 2026-11-05. Spec: `docs/design-review/review.md` (rulings R8, R9, R14) plus
the decisions below, made by Nico on 2026-11-05 after seeing the mocks in
`~/.claude/state/prompt-lab/design-review/mocks/` (r8-chips-buttons, r9-page-titles,
r14-tab-bar; dark and light). The mock HTML files there carry the exact proposed
CSS for `.chip`, `.btn` and `.page-title`; read them.

## Decisions (Nico, 2026-11-05)

- D1. `recap`: one shell command that prints, for each repo with a summarised
  session in the last N days, the newest session's "Next:" clause. Local DB only,
  no network, no model call. ~200 words max total.
- D2. R8 chips: one `.chip` with `.chip-outlined`, `.chip-tinted`, `.chip-filled`
  and severity classes (`.sev-ok`, `.sev-warn`, `.sev-bad`, `.sev-info`) for tinted.
- D3. The private badge keeps a stronger border than other outlined chips (border
  `var(--text-secondary)`), so privacy still stands out. Upper case may go.
- D4. GitHub label chips become `.chip-outlined` with an 8px coloured dot in the
  label's hue; text is the normal chip text colour (fixes white-on-hue contrast).
- D5. Project (dormant) chips on Home shrink to the chip size; phone keeps 44px taps.
- D6. One `.btn` (`.btn-primary`, `.btn-ghost`). Re-poll is `.btn-ghost`. The login
  page keeps a LARGER primary button (Nico: "agreed on bigger login button too") —
  a `.btn-lg` size modifier used only on the login page.
- D7. R9: one `.page-title` (`--fs-3xl`) on all eight pages including Day; the
  project name is the project page's `<h1>`; home gets a visually hidden `<h1>`
  "Prompt Lab"; `.section-label` elements become `<h2>` with an unchanged look.
- D8. R14: role-aware tab bar. Admin: Home, Activity, Health, Costs, More.
  Reader: Home, Activity, Todos, Costs, More (unchanged). No problem dot on Health.

## Global constraints

- `web/index.html` is one file, no build step. Pure helpers live between
  `// <pure>` and `// </pure>` and are tested by `node scripts/test_frontend_pure.mjs`
  (keep that block free of `window`, `document`, `html`).
- Tests are standalone runners, not pytest: `for f in scripts/test_*.py; do .venv/bin/python "$f"; done`.
- Phone layout check: `node scripts/phone/check.mjs` (headless; Playwright already
  installed under `scripts/phone`). It must end with 0 failed. Fixtures are synthetic.
- Use existing tokens only (`--sp-*`, `--r-*`, `--fs-*`, colour tokens). CI guards
  reject raw font sizes; check `.github/workflows/test.yml` for the guard scripts and run them.
- Phone (<=640px): every tap target >= 44px tall. Desktop controls >= 32px.
- No real data in tests or fixtures. No test touches `~/.claude/prompt-history.db`.
- Browsers run headless, Edge channel for desktop. Never headed.
- Calendar days shown to a human are America/Los_Angeles; DB timestamps are UTC.

## Task 1: `recap` command

Files: create `workflow/bin/recap.py`, create `scripts/test_recap.py`, edit
`workflow/shell/work.zsh`, edit `.github/workflows/test.yml` (add the test to the CI list
the same way the other `scripts/test_*.py` are listed).

`recap.py` (python3 stdlib only, executable, `#!/usr/bin/env python3`):
- DB path: env `PROMPT_HISTORY_DB`, else `~/.claude/prompt-history.db`. Open read-only
  (`file:...?mode=ro` URI). Missing DB → one-line message on stderr, exit 1.
- Usage: `recap [DAYS] [PROJECT]`, both optional, any order (an all-digit arg is DAYS).
  Default DAYS = 7.
- Rows: `sessions` with non-empty `summary`, time = `COALESCE(ended_at, started_at)`
  (UTC text `YYYY-MM-DD HH:MM:SS`), within the last DAYS days. Exclude project `scratch`.
- Default mode: newest session per project, projects ordered newest first, at most 8.
  PROJECT mode: that project's newest 3 sessions.
- Line text: if the summary contains `Next:`, the text after the first `Next:`;
  else the summary's first sentence. Collapse whitespace. Truncate to fit the
  terminal width (`shutil.get_terminal_size((100, 20)).columns`), ending in `…`.
- Line format: `<project padded to longest name>  <MM-DD Pacific>  <text>`. Date is
  the row time converted UTC → America/Los_Angeles (`zoneinfo`).
- Nothing found → `no summarised sessions in the last N days`.
- The script must cap total output at ~200 words: with 8 lines of terminal width
  this holds; do not add headers or footers beyond that.

`work.zsh`: add a `recap()` function that runs `~/.claude/bin/recap.py "$@"`, with a
short comment block in the file's style, and mention it in the header USE section.
No `.zshrc` change: work.zsh is already sourced.

`scripts/test_recap.py`: standalone runner in the style of the other tests
(`check(name, cond)` and exit code). Build a temp SQLite DB with a minimal `sessions`
table (id, project, started_at, ended_at, summary) and synthetic rows; run the script
via subprocess with `PROMPT_HISTORY_DB` and `COLUMNS=100`. Cover: Next extraction,
first-sentence fallback, newest-per-project and ordering, DAYS window, PROJECT mode,
scratch excluded, Pacific date (a row at 2026-11-05 03:00 UTC shows 11-04),
truncation with `…`, empty result message, missing DB exit 1.

## Task 2: R8 chips (D2–D5)

File: `web/index.html` only (plus `scripts/phone/checks.mjs` if a selector breaks).
Add `.chip` CSS per the mock (`r8-chips-buttons-dark.html`). Migrate `.tag`, `.badge`,
`.badge-private`, `.status-badge` + `.status-*`, `.dormant-chip` (+ `.muted`,
`.is-private`), `.project-link`, `.ask-example`, and the inline GitHub label chips
(see `labelColor`) to `.chip` + modifiers, then delete the old CSS rules that no
longer have users. Keep each element's `data-test` attributes and behaviour.
`.chart-day-chip` stays as is (it is a segmented control, not a chip). Keep the
monospace font on project links (a modifier or a narrow rule). Private: D3.
Labels: D4. Hover states for link chips as in the mock. Phone check and pure tests pass.

## Task 3: R8 buttons (D6)

File: `web/index.html`. Add `.btn`, `.btn-primary`, `.btn-ghost`, `.btn-lg` (login).
Replace the five hand-written primary looks (login button, ask button, Retry, the
health re-poll, and the remaining accent-filled button found by grepping
`background: var(--accent)` on buttons) with these classes, removing the inline styles
and orphaned rules. Re-poll uses `.btn-ghost`. Login keeps full width and the larger
size via `.btn-lg` (keep today's `--fs-lg`, 600 weight). Segmented controls
(`.sub-tab`, `.win-btn`, `.tab`, header buttons) are out of scope. Desktop min-height
32px holds; phone 44px holds.

## Task 4: R9 page titles (D7)

File: `web/index.html`. Add `.page-title` and a visually-hidden utility if none exists.
Replace the eight inline-styled `<h1>`s (Todos, Costs, Activity, Visitors, Health,
More, About, Day) with `class="page-title"`, keeping each one's margin needs via the
class (one margin; adjust surrounding spacing only if a page visibly breaks). Project
page: the project name becomes `<h1 class="page-title">`. Home: visually hidden
`<h1>Prompt Lab</h1>`. Every `.section-label` element becomes `<h2 class="section-label">`
with the same look (reset h2 margins/size in CSS). Phone check passes at 390px with
no horizontal overflow.

## Task 5: R14 role-aware tab bar (D8)

Files: `web/index.html`, `scripts/phone/checks.mjs`, `scripts/test_frontend_pure.mjs`
if the logic moves into the pure block. Make the tab list a function of role
(e.g. `tabsFor(role)` in the pure block, with `currentTab(view, role)`), so the admin
bar is Home, Activity, Health, Costs, More and the reader bar is unchanged. For the
admin, `todos` is reached from More and highlights More; `health` highlights Health.
For the reader, current behaviour is unchanged. `MoreView` lists what the bar does not
name for that role. Pass `role` to `TabBar`. Update the phone checks' expected tabs per
role and add a check for the admin bar (the check runner already has role fixtures;
read it). Unit-test `tabsFor`/`currentTab` for both roles.

## Task 6: docs

Files: `docs/design-review/review.md` (append "Decisions on the mocks (Nico,
2026-11-05)" with D2–D8 in one line each, and update the Status section),
`docs/current-work.md` (replace the "Still to do… mocks for R8…" line with this
branch's status; R10–R12 emails remain as their own plan), `CLAUDE.md` only if a
convention changed (it shouldn't). Do not mention `recap` anywhere but work.zsh and
current-work.md.
