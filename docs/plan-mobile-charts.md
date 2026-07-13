# Plan: mobile pass for #/visitors (#21) and #/costs (#22)

**For the next session (Sonnet).** Scope: `web/index.html` only, the `VisitorsOverview` and `CostsOverview` components. One branch, one PR, `Closes #21, Closes #22`.

Line numbers below are as of `f7243d7` — **grep for the anchors, don't trust the numbers.**

## Pre-flight

- `git pull` first (work happens across two machines).
- Anchors: `function VisitorsOverview()` (~line 1669), `function CostsOverview()` (~line 1453), the heatmap scroll pattern to copy (`scrollRef.current.scrollLeft = scrollRef.current.scrollWidth`, ~line 1089), existing `@media (max-width: 600px)` block (~line 230).

## The defects (verified in code 2026-07-13)

Both pages render the same hand-rolled stacked daily bar chart and share all three problems:

1. **Bar overflow.** Bars are `flex: 1; min-width: 3px` with `gap: 2px`, one per day, no `overflow-x` on the container. At 90d that's ≥448px of bars, at 365d ≥1823px, inside a ~280px content column on a 375px phone → the flex row can't satisfy min-widths and the layout squeezes/clips. Even 30d gives ~9px touch targets.
2. **Mouse-only tooltips.** The per-bar breakdown is `onMouseEnter`/`onMouseLeave` only. No tap equivalent; on touch the data behind the chart is unreachable.
3. **Two-column grids.** Four inline `grid-template-columns: 1fr 1fr` blocks (visitors: By site/Top pages + Referrers/Countries; costs: By project/By model) stay two-column at any width → cramped and truncated on phones.

## Approach

Chart stays a time series on both pages (decided in #22: no replacement chart type). Three shared fixes plus one costs-only enhancement.

### 1. CSS additions (in the `<style>` block)

```css
.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 16px; }
.chart-scroll { overflow-x: auto; }
@media (max-width: 600px) {
  .two-col { grid-template-columns: 1fr; }
}
```

Replace the four inline two-col grid `style` attributes with `class="two-col"` (drop the duplicated inline properties; keep any margin overrides only if they differ).

### 2. Scrollable chart, opened at the recent end (both components)

Mirror the heatmap fix (#19). In each component, inside the existing `56px 1fr` grid, wrap the **bars row + tick-label row together** in one scroll container so they stay aligned:

```jsx
const scrollRef = useRef(null);
useEffect(() => {
  if (scrollRef.current) scrollRef.current.scrollLeft = scrollRef.current.scrollWidth;
}, [data, days]);
...
<div class="chart-scroll" ref=${scrollRef}>
  <div style="min-width: ${n * 7}px">
    ...bars row (unchanged)...
    ...tick row (unchanged)...
  </div>
</div>
```

7px/day = 5px bar + 2px gap floor. 30d (210px) fits phones without scrolling; 90d/365d scroll horizontally, opening at today. Desktop is unchanged (content narrower than container → no scrollbar, flex:1 still stretches bars).

`useRef` must be pulled from the preact hooks import if not already destructured — check the existing import line; the heatmap already uses it, so it's there.

### 3. Tap-to-select day breakdown (both components)

The floating tooltip cannot simply be enabled for touch: inside an `overflow-x: auto` container, `overflow-y` computes to `auto` too, so an absolutely-positioned tooltip rising above the bars **gets clipped by the scroll container**. Don't fight that. Instead:

- Module-scope, once: `const CAN_HOVER = window.matchMedia('(hover: hover) and (pointer: fine)').matches;`
- Gate the existing floating tooltip render on `CAN_HOVER && isHovered && ...` (desktop behavior unchanged; the tooltip still escapes clipping there only because desktop never scrolls — if a long window ever scrolls on desktop the tooltip may clip at the container top; acceptable, the click panel below covers it).
- Add `selected` state (`useState(null)`, a date-index or `null`). On each bar wrapper add `onClick=${() => setSelected(s => s === i ? null : i)}`. Reset to `null` when `days` changes.
- When `selected != null` and that day has data, render a **static breakdown panel directly below the chart panel** (not floating): date + total on one line, then the same per-segment rows the tooltip shows (color swatch, name, value), all segments not just 6, using the existing `panel(...)` helper. Add a small dismiss (`×`) button. This works on desktop too — it's not touch-gated.

### 4. Costs only: spend-share bars in the By project legend

Resolution of #22's "alternate presentation" question: keep the time series, make the legend carry the per-project comparison. Each By project row gets a thin proportional bar under the label line:

```jsx
const maxProj = ranked[0]?.[1] || 1;
// inside the legend row <a>, after the existing flex line, or restructure the <a> to column:
<div style="height: 3px; border-radius: 2px; margin-top: 3px;
            width: ${(v / maxProj * 100).toFixed(1)}%;
            background: ${segColor(p)}; opacity: 0.6"></div>
```

The `<a>` row needs `display: block` (or an inner wrapper) so the bar sits under the name/percent/value line rather than inside the flex row. Keep the row's click-through to `#/project/<p>/cost` working.

## Out of scope — do not touch

- `CostChart` (project detail page, ~line 1873) and the home activity chart (~line 878) have the same hover-only/two-col disease. Leave them; note in the PR that they're candidates for the same treatment.
- No refactor into a shared chart component. The two chart bodies are near-copies and the duplication is real, but parallel edits are deliberately chosen here to keep the blast radius small in a 3,600-line single-file app. If both edits land cleanly, file a follow-up issue for extraction.
- Breakpoint is 600px to match the file's existing convention (`.header-meta` etc.). Don't invent a new one.

## Verification

Mechanical (always possible):
- No JS errors: load the page, check console clean.
- Grep-level: all four two-col grids converted; both components have scrollRef + selected state; `CAN_HOVER` defined once.

Live (preferred):
- `cd web && vercel` → preview deploy. Preview is auth-gated like prod; **do not paste secrets** — ask Nico to log in once in the browser you're driving.
- Mobile check at 375×812 (Playwright viewport or Chrome device emulation), both `#/visitors` and `#/costs`:
  - PASS: no page-level horizontal scroll; 30d chart fits; 90d/365d chart scrolls *inside its panel* and opens showing the most recent days; tapping a bar shows the breakdown panel below the chart; By site/Top pages/Referrers/Countries/By project/By model all single-column.
  - FAIL: page scrolls sideways, bars unreadably squeezed, tap does nothing, or tooltip appears clipped.
- Desktop regression at ≥1200px: hover tooltips still float per bar; grids two-column; costs legend rows still link to per-project cost pages; spend-share bars render.

Then PR → CI (ruff + tests; frontend-only, should be untouched) → squash-merge closes #21 + #22 → deploy job ships it. Ask Nico for a phone smoke test after prod deploy:

Smoke test (self-contained): open https://prompt-labs.org/#/visitors on your phone, log in if prompted. PASS = the chart fits the screen or scrolls smoothly sideways within its own box (page doesn't scroll sideways), tapping a bar shows that day's per-site numbers below the chart, and the lists below are one column. Repeat at https://prompt-labs.org/#/costs (per-project numbers + colored share bars). FAIL = anything squeezed off-screen, sideways page wobble, or taps doing nothing.
