# Design review: prompt-labs.org and its emails (2026-11-04)

Companion to `facts.md` (measurements). This file holds the review's findings and
the rulings Nico makes on them. Rulings are numbered so they can be answered by
number; each one records the decision once made. Scope is the dashboard
(`web/index.html`) and the two emails; the other sites are out of scope, though a
shared-learnings doc may follow.

Measured against `main` at `eee9ee1`, i.e. after #112 (the 12-step type scale)
merged. Post-merge count: 229 `font-size` declarations, 228 through `var(--fs-*)`,
the one remainder is a comment. No raw `rem`, `px` or `em` font sizes remain.

## What is working

- The type scale is done and guarded. #14's problem (38 values, near-duplicates
  from a uniform bump) is closed at the mechanism level.
- The colour tokens are the right set and the right size: 15 colours, two
  themes, 442 references. Nobody invents new greys.
- One chart (`StackedBars`) serves five pages; `WindowPicker` and `PageNote` were
  consolidated after drifting. The pattern of noticing drift and folding it back
  is the system's actual design process, and it works.
- Phone discipline is real: 44px targets enforced by a 404-check runner, one-line
  header, home-screen tab bar, no service worker on purpose.
- The dark theme reads well. Contrast on text and secondary text is very high
  (12 to 15:1); the 2026-07 readability fix stuck.
- The machine-voice mark is a genuinely good convention and is consistently
  applied on the dashboard.
- Both emails are structurally right: the health email leads with problems and
  age; the review email reads as a record for the engineer.

## Where the system is thin

The dashboard has a palette and a type scale and almost nothing else. Everything
below the token layer is hand-written at the call site: eight chip styles, five
hand-rolled primary buttons, fourteen radius values, four chevron treatments,
inline `<h1>` styles per page. None of it looks wrong in a screenshot, because
one person wrote it all with the same eye. It costs at edit time: every new box
re-decides padding, radius and border, and every new status colour re-decides
whether it is text-safe. The review's main recommendation is therefore not a
restyle. It is to extend #14's method (named tokens, sizes preserved, a CI guard)
to the next three layers: semantic colour roles, spacing and radius, and a small
component vocabulary. Visual change from all of it should be near zero.

The one place the current state is wrong, not just thin, is light-theme
contrast. Green and yellow fail as text (3.16, 2.81), four opacity-muted
treatments fail, the status badges fail, and four of the eight chart series are
under 3:1 on the light background. Dark has two near-misses (accent text 4.23,
white on accent 4.47). Light mode is the one Nico's phone picks in daylight.

The emails share nothing with the dashboard and nothing with each other. The
health email is a fixed string template with its own three colours; the review
email's HTML is generated fresh by the model each night and has shown six
different fingerprints in twenty sends.

## Rulings

Each item: the finding, the recommendation, then a `Decision:` line that stays
blank until Nico answers. Recommended answers are first.

### R1. Accent as text, and text on accent

Finding: `--accent` (#6366f1) is used for links and small buttons in dark at
4.23:1 on bg, 3.90 on card. White on accent fills is 4.47. Both miss 4.5.

Recommend: two semantic tokens. `--link` (dark: `--accent-light` #818cf8, 6.33;
light: `--accent` #4f46e5, 6.02) for any accent-coloured text; `--on-accent`
(#fff) replacing the four `#fff` and four `white` literals. Nudge the dark accent
fill one step darker (around #5558e6) so white on it clears 4.5; verify the
number at implementation. Accent itself stays for fills, rings and chart series.

Decision: yes, as recommended (Nico, 2026-11-04).

### R2. Light-theme green and yellow as text

Finding: light `--green` #16a34a is 3.16 on bg, `--yellow` #ca8a04 is 2.81. Both
carry small uppercase status text (fresh, active, stalled, health banners).

Recommend: darken the light solid tokens only (green to about #15803d, yellow to
about #a16207; both clear 4.5 on #fafafa and #fff), leave the `-dim` fills
alone. Status badges then pass too. Dark values are unchanged. One-line change
in each of the two light blocks; no new token.

Decision: yes, as recommended (Nico, 2026-11-04).

### R3. `--bg-elevated`

Finding: referenced five times, defined nowhere. Three fall back to `--card`;
two (cost table header, project cost box) resolve to transparent.

Recommend: define it (dark #222, the existing `--card-hover` value; light #fff)
and drop the inline fallbacks. The alternative, replacing all five with
`--card`, loses the distinction the author was reaching for.

Decision: yes, as recommended (Nico, 2026-11-04).

### R4. Opacity as a colour

Finding: 26 `opacity` declarations produce effective text colours outside the
token set. Four of them fail 4.5 in light (`.header-user` 3.73, `.machine-mark`
3.31, `.nav-build-label` 4.23, private/dormant chips about 3.8).

Recommend: one `--text-muted` token (dark about #9a9a9a, light about #5c5c5c,
both over 6:1) and replace the text-opacity uses with it. Opacity stays for
genuinely transparent things (disabled states, heatmap cells, chart dimming).

Decision: yes, as recommended (Nico, 2026-11-04).

### R5. The 600/640 breakpoint split

Finding: nav and tap targets switch at 640px, layout at 600px, chart bucketing
in JS at 640px. A 601 to 640px viewport gets phone nav with desktop layout.

Recommend: one breakpoint at 640px, written once as a comment-documented
constant, and the `max-width: 600px` rules moved to it. The phone check runs at
390px so nothing it guards changes.

Decision: yes, as recommended (Nico, 2026-11-04).

### R6. Chart palette

Finding: `COST_PALETTE` is eight hard-coded dark-theme hexes, used in both
themes. On light, green 2.18, yellow 1.84, cyan 2.33, orange 2.69 are under the
3:1 graphics floor. `#555` "other" is 2.53 on dark. `#06b6d4` is also inlined on
the page-views sparkline.

Recommend: eight `--chart-1` to `--chart-8` tokens plus `--chart-other`, with
darkened light-theme values, read by the chart code at render time. Dark values
stay as they are. Its own PR, because it touches the pure helpers and the
frontend test.

Decision: yes, as recommended (Nico, 2026-11-04).

### R7. Spacing, radius, shadow, z-index

Finding: no scale for any of them. Radius alone uses 4, 6, 8 and `--radius`
(8px) for the same card role. Shadows are six `rgba(0,0,0,.x)` literals.

Recommend: extend #14's method in two steps. First, radius (`--r-sm` 4,
`--r-md` 6, `--r-lg` 8, folding 3 into 4 and 5/7/9 into their neighbours) and
shadow (`--shadow-card`, `--shadow-overlay`), with a CI guard like the font-size
one. Second, spacing (4/8/12/16/24/32 as `--sp-1` to `--sp-6`), which is a larger
mechanical edit. z-index: four named layers (base, sticky header, dropdown,
overlay). Sizes preserved throughout.

Decision: yes, as recommended (Nico, 2026-11-04).

### R8. Chips, badges and buttons

Finding: eight chip styles; eleven button classes plus five inline primary
buttons with five different paddings and four font sizes.

Recommend: one `.chip` with three modifiers (outlined, tinted, filled) and the
colour chosen by a severity class, replacing the eight. One `.btn` with
`.btn-primary` and `.btn-ghost`, replacing the inline primaries. Sub-tabs,
window picker and the tab bar keep their own classes because they are
segmented controls, not buttons. Expect small visible deltas (a chip gaining or
losing 1px of padding); accept them.

Decision: yes, as recommended (Nico, 2026-11-04).

### R9. Page titles and headings

Finding: five pages use an inline-styled `<h1>` at 3xl, three at 2xl; home and
project have no `<h1>` at all, using styled divs. No `<h3>` anywhere.

Recommend: one `.page-title` class at `--fs-3xl` for all eight; the project
name becomes the project page's `<h1>`; home gets a visually hidden `<h1>`
"Prompt Lab". Section labels (`.section-label`) become `<h2>` with the same look.
Cosmetic change only on the three 2xl pages (More, About, Day), which grow one
step.

Decision: yes, as recommended (Nico, 2026-11-04).

### R10. Review email: fixed template

Finding: the model returns finished HTML guided by a prose style spec. Twenty
sends show six fingerprints (font stacks, first colours, fragment vs. full
document). The email cannot carry a machine-voice mark, a dark-mode rule or a
shared palette because its markup is not ours.

Recommend: the model returns structured content only (subject, headline,
sections as lists of paragraphs) through the existing tool schema, and
`send-review.py` renders it with a shared Python email module. The look becomes
fixed and testable, and the mock in the screenshot folder becomes a real
rendering. This is the largest item in the review; it changes the prompt and
the tool schema, so the first few nights need a read.

Decision: yes, as recommended (Nico, 2026-11-04).

### R11. Shared email palette, and dark mode

Finding: the health email's red/amber/green (#c62828/#b26a00/#2e7d32) match
nothing on the dashboard; neither email declares `color-scheme`; the review
email paints a light page, the health email paints none.

Recommend: one `web/api/email_style.py` (or `email_style` in a shared module
both scripts import) holding the light-theme text-safe values from R2 plus
text/muted/border, used by both emails and by the pause and sign-in-failure
pages. Dark mode: declare `color-scheme: light` and stay light. Dark email
rendering differs across Mail, Gmail and iOS enough that a light-only email with
a declared scheme is the predictable choice; revisit if a dark-mode complaint
ever appears.

Decision: yes, as recommended (Nico, 2026-11-04).

### R12. Machine voice in emails and in Ask

Finding: the review email and the Ask answer are model-written and unmarked; the
dashboard rule says AI-authored text carries "↳ from claude".

Recommend: apply the rule. The review email's footer gains the mark (natural once
R10 lands); the Ask answer renders through `MachineText`. The health email's joke
line is one sentence and already italic; mark it too, for consistency, or leave
it as the one exception. Recommend marking it.

Decision: yes, as recommended (Nico, 2026-11-04).

### R13. Phone gutter and desktop tap floor

Finding: `.container` keeps 24px side padding on a 390px phone (the artifact
convention in this repo says 16px). Desktop has no minimum control height;
several buttons are about 28px tall.

Recommend: 16px gutter below the breakpoint; a 32px `min-height` on `.btn`,
`.win-btn` and `.sub-tab` on desktop. Both small.

Decision: yes, as recommended (Nico, 2026-11-04).

### R14. Home-screen tab bar contents

Finding: the standalone tab bar is Home, Activity, Todos, Costs, More for both
roles; Health, Visitors and About sit behind More. Health is the admin's
most-checked page.

Recommend: a role-aware bar. Admin: Home, Activity, Health, Costs, More. Reader:
unchanged. Todos moves to More for the admin, where it is one tap further.
Alternative is to leave it, since the health email already carries the alarm;
the page is for drilling in, not for noticing.

Decision: yes, as recommended (Nico, 2026-11-04).

### R15. Type scale values

Finding: #112 preserved every size. Three steps sit within 18% of each other
(`body-sm` .95, `body` 1.06, `md` 1.12) and `2xs` is 9.8px.

Recommend: raise `--fs-2xs` from .61 to .7rem (11px) now; it is two uses, both
header meta. Leave the twelve steps as they are until R7's spacing pass, then
look at folding `md` into `body` with the sizes in front of us. Do not change
the step count in this review.

Decision: yes, as recommended (Nico, 2026-11-04).

### R16. `color-scheme` and `theme-color`

Finding: no `color-scheme` property, so native selects, scrollbars and the
preview-password input follow the OS rather than the chosen theme.
`theme-color` is fixed `#111`, so the status bar is dark over a light page in
home-screen mode.

Recommend: `color-scheme: dark` on `:root`, `light` in both light blocks; two
`theme-color` metas with `media="(prefers-color-scheme: …)"`, and the head
script that sets `data-theme` also rewrites the active one. Trivial.

Decision: yes, as recommended (Nico, 2026-11-04).

### R17. Light block duplication

Finding: the light palette is written twice (OS preference and explicit choice)
and must be edited in step. R2 adds another paired edit.

Recommend: keep the duplication (CSS offers no clean single-source form here)
and add a frontend test that parses both blocks and asserts they are identical.
The guard is cheaper than the refactor.

Decision: yes, as recommended (Nico, 2026-11-04).

### R18. Accessibility pass (one PR, no visual change)

Finding: no `aria-live` region for loading, error or saved states; the header
nav is not a `<nav>`; charts have no text alternative; the reduced-motion query
covers two animations of about seven; clickable divs and anchors without `href`
carry no role or tabindex.

Recommend: one pass. `aria-live="polite"` on the shared loading/error/saved
containers; `<nav aria-label="Primary">` on the header nav; `role="img"` with
an `aria-label` summarising each chart (the readout text already exists);
reduced-motion covering every transition; `role="button"` and `tabindex="0"`
with an Enter/Space handler on the clickable divs, or turning them into
`<button>`s. The red-on-red-dim error banner (4.33 dark, 3.98 light) moves to
`--text` on the tinted background with a red left border.

Decision: yes, as recommended (Nico, 2026-11-04).

### R19. Order of work

Recommend, if the rulings land roughly as proposed:

1. Contrast fixes with no new structure: R2, R3, R4, R16, R15's 2xs change, the
   error banner from R18. One PR, visible change small, light mode passes.
2. R1, R6 (semantic colour roles and chart tokens). One PR each.
3. R7 radius and shadow, then spacing. One PR each, each with a guard.
4. R8, R9, R13, R5 (components and breakpoints). One PR.
5. R18 accessibility. One PR.
6. R10, R11, R12 (emails). Email module first, health email on it, then the
   review email's schema change.
7. R14 and R17 wherever they fit.

Each PR gets the phone check and the frontend pure tests; a before/after
screenshot pair goes in the state folder, never the repo.

Decision: yes, as recommended (Nico, 2026-11-04).

### Mocks vs build (Nico, 2026-11-04)

Build first. Token and scale work preserves the look, so each PR ships with
before/after screenshots (synthetic data, state folder) instead of mocks. Mocks
are made only for the four items whose look changes: R8 (chips and buttons),
R9 (page titles), R10 (review email template) and R14 (admin tab bar). One
synthetic screenshot of the proposed look each, Nico picks, then build.

### Status (2026-11-04)

R1–R7, R13, R15–R18: built on branch `claude/design-system-1`, PR #113. R8, R9, R14: mocks made, decided below. R10–R12: separate plan.

### Decisions on the mocks (Nico, 2026-11-05)

- D2. R8 chips: one `.chip` with `.chip-outlined`, `.chip-tinted`, `.chip-filled`; tinted chips take `.sev-ok`, `.sev-warn`, `.sev-bad` or `.sev-info`.
- D3. The private badge keeps a stronger border than other outlined chips. Upper case was dropped on outlined chips (tinted status chips keep it).
- D4. GitHub label chips are outlined with an 8px dot in the label's hue; text uses the normal chip colour.
- D5. Dormant project chips on Home shrink to the chip size; the phone keeps 44px tap targets.
- D6. One `.btn` (`.btn-primary`, `.btn-ghost`). Re-poll is ghost. The login page keeps a larger primary button (`.btn-lg`, login only). The Google sign-in button keeps its outlined look at that size.
- D7. R9: one `.page-title` on all eight pages including Day. The project name is the project page's `<h1>`; Home gets a visually hidden `<h1>` "Prompt Lab"; section labels become `<h2>` with the same look. Cost detail and the login screen also got an `<h1>`.
- D8. R14: role-aware tab bar. Admin: Home, Activity, Health, Costs, More. Reader: Home, Activity, Todos, Costs, More (unchanged). No problem dot on Health.

### Status (2026-11-05)

R8, R9 and R14 are built on branch `claude/recap-and-design-system-2` (open as a PR). R10–R12 (emails): separate plan.
