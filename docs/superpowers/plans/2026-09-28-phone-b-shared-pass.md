# Phone-first PR B — shared phone pass — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every dashboard route comfortable on a 390px phone: charts that never scroll sideways, touch selection with a readout, 44px controls, a one-line header, collapsed page notes, and collapsed uptime cards.

**Architecture:** Bucketing and hit-testing are pure functions inside a marked block of `web/index.html`, unit-tested under Node by extracting the block. One shared `StackedBars` component replaces the five copy-pasted stacked bar charts so bucketing and touch selection exist once. Narrowness reaches JS through a `useNarrow()` hook backed by a `matchMedia` listener. The phone layout check from PR A gains fixtures and checks for every route, and a desktop profile pins that wide layouts are unchanged.

**Tech Stack:** Preact + HTM inline in `web/index.html` (no build step), Node 20 built-in `assert`, Playwright (dev-only, local), standalone Python test runners.

**Spec:** `docs/superpowers/specs/2026-09-28-phone-first-design.md` (section "PR B")

## Global Constraints

- `web/index.html` stays a single file served as-is: no build step, no new runtime dependency, no separately served JS module.
- Desktop must not get worse. At widths above 640px every chart renders daily bars at every window and a click on a bar navigates to `#/day/<date>`, exactly as today. Layout changes are gated to `max-width: 640px` (or `600px` where an existing rule already uses it).
- "Narrow" means `window.matchMedia('(max-width: 640px)')`. JS learns it only through `useNarrow()`, which listens for changes, so rotation cannot desync it.
- Bucket sizes on a narrow screen: window of 365 days renders monthly buckets, 90 days renders weekly buckets, 7 and 30 days stay daily. A week runs Monday to Sunday.
- Calendar arithmetic on `YYYY-MM-DD` strings uses `Date.UTC` on the parsed parts and the `getUTC*` getters. Never `new Date(iso)` with local getters, and never `toISOString()` followed by `.slice(0,` (a source guard in `scripts/test_web_api.py` fails the build on that pattern).
- On a phone, selected-bucket detail renders in normal page flow under the chart. No `position: fixed` and no floating tooltip on touch.
- Tap targets on a phone are at least 44px tall: every `button`, `summary`, `select`, `[role=tab]`, and every anchor whose computed `display` is not `inline`. Inline links inside running text are exempt.
- The repository is public. Fixtures are synthetic: hostnames use the `.example` TLD, project names are invented, no real traffic, costs or summaries. Screenshots go only to the gitignored `.playwright-mcp/phone/` directory.
- Tests are standalone runners, not pytest. Python: `/Users/nico/src/prompt-lab/.venv/bin/python scripts/test_web_api.py`. Pure JS: `node scripts/test_frontend_pure.mjs`. Layout: `node scripts/phone/check.mjs`. Ruff: `/Users/nico/src/prompt-lab/.venv/bin/ruff check . --exclude .venv`.
- Match the surrounding code's comment density and voice: comments explain why, not what.
- Commit messages end with the line `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Never read `.env` files or any secret material. Never run `install.sh`.
- Work only inside this worktree: `/Users/nico/src/prompt-lab/.claude/worktrees/phone-first`. Do not push; the controller pushes.

## Review Focus

- A window that starts mid-week or mid-month: the first and last buckets are partial, every date lands in exactly one bucket, and totals across buckets equal the daily total. Pinned in Task 1.
- A Monday and a Sunday at a year boundary and at both DST changes: each buckets to its own Monday-to-Sunday week. Pinned in Task 1.
- A bucket with no data at all (a week before a site was instrumented): it renders as an empty bar, can be selected, and its readout says zero rather than showing `NaN` or nothing. Pinned in Task 3.
- Rotating the phone while a weekly bucket is selected: the chart re-buckets to the new width and the stale selection is cleared rather than pointing at a bucket that no longer exists. Pinned in Task 3.
- A vertical scroll that starts on a chart: the page still scrolls, and the drag does not select a bar by accident on its way. Pinned in Task 3.
- A reader (non-admin) account: the header has three destinations, fits one line, and offers no Visitors or Health. Pinned in Task 6.

---

### Task 1: Pure helpers block and its Node test runner

**Files:**
- Modify: `web/index.html` — add the marked block directly above the line `// ---- Costs Overview (all projects, over time) ----`; move the existing `fmtShortDate` into it.
- Create: `scripts/test_frontend_pure.mjs`
- Modify: `.github/workflows/test.yml` — add one step after `Web API unit tests`.
- Modify: `CLAUDE.md` — the `### Testing` section only.

**Interfaces:**
- Produces, all inside the `// <pure>` … `// </pure>` block of `web/index.html`:
  - `fmtShortDate(iso: string): string` — `'2026-09-14'` → `'Sep 14'` (moved, behaviour unchanged).
  - `fmtMonth(ym: string): string` — `'2026-09'` → `'Sep 2026'`.
  - `addDays(iso: string, n: number): string`
  - `mondayOf(iso: string): string`
  - `bucketSizeFor(days: number, narrow: boolean): 'day' | 'week' | 'month'`
  - `bucketDates(dates: string[], size): Array<{ key: string, size: string, dates: string[], label: string }>`
  - `bucketTotals(bucket, byDateSeg: {[date]: {[segment]: number|string}}): { total: number, segs: Array<[string, number]> }`
  - `bucketIndexAt(x: number, width: number, count: number): number` — `-1` when there is nothing to hit.

- [ ] **Step 1: Write the failing test runner**

Create `scripts/test_frontend_pure.mjs`:

```js
#!/usr/bin/env node
// Unit tests for the pure helpers in web/index.html. The dashboard is one file
// with no build step, so the helpers cannot be imported: this extracts the
// block between the `// <pure>` and `// </pure>` markers and evaluates it.
// Anything inside the markers must therefore stay free of window, document
// and html — a reference to any of them fails here, which is the point.
//
//   node scripts/test_frontend_pure.mjs

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const src = readFileSync(path.join(ROOT, 'web', 'index.html'), 'utf8');

const open = src.indexOf('// <pure>');
const close = src.indexOf('// </pure>');
if (open < 0 || close < 0 || close < open) {
  console.error('FAIL: no `// <pure>` … `// </pure>` block in web/index.html');
  process.exit(1);
}
if (src.indexOf('// <pure>', open + 1) >= 0) {
  console.error('FAIL: more than one `// <pure>` marker in web/index.html');
  process.exit(1);
}

const NAMES = ['fmtShortDate', 'fmtMonth', 'addDays', 'mondayOf', 'bucketSizeFor',
               'bucketDates', 'bucketTotals', 'bucketIndexAt'];
const pure = new Function(`"use strict";\n${src.slice(open, close)}\nreturn { ${NAMES.join(', ')} };`)();

const tests = [];
const test = (name, fn) => tests.push([name, fn]);

// Ascending run of calendar days, built with the helper under test's own
// arithmetic deliberately avoided: plain UTC math, so a bug in addDays cannot
// hide itself.
function days(from, count) {
  const [y, m, d] = from.split('-').map(Number);
  return Array.from({ length: count }, (_, i) => {
    const t = new Date(Date.UTC(y, m - 1, d + i));
    const p = (n) => String(n).padStart(2, '0');
    return `${t.getUTCFullYear()}-${p(t.getUTCMonth() + 1)}-${p(t.getUTCDate())}`;
  });
}

test('fmtShortDate and fmtMonth', () => {
  assert.equal(pure.fmtShortDate('2026-09-14'), 'Sep 14');
  assert.equal(pure.fmtShortDate('2026-01-05'), 'Jan 5');
  assert.equal(pure.fmtMonth('2026-09'), 'Sep 2026');
  assert.equal(pure.fmtMonth('2027-01'), 'Jan 2027');
});

test('addDays crosses months, years, leap days and both DST changes', () => {
  assert.equal(pure.addDays('2026-09-30', 1), '2026-10-01');
  assert.equal(pure.addDays('2026-12-31', 1), '2027-01-01');
  assert.equal(pure.addDays('2027-01-01', -1), '2026-12-31');
  assert.equal(pure.addDays('2028-02-28', 1), '2028-02-29');
  assert.equal(pure.addDays('2026-03-08', 1), '2026-03-09');   // US spring forward
  assert.equal(pure.addDays('2026-11-01', 1), '2026-11-02');   // US fall back
  assert.equal(pure.addDays('2026-09-14', 0), '2026-09-14');
});

test('mondayOf: a Monday is its own week, a Sunday belongs to the week before', () => {
  assert.equal(pure.mondayOf('2026-09-14'), '2026-09-14');     // Monday
  assert.equal(pure.mondayOf('2026-09-13'), '2026-09-07');     // Sunday
  assert.equal(pure.mondayOf('2026-09-16'), '2026-09-14');     // Wednesday
  assert.equal(pure.mondayOf('2027-01-01'), '2026-12-28');     // Friday, across the year
  assert.equal(pure.mondayOf('2026-03-08'), '2026-03-02');     // Sunday of spring forward
  assert.equal(pure.mondayOf('2026-11-02'), '2026-11-02');     // Monday after fall back
});

test('bucketSizeFor: only a narrow screen buckets, and only long windows', () => {
  for (const d of [7, 30, 90, 365]) assert.equal(pure.bucketSizeFor(d, false), 'day');
  assert.equal(pure.bucketSizeFor(7, true), 'day');
  assert.equal(pure.bucketSizeFor(30, true), 'day');
  assert.equal(pure.bucketSizeFor(90, true), 'week');
  assert.equal(pure.bucketSizeFor(365, true), 'month');
});

test('bucketDates day: one bucket per date', () => {
  const b = pure.bucketDates(days('2026-09-01', 3), 'day');
  assert.deepEqual(b.map((x) => x.key), ['2026-09-01', '2026-09-02', '2026-09-03']);
  assert.deepEqual(b.map((x) => x.label), ['Sep 1', 'Sep 2', 'Sep 3']);
  assert.ok(b.every((x) => x.dates.length === 1 && x.size === 'day'));
});

test('bucketDates week: partial first and last buckets, Monday keys', () => {
  // 2026-09-01 is a Tuesday; 14 days ends on Monday 2026-09-14.
  const b = pure.bucketDates(days('2026-09-01', 14), 'week');
  assert.deepEqual(b.map((x) => x.key), ['2026-08-31', '2026-09-07', '2026-09-14']);
  assert.deepEqual(b.map((x) => x.dates.length), [6, 7, 1]);
  assert.deepEqual(b.map((x) => x.label), ['Sep 1–6', 'Sep 7–13', 'Sep 14']);
});

test('bucketDates week: a week spanning two months names both', () => {
  const b = pure.bucketDates(days('2026-09-28', 7), 'week');
  assert.equal(b.length, 1);
  assert.equal(b[0].label, 'Sep 28 – Oct 4');
});

test('bucketDates month: a 365-day window covers every date exactly once', () => {
  const all = days('2025-09-29', 365);
  const b = pure.bucketDates(all, 'month');
  assert.ok(b.length === 12 || b.length === 13, `month count ${b.length}`);
  assert.deepEqual(b.flatMap((x) => x.dates), all);
  assert.equal(b[0].label, 'Sep 2025');
  assert.equal(b[b.length - 1].label, 'Sep 2026');
  assert.equal(b[0].dates.length, 2, 'first bucket is partial: Sep 29 and 30');
});

test('bucketDates: empty input gives no buckets', () => {
  assert.deepEqual(pure.bucketDates([], 'week'), []);
});

test('bucketTotals merges segments, coerces strings, sorts largest first', () => {
  const [week] = pure.bucketDates(days('2026-09-07', 7), 'week');
  const got = pure.bucketTotals(week, {
    '2026-09-07': { a: 2, b: '5' },          // Turso hands counts back as strings
    '2026-09-09': { a: 3, c: 1 },
    '2026-09-20': { a: 100 },                // outside the bucket: ignored
  });
  assert.deepEqual(got, { total: 11, segs: [['a', 5], ['b', 5], ['c', 1]] });
});

test('bucketTotals: a bucket with no data is zero, not NaN', () => {
  const [week] = pure.bucketDates(days('2026-09-07', 7), 'week');
  assert.deepEqual(pure.bucketTotals(week, {}), { total: 0, segs: [] });
  assert.deepEqual(pure.bucketTotals(week, { '2026-09-07': { a: 'x' } }), { total: 0, segs: [['a', 0]] });
});

test('bucket totals across a window equal the daily total', () => {
  const all = days('2026-07-01', 90);
  const byDate = Object.fromEntries(all.map((d, i) => [d, { a: i % 5, b: 1 }]));
  const daily = all.reduce((s, d) => s + byDate[d].a + byDate[d].b, 0);
  for (const size of ['day', 'week', 'month']) {
    const sum = pure.bucketDates(all, size)
      .reduce((s, b) => s + pure.bucketTotals(b, byDate).total, 0);
    assert.equal(sum, daily, `${size} buckets lose or double-count`);
  }
});

test('bucketIndexAt clamps to the chart and refuses an empty one', () => {
  assert.equal(pure.bucketIndexAt(0, 300, 30), 0);
  assert.equal(pure.bucketIndexAt(299.9, 300, 30), 29);
  assert.equal(pure.bucketIndexAt(300, 300, 30), 29);    // the right edge itself
  assert.equal(pure.bucketIndexAt(-5, 300, 30), 0);      // finger slid off the left
  assert.equal(pure.bucketIndexAt(400, 300, 30), 29);    // and off the right
  assert.equal(pure.bucketIndexAt(155, 300, 30), 15);
  assert.equal(pure.bucketIndexAt(10, 0, 30), -1);       // not measured yet
  assert.equal(pure.bucketIndexAt(10, 300, 0), -1);      // no buckets
});

let failed = 0;
for (const [name, fn] of tests) {
  try {
    fn();
    console.log(`PASS ${name}`);
  } catch (e) {
    failed++;
    console.log(`FAIL ${name}\n     ${String(e.message).split('\n').join('\n     ')}`);
  }
}
console.log(`${tests.length - failed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
```

- [ ] **Step 2: Run it to verify it fails**

Run: `node scripts/test_frontend_pure.mjs`
Expected: exit code 1 with `FAIL: no \`// <pure>\` … \`// </pure>\` block in web/index.html`.

- [ ] **Step 3: Add the pure block to `web/index.html`**

Delete the existing `function fmtShortDate(iso) { … }` (it sits just below `fmtUsd`). Insert this block directly above the comment line `// ---- Costs Overview (all projects, over time) ----`, indented to match the surrounding script (4 spaces):

```js
    // <pure>
    // Pure helpers: no DOM, no Preact, nothing from outside this block.
    // scripts/test_frontend_pure.mjs lifts the block out by its markers and
    // unit-tests it under Node — the only way to test logic in a page that has
    // no build step. A reference to window, document or html in here fails
    // that run, which is what keeps the block honest.
    const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun',
                    'Jul','Aug','Sep','Oct','Nov','Dec'];
    function fmtShortDate(iso) {
      const [, m, d] = iso.split('-');
      return MONTHS[parseInt(m, 10) - 1] + ' ' + parseInt(d, 10);
    }
    function fmtMonth(ym) {
      const [y, m] = ym.split('-');
      return MONTHS[parseInt(m, 10) - 1] + ' ' + y;
    }

    // Calendar arithmetic on YYYY-MM-DD strings. The strings are already
    // Pacific calendar days; Date.UTC on their parts keeps them that way.
    // Reading one back through a timezone is how a bucket slides a day.
    function addDays(iso, n) {
      const [y, m, d] = iso.split('-').map(Number);
      const t = new Date(Date.UTC(y, m - 1, d + n));
      const p = (v) => String(v).padStart(2, '0');
      return t.getUTCFullYear() + '-' + p(t.getUTCMonth() + 1) + '-' + p(t.getUTCDate());
    }
    // Monday-to-Sunday weeks, and a Monday is its own week — the same rule the
    // SQL rollups use ('weekday 0','-6 days'), so a phone bar and a weekly
    // rollup never disagree about which week a Monday belongs to.
    function mondayOf(iso) {
      const [y, m, d] = iso.split('-').map(Number);
      const weekday = new Date(Date.UTC(y, m - 1, d)).getUTCDay();   // 0 = Sunday
      return addDays(iso, -((weekday + 6) % 7));
    }

    // A phone has room for about fifty bars. 90 days become weeks and a year
    // becomes months there; a wide screen keeps a bar per day at every window.
    function bucketSizeFor(days, narrow) {
      if (!narrow) return 'day';
      if (days >= 365) return 'month';
      if (days >= 90) return 'week';
      return 'day';
    }

    function bucketLabel(b) {
      const first = b.dates[0], last = b.dates[b.dates.length - 1];
      if (b.size === 'month') return fmtMonth(b.key);
      if (b.size === 'week' && first !== last) {
        return first.slice(0, 7) === last.slice(0, 7)
          ? fmtShortDate(first) + '–' + parseInt(last.slice(8), 10)
          : fmtShortDate(first) + ' – ' + fmtShortDate(last);
      }
      return fmtShortDate(first);
    }

    // `dates` ascending. The first and last bucket are usually partial: a
    // window rarely starts on a Monday or on the 1st.
    function bucketDates(dates, size) {
      const out = [];
      for (const d of dates) {
        const key = size === 'month' ? d.slice(0, 7) : size === 'week' ? mondayOf(d) : d;
        const last = out[out.length - 1];
        if (last && last.key === key) last.dates.push(d);
        else out.push({ key, size, dates: [d] });
      }
      for (const b of out) b.label = bucketLabel(b);
      return out;
    }

    // byDateSeg: { date: { segment: count } }. Counts may arrive as strings.
    function bucketTotals(bucket, byDateSeg) {
      const merged = {};
      for (const d of bucket.dates)
        for (const [s, v] of Object.entries(byDateSeg[d] || {}))
          merged[s] = (merged[s] || 0) + (Number(v) || 0);
      const segs = Object.entries(merged)
        .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
      return { total: segs.reduce((t, [, v]) => t + v, 0), segs };
    }

    // Which bucket is under a pointer `x` pixels into a chart `width` wide.
    // Clamped, because a finger dragging across a chart slides off its edges.
    function bucketIndexAt(x, width, count) {
      if (!(width > 0) || count < 1) return -1;
      return Math.max(0, Math.min(count - 1, Math.floor((x / width) * count)));
    }
    // </pure>

```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `node scripts/test_frontend_pure.mjs`
Expected: 13 `PASS` lines, `13 passed, 0 failed`, exit code 0.

Run: `/Users/nico/src/prompt-lab/.venv/bin/python scripts/test_web_api.py 2>&1 | tail -5`
Expected: all pass (the `clocks:` source guard reads `web/index.html`).

Run: `node scripts/phone/check.mjs`
Expected: all PASS — moving `fmtShortDate` must not break any page.

- [ ] **Step 5: Add the CI step and document the runner**

In `.github/workflows/test.yml`, directly after the `Web API unit tests` step:

```yaml
      - name: Frontend pure-helper tests
        run: node scripts/test_frontend_pure.mjs
```

In `CLAUDE.md`'s `### Testing` section, directly before the paragraph that begins "Phone layout is checked by a separate local runner", add:

```markdown
The dashboard is one file with no build step, so its logic cannot be imported by
a test. Pure helpers live in `web/index.html` between `// <pure>` and
`// </pure>`; `node scripts/test_frontend_pure.mjs` lifts that block out and
unit-tests it (CI-gated). Keep the block free of `window`, `document` and `html`.
```

- [ ] **Step 6: Commit**

```bash
git add web/index.html scripts/test_frontend_pure.mjs .github/workflows/test.yml CLAUDE.md
git commit -m "test: pure bucketing helpers with a Node runner that lifts them from index.html"
```

---

### Task 2: Fixtures and baseline checks for every route

**Files:**
- Modify: `scripts/phone/fixtures.mjs`
- Modify: `scripts/phone/checks.mjs`

**Interfaces:**
- Consumes: `apiFixture(pathname, searchParams, method)`, `fixtureOptions`, `resetFixtureOptions()`, `labDay(i)`, `CHECKS`, `pageOverflow(page)` and the `before`/`after` hooks from PR A. The runner already fails a check when the page requests an API route that has no fixture, and resets `fixtureOptions` after every check; add any new option to the defaults that `resetFixtureOptions()` restores.
- Produces: fixtures for `/api/overview`, `/api/info`, `/api/activity_timeline`, `/api/cost_overview`, `/api/cost_timeline`, `/api/project`, `/api/day`, `/api/todos`, `/api/health_report`, `/api/uptime_overview`. `fixtureOptions.role` (`'admin'` default, or `'reader'`) controls what `/api/login` returns.
- Produces: checks named `home`, `activity`, `costs`, `todos`, `health`, `about`, `day`, `project`, each under profile `phone`, and the same eight with the suffix `-desktop` under profile `desktop`. Exported helper `smallTargets(page)` returning `[{ what, w, h }]` for every tap target under 44px tall per the Global Constraints rule.
- Produces: invented project names used by later tasks: `alpha-app`, `bravo-site`, `charlie-tool`, `delta-lab` plus eight more, so a chart has more than eight segments and one folds into "other".

- [ ] **Step 1: Learn each response shape from its source**

For each endpoint read the handler in `web/api/<name>.py` and the component in `web/index.html` that consumes it (search for `api('/api/<name>`). The shape the component reads is the contract; `scripts/test_web_api.py` has stubbed examples for most endpoints. Do not read any `.env` file and do not call the live API.

- [ ] **Step 2: Write the fixtures**

Add one builder function per endpoint to `scripts/phone/fixtures.mjs` and route to it from `apiFixture`. Requirements:

- Deterministic (use the existing `seeded()` generator), dates from `labDay(i)`.
- 365 days of data wherever the page offers a 1y window, so 90d and 1y charts have something to bucket.
- Twelve invented projects in `overview` and `activity_timeline`, so the ninth and later fold into the "other" colour.
- At least one project name 40 characters long with no break characters, and one daily summary of 600 characters, because long unbroken text is what broke Visitors.
- `/api/health_report` with eleven targets and `/api/uptime_overview` with twelve monitors, including one monitor whose series starts only ten days ago (the grey "not archived" case) and one day with uptime below 100.
- `/api/day` answers for any date requested.
- `/api/login` returns `{ role: fixtureOptions.role, email: null }`.
- Unknown paths keep returning the 404 `no fixture for …` body.

- [ ] **Step 3: Write the baseline checks**

Add `smallTargets` to `scripts/phone/checks.mjs`:

```js
// Tap targets under 44px tall. Inline links inside running text are exempt:
// padding them to 44px would tear the paragraph apart, and WCAG exempts them.
export async function smallTargets(page) {
  return page.evaluate(() => {
    const out = [];
    for (const el of document.querySelectorAll('button, summary, select, [role=tab], a')) {
      const r = el.getBoundingClientRect();
      if (!r.width || !r.height) continue;                      // not rendered
      if (el.tagName === 'A' && getComputedStyle(el).display === 'inline') continue;
      if (r.height < 44) {
        out.push({ what: (el.innerText || el.getAttribute('aria-label') || el.tagName).trim().slice(0, 24),
                   w: Math.round(r.width), h: Math.round(r.height) });
      }
    }
    return out;
  });
}
```

Add the sixteen checks with a small factory so each route is one line:

```js
const ROUTES = [
  ['home', '#/', 'text=Active projects'],
  ['activity', '#/activity', 'text=By project'],
  ['costs', '#/costs', 'text=By project'],
  ['todos', '#/todos', 'text=open across'],
  ['health', '#/health', 'text=Uptime archive'],
  ['about', '#/about', 'text=About'],
  ['day', '#/day/' + labDay(1), 'text=back'],
  ['project', '#/project/alpha-app', 'text=Trajectory'],
];

function baseline([name, hash, ready], profile) {
  return {
    name: profile === 'phone' ? name : `${name}-${profile}`,
    profile, hash, ready,
    async run(page, t) {
      const m = await pageOverflow(page);
      t.ok(m.doc <= m.vw, `no horizontal page overflow (document ${m.doc}px, viewport ${m.vw}px)`);
      const errors = await page.evaluate(() => /Couldn't load|no fixture for/.test(document.body.innerText));
      t.ok(!errors, 'page rendered its data, not an error placeholder');
    },
  };
}

CHECKS.push(...ROUTES.flatMap((r) => [baseline(r, 'phone'), baseline(r, 'desktop')]));
```

Adjust a `ready` selector if the page's real text differs; keep it specific to content that only appears once data has rendered. `CHECKS` must be declared before the `push`.

- [ ] **Step 4: Run the checks**

Run: `node scripts/phone/check.mjs`
Expected: every check PASS, exit code 0. Overflow already passes on these routes; the value of this task is that the fixtures render every page, so later tasks have a baseline to break.

Read these screenshots and confirm each shows a fully rendered page with charts and lists, not a spinner, an error, or an empty state: `.playwright-mcp/phone/home-phone.png`, `activity-phone.png`, `costs-phone.png`, `health-phone.png`, `day-phone.png`, `project-phone.png`, `todos-phone.png`, `home-desktop.png`, `health-desktop.png`.

Copy the nine desktop and phone screenshots of `home`, `activity`, `costs`, `health`, `project` to `.playwright-mcp/phone/baseline/` (same filenames). Later tasks compare against them by eye. The directory is gitignored.

- [ ] **Step 5: Record the current small targets**

The list of controls under 44px is what Task 6 must empty, so record it now. Add a temporary, non-failing probe: in the `baseline` factory, for the `phone` profile only, log (with `console.log`, not `t.ok`) `smallTargets(page)` grouped as `<name>: <count> targets under 44px` plus the distinct `what` labels. Run `node scripts/phone/check.mjs`, copy the lines into the report, then remove the probe before committing. Task 6 adds the real assertion.

- [ ] **Step 6: Commit**

```bash
git add scripts/phone/fixtures.mjs scripts/phone/checks.mjs
git commit -m "test: phone check fixtures and baseline overflow checks for every route"
```

---

### Task 3: `useNarrow`, `StackedBars` and `ChartReadout`, on the Visitors chart

**Files:**
- Modify: `web/index.html` — new `useNarrow` hook and `StackedBars`, `ChartReadout` components placed directly after `DateAxis`; new CSS next to `.chart-scroll`; `VisitorsOverview` uses `StackedBars` in place of its inline chart.
- Modify: `scripts/phone/checks.mjs`

**Interfaces:**
- Consumes: from Task 1, `bucketSizeFor`, `bucketDates`, `bucketTotals`, `bucketIndexAt`, `fmtShortDate`. Existing `DateAxis({ dates, fmt, style })`, `CAN_HOVER`, `navigate(hash)`, `prefetchDay(date)`, `labDay(i)`.
- Produces: `useNarrow(): boolean`.
- Produces: `StackedBars({ id, dates, days, byDateSeg, segColor, fmtValue, unit, chartH, markToday })`:
  - `id: string` — goes to `data-chart` for tests.
  - `dates: string[]` — ascending calendar days of the window.
  - `days: number` — the window (7, 30, 90, 365).
  - `byDateSeg: { [date]: { [segment]: number } }`.
  - `segColor: (segment) => cssColor`.
  - `fmtValue: (n) => string` — e.g. `n => n.toLocaleString()` or `fmtUsd`.
  - `unit: string` — appended after a total in the tooltip and readout (`'views'`, `'prompts'`), or `''`.
  - `chartH: number` — bar area height in px, default `140`.
  - `markToday: boolean` — draw the dashed outline on the last day, default `false`.
- Produces: `ChartReadout({ bucket, total, segs, segColor, fmtValue, unit, byDateTotal })`.
- Produces test hooks: `data-test="chart"` + `data-chart=<id>` on the chart root; `data-test="chart-bars"` on the element that receives pointer events (its width is the hit-test width); `data-test="chart-bar"` on each bar with `data-key=<bucket key>`; `data-test="chart-readout"`; `data-test="open-day"`; `data-test="day-chip"` with `data-date=<date>`.

**Behaviour (the requirements; the component is yours to write):**

1. `useNarrow` reads `window.matchMedia('(max-width: 640px)')`, returns its current `matches`, and updates on the media query's `change` event. Use `addEventListener('change', …)` with a fallback to the deprecated `addListener` for older Safari. Clean up on unmount.
2. `StackedBars` computes `size = bucketSizeFor(days, narrow)`, `buckets = bucketDates(dates, size)`, and each bucket's `bucketTotals`. The y-axis gutter shows the peak bucket total, half of it, and zero, formatted with `fmtValue`.
3. Wide screen (`!narrow`): render exactly what the Visitors chart renders today — the `56px 1fr` grid, the `.chart-scroll` container opening at its right end, `min-width: n * 7px`, the hover tooltip gated by `CAN_HOVER`, `prefetchDay` on pointer enter, and a click on a bar navigating to `#/day/<date>`. Compare against `.playwright-mcp/phone/baseline/` and the `visitors-desktop` screenshot.
4. Narrow screen: no `min-width` on the bar row and no horizontal scroll; the bars share the available width. The gutter is `44px` wide.
5. Selection. The bar row has `touch-action: pan-y`, so a vertical swipe scrolls the page and a horizontal drag stays with the chart. On `pointerdown` and `pointermove` with `pointerType === 'touch'` (or `'pen'`), select `bucketIndexAt(clientX - rowLeft, rowWidth, buckets.length)`. A touch that turns into a vertical scroll must not drag the selection with it: remember the `pointerdown` point, follow the pointer only while it stays within 10px vertically of that point, and stop following for the rest of the gesture once it moves further or `pointercancel` fires (the browser fires that when it takes the gesture for scrolling). A plain tap (down and up without moving) selects.
6. A click on a bar (mouse) navigates when the bucket is a single day and `CAN_HOVER` is true; otherwise it selects. So a narrow desktop window with weekly buckets selects rather than guessing a day.
7. The selected bar is drawn at full opacity with the others at `0.45`; with nothing selected all bars are at `0.85` as today.
8. `ChartReadout` renders under the date axis, in normal flow, when a bucket is selected: a heading `<label> · <fmtValue(total)> <unit>`; up to six segment rows (swatch, name, value) and `+N more`; and then either
   - for a day bucket, a button `Open day →` (`data-test="open-day"`, at least 44px tall, full width) that navigates to `#/day/<date>`; or
   - for a week or month bucket, the bucket's days as chips (`data-test="day-chip"`), each showing the day of the month, at least 44px by 44px, in a wrapping grid, each navigating to `#/day/<date>`. A day whose total is zero is dimmed (`opacity: 0.45`) but still tappable. `byDateTotal(date)` supplies the per-day total.
   A bucket with no data shows the heading with a zero total and the text `Nothing recorded.` in place of segment rows.
9. When `days`, `dates.length` or `narrow` changes, clear the selection: the index would point at a different bucket.
10. `markToday` draws the dashed outline on the final day bucket only when `size === 'day'`.
11. In `VisitorsOverview`, replace the inline chart (the `panel(html\`…\`)` block holding the `56px 1fr` grid) with `<${StackedBars} id="visitors" … />` inside the same `panel(...)`, and delete the state and refs the inline chart needed (`hovered`, `scrollRef`, the scroll `useEffect`) if nothing else uses them.

- [ ] **Step 1: Write the failing checks**

Add to `scripts/phone/checks.mjs` a helper and three checks:

```js
// Drive a chart the way a thumb does. Returns the bar-row box.
async function chartBox(page, id) {
  return page.locator(`[data-chart="${id}"] [data-test="chart-bars"]`).boundingBox();
}
async function tapAt(page, x, y) { await page.touchscreen.tap(x, y); }

function chartCheck({ name, hash, ready, id, windows }) {
  return {
    name, profile: 'phone', hash, ready,
    async run(page, t) {
      for (const [label, expectMin, expectMax] of windows) {
        await page.getByRole('button', { name: label, exact: true }).tap();
        await page.waitForTimeout(400);
        const chart = page.locator(`[data-chart="${id}"]`);
        const bars = await chart.locator('[data-test="chart-bar"]').count();
        t.ok(bars >= expectMin && bars <= expectMax, `${label}: ${bars} bars (expected ${expectMin}–${expectMax})`);
        const scroll = await chart.evaluate((root) => Math.max(0, ...[...root.querySelectorAll('*')]
          .map((e) => e.scrollWidth - e.clientWidth)));
        t.ok(scroll <= 1, `${label}: nothing inside the chart scrolls sideways (overflow ${scroll}px)`);
        const m = await pageOverflow(page);
        t.ok(m.doc <= m.vw, `${label}: no horizontal page overflow (${m.doc}px)`);

        await chart.scrollIntoViewIfNeeded();
        const box = await chartBox(page, id);
        const before = page.url();
        await tapAt(page, box.x + box.width - 3, box.y + box.height / 2);   // the newest bar
        t.ok(page.url() === before, `${label}: tapping a bar does not leave the page`);
        const readout = chart.locator('[data-test="chart-readout"]');
        t.ok(await readout.isVisible(), `${label}: tapping a bar shows the readout`);
        const text = (await readout.innerText()).replace(/\s+/g, ' ');
        t.ok(!/NaN|undefined/.test(text), `${label}: readout is well formed ("${text.slice(0, 60)}")`);
        const fixed = await readout.evaluate((e) => {
          for (let n = e; n; n = n.parentElement) {
            if (getComputedStyle(n).position === 'fixed') return true;
          }
          return false;
        });
        t.ok(!fixed, `${label}: readout is in page flow, not a fixed overlay`);

        if (label === '7d' || label === '30d') {                // daily buckets
          const open = readout.locator('[data-test="open-day"]');
          const h = await open.evaluate((e) => Math.round(e.getBoundingClientRect().height));
          t.ok(h >= 44, `${label}: Open day is at least 44px tall (${h})`);
        } else {
          const chips = readout.locator('[data-test="day-chip"]');
          const n = await chips.count();
          const sizes = await chips.evaluateAll((els) => els.map((e) => {
            const r = e.getBoundingClientRect(); return Math.min(Math.round(r.width), Math.round(r.height));
          }));
          t.ok(n >= 1 && n <= 31, `${label}: readout lists the bucket's days (${n})`);
          t.ok(sizes.every((s) => s >= 44), `${label}: day chips are at least 44px (${Math.min(...sizes)})`);
        }
      }
    },
  };
}

CHECKS.push(chartCheck({
  name: 'visitors-chart', hash: '#/visitors', ready: 'text=By site', id: 'visitors',
  // window label, fewest and most bars it may draw on a phone
  windows: [['30d', 30, 30], ['90d', 13, 14], ['1y', 12, 13], ['7d', 7, 7]],
}));

CHECKS.push({
  name: 'visitors-chart-navigate', profile: 'phone', hash: '#/visitors', ready: 'text=By site',
  async run(page, t) {
    const chart = page.locator('[data-chart="visitors"]');
    await chart.scrollIntoViewIfNeeded();
    const box = await chartBox(page, 'visitors');
    await tapAt(page, box.x + box.width - 3, box.y + box.height / 2);
    await chart.locator('[data-test="open-day"]').tap();
    await page.waitForFunction(() => location.hash.startsWith('#/day/'));
    t.ok(/#\/day\/\d{4}-\d{2}-\d{2}$/.test(page.url()), `Open day goes to the day page (${page.url().split('#')[1]})`);

    await page.goto(page.url().split('#')[0] + '#/visitors');
    await page.locator('text=By site').first().waitFor();
    await page.getByRole('button', { name: '90d', exact: true }).tap();
    await page.waitForTimeout(400);
    await chart.scrollIntoViewIfNeeded();
    const wide = await chartBox(page, 'visitors');
    await tapAt(page, wide.x + wide.width / 2, wide.y + wide.height / 2);
    const chip = chart.locator('[data-test="day-chip"]').first();
    const date = await chip.getAttribute('data-date');
    await chip.tap();
    await page.waitForFunction(() => location.hash.startsWith('#/day/'));
    t.ok(page.url().endsWith('#/day/' + date), `a day chip goes to its own day (${date})`);
  },
});

CHECKS.push({
  name: 'visitors-chart-scroll', profile: 'phone', hash: '#/visitors', ready: 'text=By site',
  async run(page, t) {
    const chart = page.locator('[data-chart="visitors"]');
    await chart.scrollIntoViewIfNeeded();
    const action = await chart.locator('[data-test="chart-bars"]').evaluate((e) => getComputedStyle(e).touchAction);
    t.ok(action === 'pan-y', `bar row leaves vertical scrolling to the page (touch-action: ${action})`);

    // A selection, then a rotation: the chart re-buckets and must drop it.
    await page.getByRole('button', { name: '90d', exact: true }).tap();
    await page.waitForTimeout(400);
    const box = await chartBox(page, 'visitors');
    await tapAt(page, box.x + box.width / 2, box.y + box.height / 2);
    t.ok(await chart.locator('[data-test="chart-readout"]').isVisible(), 'a weekly bucket is selected');
    await page.setViewportSize({ width: 844, height: 390 });
    await page.waitForTimeout(400);
    const bars = await chart.locator('[data-test="chart-bar"]').count();
    t.ok(bars === 90, `landscape is wide: a bar per day (${bars})`);
    t.ok(!(await chart.locator('[data-test="chart-readout"]').isVisible()), 'the stale selection is cleared on rotate');
  },
});
```

Also extend the existing `visitors-desktop` check:

```js
      const chart = page.locator('[data-chart="visitors"]');
      for (const [label, n] of [['30d', 30], ['90d', 90], ['1y', 365]]) {
        await page.getByRole('button', { name: label, exact: true }).click();
        await page.waitForTimeout(400);
        const bars = await chart.locator('[data-test="chart-bar"]').count();
        t.ok(bars === n, `desktop ${label}: a bar per day (${bars})`);
      }
      await page.getByRole('button', { name: '30d', exact: true }).click();
      await page.waitForTimeout(400);
      const last = chart.locator('[data-test="chart-bar"]').last();
      await last.hover();
      t.ok(await chart.getByText(/views/).first().isVisible(), 'desktop: hovering a bar shows the tooltip');
      await last.click();
      await page.waitForFunction(() => location.hash.startsWith('#/day/'));
      t.ok(page.url().endsWith('#/day/' + labDay(0)), 'desktop: clicking a bar opens that day');
```

(`labDay` is imported from `./fixtures.mjs`.)

Run: `node scripts/phone/check.mjs visitors-chart visitors-chart-navigate visitors-chart-scroll visitors-desktop`
Expected: the three new checks FAIL or crash on the missing `data-chart` locator; the new desktop assertions crash the same way. Record the output.

An empty bucket must be selectable. Add a fixture switch `fixtureOptions.quietStart` that, when true, drops every `daily` row older than 40 days, and a check:

```js
CHECKS.push({
  name: 'visitors-chart-empty-bucket', profile: 'phone', hash: '#/visitors', ready: 'text=By site',
  async before() { fixtureOptions.quietStart = true; },
  async after() { fixtureOptions.quietStart = false; },
  async run(page, t) {
    await page.getByRole('button', { name: '90d', exact: true }).tap();
    await page.waitForTimeout(400);
    const chart = page.locator('[data-chart="visitors"]');
    await chart.scrollIntoViewIfNeeded();
    const box = await chartBox(page, 'visitors');
    await tapAt(page, box.x + 3, box.y + box.height / 2);              // the oldest bucket: no data
    const text = (await chart.locator('[data-test="chart-readout"]').innerText()).replace(/\s+/g, ' ');
    t.ok(/\b0\b/.test(text) && /Nothing recorded\./.test(text), `an empty bucket reads as zero ("${text.slice(0, 60)}")`);
    t.ok(!/NaN|undefined/.test(text), 'and is well formed');
  },
});
```

- [ ] **Step 2: Implement `useNarrow`, `StackedBars`, `ChartReadout` and the CSS** per the Behaviour list above.

- [ ] **Step 3: Use `StackedBars` in `VisitorsOverview`** per Behaviour item 11.

- [ ] **Step 4: Run the checks**

Run: `node scripts/phone/check.mjs`
Expected: every check PASS, exit code 0.

Run: `node scripts/test_frontend_pure.mjs && /Users/nico/src/prompt-lab/.venv/bin/python scripts/test_web_api.py 2>&1 | tail -3`
Expected: all pass.

Read `.playwright-mcp/phone/visitors-chart-phone.png`, `visitors-chart-navigate-phone.png` and `visitors-desktop.png`. Confirm by eye: the phone chart fills its panel with no clipped bars and the readout sits under the axis; the desktop chart looks like `.playwright-mcp/phone/baseline/` did for the other charts (daily bars, y-axis gutter, date axis).

- [ ] **Step 5: Commit**

```bash
git add web/index.html scripts/phone/checks.mjs scripts/phone/fixtures.mjs
git commit -m "feat(charts): bucketed bars and touch selection with a readout, on Visitors"
```

---

### Task 4: `StackedBars` on Costs, Activity, the home chart and the project cost chart

**Files:**
- Modify: `web/index.html` — `CostsOverview`, `ActivityOverview`, `CrossProjectActivity`, `CostChart`.
- Modify: `scripts/phone/checks.mjs`

**Interfaces:**
- Consumes: `StackedBars` and `ChartReadout` from Task 3 with the exact props listed there; `chartCheck({ name, hash, ready, id, windows })`, `chartBox`, `tapAt` from Task 3's checks; the baseline screenshots in `.playwright-mcp/phone/baseline/` from Task 2.
- Produces: chart ids `costs`, `activity`, `home`, `project-cost`.

**Behaviour:**

1. Each of the four components builds the same `dates`, `byDateSeg` and `segColor` it builds today and renders `<${StackedBars} … />` in place of its inline bar markup. Delete each component's now-unused hover state, scroll ref and scroll effect.
2. Per chart:
   - `CostsOverview`: `id="costs"`, `fmtValue=${fmtUsd}`, `unit=""`.
   - `ActivityOverview`: `id="activity"`, `unit` is the selected metric (`sessions`, `prompts` or `commits`), `fmtValue=${n => n.toLocaleString()}`. Keep its "other" colour folding for projects past the eighth.
   - `CrossProjectActivity` (home): `id="home"`, `unit="prompts"`, `chartH=${120}`, `markToday=${true}`. It has no y-axis gutter today; add a prop `gutter` to `StackedBars` (boolean, default `true`) and pass `gutter=${false}` here so the home chart keeps its full-width look. When a day bucket is today, the readout heading ends with ` so far`, as the tooltip does now.
   - `CostChart` (project page): `id="project-cost"`, `fmtValue=${fmtUsd}`, `unit=""`.
3. The home chart's subtitle reads "prompts per day, stacked by project · tap a bar for that day". On a phone a tap now shows a breakdown first, so render the subtitle as "prompts per day, stacked by project · tap a bar for its breakdown" when `useNarrow()` is true and keep today's wording otherwise.
4. Nothing else about these four pages changes: legends, sort toggles, totals and lists stay as they are.
5. One cleanup carried over from PR A's review: the Visitors "By site" rows reuse `class="list-row"` and then override its `display` with an inline `display: block`. Give them their own `.share-row` class holding only the border and padding they need, and drop the inline override. The `visitors` and `visitors-desktop` checks pin that nothing moves.

- [ ] **Step 1: Write the failing checks**

```js
CHECKS.push(
  chartCheck({ name: 'costs-chart', hash: '#/costs', ready: 'text=By project', id: 'costs',
    windows: [['30d', 30, 30], ['90d', 13, 14], ['1y', 12, 13]] }),
  chartCheck({ name: 'activity-chart', hash: '#/activity', ready: 'text=By project', id: 'activity',
    windows: [['30d', 30, 30], ['90d', 13, 14], ['1y', 12, 13]] }),
  chartCheck({ name: 'home-chart', hash: '#/', ready: 'text=Active projects', id: 'home',
    windows: [['30d', 30, 30], ['7d', 7, 7]] }),
  chartCheck({ name: 'project-cost-chart', hash: '#/project/alpha-app', ready: 'text=Trajectory', id: 'project-cost',
    windows: [['30d', 30, 30]] }),
);
```

The project cost chart's window buttons may differ from `30d`: read `CostChart` and list the windows it actually offers, with the bar counts the bucketing rule gives each. The home chart has two window buttons and other charts on the same page may have buttons with the same label: if `getByRole('button', { name: label })` is ambiguous on a page, extend `chartCheck` to scope the button lookup to the nearest section containing the chart, and say so in the report.

Add desktop assertions to the `home-desktop`, `activity-desktop`, `costs-desktop` and `project-desktop` checks, one block each, following the `visitors-desktop` block from Task 3: a bar per day at every window the page offers, the hover tooltip appears, and a click on the last bar navigates to `#/day/<labDay(0)>`.

Add to the `home` phone check:

```js
      t.ok(await page.getByText('tap a bar for its breakdown').isVisible(), 'home subtitle describes what a tap does on a phone');
```

and to `home-desktop`:

```js
      t.ok(await page.getByText('tap a bar for that day').isVisible(), 'home subtitle is unchanged on desktop');
```

Run: `node scripts/phone/check.mjs`
Expected: the four new chart checks and the new desktop and subtitle assertions FAIL; everything from earlier tasks PASS. Record the output.

- [ ] **Step 2: Convert the four components** per the Behaviour list.

- [ ] **Step 3: Run everything**

Run: `node scripts/phone/check.mjs`
Expected: every check PASS.

Run: `node scripts/test_frontend_pure.mjs && /Users/nico/src/prompt-lab/.venv/bin/python scripts/test_web_api.py 2>&1 | tail -3`
Expected: all pass.

Compare by eye, Read tool, each pair: `.playwright-mcp/phone/baseline/home-desktop.png` against `.playwright-mcp/phone/home-desktop.png`, and the same for `activity`, `costs`, `project`. The charts must look the same on desktop: same bar colours, same stacking order, same axis, same today outline on home. Report any visible difference, however small.

- [ ] **Step 4: Confirm the duplication is gone**

Run: `grep -c "onMouseEnter" web/index.html`
Expected: `2` or fewer — `StackedBars` and `MonitorUptimeCard` (which Task 5 handles). Before this plan there were six. If the number is higher, a chart still carries its own copy of the bar markup.

- [ ] **Step 5: Commit**

```bash
git add web/index.html scripts/phone/checks.mjs
git commit -m "refactor(charts): one StackedBars behind Costs, Activity, home and project cost"
```

---

### Task 5: Health — uptime cards collapse on a phone, and their charts bucket

**Files:**
- Modify: `web/index.html` — a new pure helper inside the `// <pure>` block, `MonitorUptimeCard`, `UptimeArchive`.
- Modify: `scripts/test_frontend_pure.mjs`
- Modify: `scripts/phone/checks.mjs`

**Interfaces:**
- Consumes: `useNarrow`, `bucketSizeFor`, `bucketDates`, `bucketIndexAt`, `ChartReadout`'s visual conventions from Task 3; the `health` fixtures from Task 2.
- Produces: pure helper `bucketUptime(bucket, byDate): { uptime: number|null, ms: number|null, days: number }` where `byDate` is `{ [date]: { uptime: number|null, ms: number|null } }`. `uptime` is the LOWEST uptime among the bucket's days that have one, `ms` is the mean response among days that have one, `days` is how many days had data. A bucket with no data returns `{ uptime: null, ms: null, days: 0 }`.
- Produces test hooks: `data-test="uptime-card"` with `data-monitor=<name>`; `data-test="uptime-toggle"` on the collapsed row; `data-test="uptime-detail"` on the expandable body; `data-chart="uptime-<name>"` on the card's chart, with the same `chart-bars`, `chart-bar`, `chart-readout`, `open-day`, `day-chip` hooks as `StackedBars`.

**Behaviour:**

1. On a narrow screen each uptime card renders collapsed: one row, at least 44px tall, showing the monitor's name, its UP/DOWN badge and its 30d ratio, with a disclosure arrow. Tapping the row expands the card in place to what it shows today; tapping again collapses it. The row is a `button` with `aria-expanded`.
2. On a wide screen every card is expanded, with no toggle, exactly as today.
3. A collapsed card whose 30d ratio is below 100 draws its ratio in the page's existing warning colour, so a problem is visible without expanding anything.
4. The card's chart buckets by the same rule as every other chart (`bucketSizeFor(days, narrow)`). The strip colour of a bucket is `uptimeColor(bucketUptime(...).uptime)`: the worst day decides, because an average would paint a week with one bad day green. The response bar is the mean. A bucket with no data keeps today's grey "not archived" look.
5. Touch selection and the readout follow Task 3's rules. The readout shows the bucket label, `uptime <lowest>%` with the text `lowest of <n> days` when the bucket spans more than one day, and `response <mean>ms`; a bucket with no data shows `not archived`. Then `Open day →` or day chips, as in Task 3.
6. The uptime chart on a narrow screen has no horizontal scroll.

- [ ] **Step 1: Write the failing pure test**

Add `'bucketUptime'` to `NAMES` in `scripts/test_frontend_pure.mjs` and add:

```js
test('bucketUptime: the worst day decides, response is the mean, gaps are not zero', () => {
  const [week] = pure.bucketDates(days('2026-09-07', 7), 'week');
  assert.deepEqual(pure.bucketUptime(week, {
    '2026-09-07': { uptime: 100, ms: 100 },
    '2026-09-08': { uptime: 97.5, ms: 300 },
    '2026-09-09': { uptime: 100, ms: null },      // up, but no response sample
    '2026-09-20': { uptime: 0, ms: 9999 },        // outside the bucket
  }), { uptime: 97.5, ms: 200, days: 3 });
});

test('bucketUptime: no data is null, never 0% and never NaN', () => {
  const [week] = pure.bucketDates(days('2026-09-07', 7), 'week');
  assert.deepEqual(pure.bucketUptime(week, {}), { uptime: null, ms: null, days: 0 });
  assert.deepEqual(pure.bucketUptime(week, { '2026-09-07': { uptime: null, ms: null } }),
    { uptime: null, ms: null, days: 0 });
});

test('bucketUptime: string values from the API are coerced', () => {
  const [day] = pure.bucketDates(['2026-09-07'], 'day');
  assert.deepEqual(pure.bucketUptime(day, { '2026-09-07': { uptime: '99.9', ms: '120' } }),
    { uptime: 99.9, ms: 120, days: 1 });
});
```

Run: `node scripts/test_frontend_pure.mjs`
Expected: FAIL at load with `bucketUptime is not defined`.

- [ ] **Step 2: Implement `bucketUptime`** inside the `// <pure>` block:

```js
    // An uptime bucket takes its WORST day, not its average: averaging paints a
    // week with one bad day green, and a gap in the archive is missing data,
    // never 0% — so days without a reading are skipped, not counted as down.
    function bucketUptime(bucket, byDate) {
      const ups = [], mss = [];
      let days = 0;
      for (const d of bucket.dates) {
        const v = byDate[d];
        if (!v) continue;
        const up = v.uptime == null ? NaN : Number(v.uptime);
        const ms = v.ms == null ? NaN : Number(v.ms);
        if (Number.isFinite(up)) ups.push(up);
        if (Number.isFinite(ms)) mss.push(ms);
        if (Number.isFinite(up) || Number.isFinite(ms)) days++;
      }
      return {
        uptime: ups.length ? Math.min(...ups) : null,
        ms: mss.length ? mss.reduce((s, v) => s + v, 0) / mss.length : null,
        days,
      };
    }
```

Run: `node scripts/test_frontend_pure.mjs`
Expected: all PASS.

- [ ] **Step 3: Write the failing layout checks**

```js
CHECKS.push({
  name: 'health-cards', profile: 'phone', hash: '#/health', ready: 'text=Uptime archive',
  async run(page, t) {
    const cards = page.locator('[data-test="uptime-card"]');
    const n = await cards.count();
    t.ok(n === 12, `twelve uptime cards (${n})`);
    const open = await page.locator('[data-test="uptime-detail"]').evaluateAll(
      (els) => els.filter((e) => e.getBoundingClientRect().height > 0).length);
    t.ok(open === 0, `every card starts collapsed on a phone (${open} open)`);
    const heights = await page.locator('[data-test="uptime-toggle"]').evaluateAll(
      (els) => els.map((e) => Math.round(e.getBoundingClientRect().height)));
    t.ok(heights.every((h) => h >= 44 && h <= 72), `each collapsed row is one tappable line (${Math.min(...heights)}–${Math.max(...heights)}px)`);
    const pageH = await page.evaluate(() => document.documentElement.scrollHeight);
    t.ok(pageH < 844 * 5, `the page is under five screens tall (${(pageH / 844).toFixed(1)})`);

    const first = cards.first();
    const name = await first.getAttribute('data-monitor');
    await first.locator('[data-test="uptime-toggle"]').tap();
    t.ok(await first.locator('[data-test="uptime-detail"]').isVisible(), 'tapping a row expands its card');
    t.ok(await first.locator('[data-test="uptime-toggle"]').getAttribute('aria-expanded') === 'true', 'and says so to assistive tech');

    for (const label of ['90d', '1y']) {
      await page.locator('text=Uptime archive').locator('..').getByRole('button', { name: label, exact: true }).tap();
      await page.waitForTimeout(400);
      const chart = page.locator(`[data-chart="uptime-${name}"]`);
      const scroll = await chart.evaluate((root) => Math.max(0, ...[...root.querySelectorAll('*')]
        .map((e) => e.scrollWidth - e.clientWidth)));
      t.ok(scroll <= 1, `${label}: the uptime chart does not scroll sideways (overflow ${scroll}px)`);
    }
    const chart = page.locator(`[data-chart="uptime-${name}"]`);
    await chart.scrollIntoViewIfNeeded();
    const box = await chartBox(page, `uptime-${name}`);
    await tapAt(page, box.x + box.width - 3, box.y + box.height / 2);
    const text = (await chart.locator('[data-test="chart-readout"]').innerText()).replace(/\s+/g, ' ');
    t.ok(/uptime|not archived/.test(text) && !/NaN|undefined/.test(text), `uptime readout is well formed ("${text.slice(0, 60)}")`);

    await first.locator('[data-test="uptime-toggle"]').tap();
    t.ok(!(await first.locator('[data-test="uptime-detail"]').isVisible()), 'tapping again collapses it');
    const m = await pageOverflow(page);
    t.ok(m.doc <= m.vw, `no horizontal page overflow (${m.doc}px)`);
  },
});
```

If the window buttons of the uptime archive cannot be found with that locator, scope the lookup to the archive section's container and say so in the report.

Add to `health-desktop`:

```js
      const details = await page.locator('[data-test="uptime-detail"]').evaluateAll(
        (els) => els.filter((e) => e.getBoundingClientRect().height > 0).length);
      t.ok(details === 12, `desktop shows every uptime card expanded (${details} of 12)`);
      t.ok(await page.locator('[data-test="uptime-toggle"]').count() === 0
        || !(await page.locator('[data-test="uptime-toggle"]').first().isVisible()), 'desktop has no collapse toggle');
```

Run: `node scripts/phone/check.mjs health health-desktop health-cards`
Expected: `health-cards` and the new desktop assertions FAIL. Record the output.

- [ ] **Step 4: Implement** per the Behaviour list.

- [ ] **Step 5: Run everything**

Run: `node scripts/phone/check.mjs && node scripts/test_frontend_pure.mjs && /Users/nico/src/prompt-lab/.venv/bin/python scripts/test_web_api.py 2>&1 | tail -3`
Expected: all pass.

Compare `.playwright-mcp/phone/baseline/health-desktop.png` against `.playwright-mcp/phone/health-desktop.png` by eye: desktop must look the same. Read `.playwright-mcp/phone/health-cards-phone.png` and confirm the collapsed rows read cleanly and the one expanded during the check rendered its chart.

- [ ] **Step 6: Commit**

```bash
git add web/index.html scripts/test_frontend_pure.mjs scripts/phone/checks.mjs
git commit -m "feat(health): uptime cards collapse on a phone and their charts bucket by worst day"
```

---

### Task 6: One-line header, `WindowPicker`, and 44px tap targets

**Files:**
- Modify: `web/index.html` — header CSS and `Header`; a new `WindowPicker` component placed directly after `PageNote`; every inline window picker; tap-target CSS.
- Modify: `scripts/phone/checks.mjs`

**Interfaces:**
- Consumes: `smallTargets(page)` and the sixteen baseline checks from Task 2; `fixtureOptions.role` from Task 2.
- Produces: `WindowPicker({ days, onChange, options })` — `options` defaults to `[7, 30, 90, 365]`; renders the label `1y` for 365 and `<n>d` otherwise; the selected button has `aria-pressed="true"`. CSS class `win-btn`.

**Behaviour:**

1. Header. On a phone the logo (and, on a project page, the `/` and project picker) sits on the left and the theme toggle and Menu button sit on the right of the same line. The open menu still drops below as a full-width list. On a project page with a long project name the name truncates with an ellipsis rather than pushing the buttons onto a second line. First find out why the row wraps today (read the `header`, `.header-left`, `.header-right` rules and the `@media (max-width: 640px)` block) and fix the cause; do not paper over it with a fixed height.
2. `WindowPicker` replaces the five inline copies of the window buttons (four with `[7, 30, 90, 365]`, one with `[7, 30]` on the home chart). Wide screen: the buttons look as they do today (the home chart's pair is slightly smaller than the others today; after this task all five share the larger style — see the desktop comparison step). Phone: each button is at least 44px tall and 44px wide.
3. On a phone, every tap target covered by the Global Constraints rule is at least 44px tall on every route: theme toggle, Menu button, menu entries, window buttons, sub-tabs (Activity's sessions/prompts/commits), sort toggles, the Todos filter pills, search field, "Show all repos" and "Expand all" links and per-row "project →" links, the day page's back link, the project page's selects and links, the About page's buttons, and Health's re-poll button. Grow the hit area with `min-height` and padding; do not enlarge the text. Where a control sits at the end of a list row, the row may grow taller.
4. Inline links inside running text stay as they are.
5. Desktop sizes do not change, except the home chart's window buttons per item 2.

- [ ] **Step 1: Write the failing checks**

In the `baseline` factory, for the `phone` profile only, add after the existing assertions:

```js
      if (profile === 'phone') {
        const small = await smallTargets(page);
        t.ok(small.length === 0, `every tap target is at least 44px tall (${small.length} too small: ${
          small.slice(0, 6).map((s) => `${s.what} ${s.w}x${s.h}`).join('; ')})`);
        const header = await page.evaluate(() => {
          const h = document.querySelector('header').getBoundingClientRect();
          const logo = document.querySelector('.header-logo').getBoundingClientRect();
          const menu = document.querySelector('.nav-toggle').getBoundingClientRect();
          return { height: Math.round(h.height), sameLine: Math.abs((logo.top + logo.bottom) / 2 - (menu.top + menu.bottom) / 2) < 12,
                   menuRight: Math.round(menu.right), vw: window.innerWidth };
        });
        t.ok(header.sameLine, 'logo and Menu share one line');
        t.ok(header.height <= 76, `header is one line tall (${header.height}px)`);
        t.ok(header.menuRight <= header.vw, `Menu is inside the viewport (right edge ${header.menuRight}px)`);
      }
```

Add the same `smallTargets` assertion to the `visitors` phone check.

Add three checks:

```js
CHECKS.push({
  name: 'header-menu', profile: 'phone', hash: '#/', ready: 'text=Active projects',
  async run(page, t) {
    await page.locator('.nav-toggle').tap();
    const entries = page.locator('.nav-drop.open .header-btn');
    const labels = (await entries.allInnerTexts()).map((s) => s.trim());
    t.ok(['Activity', 'Todos', 'Costs', 'Visitors', 'Health'].every((l) => labels.includes(l)),
      `admin menu lists the five destinations (${labels.join(', ')})`);
    const small = await smallTargets(page);
    t.ok(small.length === 0, `open menu: every entry is at least 44px tall (${small.map((s) => `${s.what} ${s.h}`).join('; ')})`);
    const m = await pageOverflow(page);
    t.ok(m.doc <= m.vw, `open menu: no horizontal page overflow (${m.doc}px)`);
    await page.locator('.nav-drop.open .header-btn', { hasText: 'Costs' }).tap();
    await page.waitForFunction(() => location.hash === '#/costs');
    t.ok(!(await page.locator('.nav-drop.open').isVisible()), 'choosing a destination closes the menu');
  },
});

CHECKS.push({
  name: 'header-reader', profile: 'phone', hash: '#/', ready: 'text=Active projects',
  async before() { fixtureOptions.role = 'reader'; },
  async after() { fixtureOptions.role = 'admin'; },
  async run(page, t) {
    await page.locator('.nav-toggle').tap();
    const labels = (await page.locator('.nav-drop.open .header-btn').allInnerTexts()).map((s) => s.trim());
    t.ok(!labels.includes('Visitors') && !labels.includes('Health'), `a reader is offered no Visitors or Health (${labels.join(', ')})`);
    t.ok(['Activity', 'Todos', 'Costs'].every((l) => labels.includes(l)), 'a reader keeps Activity, Todos and Costs');
  },
});

CHECKS.push({
  name: 'header-long-project', profile: 'phone',
  hash: '#/project/' + encodeURIComponent(LONG_PROJECT), ready: 'text=Trajectory',
  async run(page, t) {
    const header = await page.evaluate(() => {
      const h = document.querySelector('header').getBoundingClientRect();
      const menu = document.querySelector('.nav-toggle').getBoundingClientRect();
      return { height: Math.round(h.height), menuRight: Math.round(menu.right), vw: window.innerWidth };
    });
    t.ok(header.height <= 76, `a 40-character project name does not wrap the header (${header.height}px)`);
    t.ok(header.menuRight <= header.vw, `and Menu stays on screen (right edge ${header.menuRight}px)`);
    const m = await pageOverflow(page);
    t.ok(m.doc <= m.vw, `no horizontal page overflow (${m.doc}px)`);
  },
});
```

`LONG_PROJECT` is the 40-character project name from Task 2's fixtures: export it from `scripts/phone/fixtures.mjs` under that name if it is not already exported, and import it here.

Run: `node scripts/phone/check.mjs`
Expected: the tap-target and header assertions FAIL on most routes with the offending controls named. Record the output.

- [ ] **Step 2: Implement** per the Behaviour list.

- [ ] **Step 3: Run everything**

Run: `node scripts/phone/check.mjs && node scripts/test_frontend_pure.mjs && /Users/nico/src/prompt-lab/.venv/bin/python scripts/test_web_api.py 2>&1 | tail -3`
Expected: all pass.

Compare each desktop screenshot against its baseline by eye (`home`, `activity`, `costs`, `health`, `project`). Expected differences: none, except the home chart's two window buttons, which are now the same size as the other pages'. Report anything else.

Read `home-phone.png`, `todos-phone.png`, `project-phone.png` and `header-long-project-phone.png` and confirm the header is one line and nothing looks oversized or crowded.

- [ ] **Step 4: Confirm the window pickers are one component**

Run: `grep -c "\[7, 30, 90, 365\]" web/index.html`
Expected: `1` (the default in `WindowPicker`).

- [ ] **Step 5: Commit**

```bash
git add web/index.html scripts/phone/checks.mjs scripts/phone/fixtures.mjs
git commit -m "feat(phone): one-line header, shared WindowPicker, 44px tap targets on every route"
```

---

### Task 7: `PageNote` on every page that opens with an explanation

**Files:**
- Modify: `web/index.html` — `ActivityOverview`, `CostsOverview`, `HealthView`, `UptimeArchive`, `CrossProjectActivity`, and the project page's trajectory note (in `ActivityHeatmap`).
- Modify: `scripts/phone/checks.mjs`

**Interfaces:**
- Consumes: `PageNote({ summary, children })` from PR A, with its hooks `data-test="page-note"` (phone disclosure) and `data-test="page-note-wide"` (desktop copy).

**Behaviour:**

1. Wrap each page's standing explanation in `<${PageNote}>…<//>`, text and inline styles unchanged:
   - Activity: the paragraph beginning "Sessions, prompts and commits per day".
   - Costs: the paragraph beginning "API spend across all projects".
   - Health: the paragraph beginning "Live poll of each target's health endpoint".
   - Uptime archive: the paragraph beginning "What UptimeRobot saw".
   - Home chart: the note beginning "Today (outlined) fills in". The one-line subtitle above it stays visible.
   - Project page: the trajectory note beginning "Counts before 2026-08-14".
   Footnotes that sit below a list (Activity's "Bar is each project's share" and "All three over the last 30 days") stay as they are: they are under the data, not in front of it.
2. Use a `summary` that says what is behind it where the default is vague: `About these counts` for the trajectory note, `About this chart` for the home chart note. The default `About this data` fits the rest.
3. Health's "Health emails paused until …" banner is a status, not an explanation. It stays visible.
4. Negative margins that pull a note up under its paragraph must not make blocks overlap inside the phone disclosure. PR A's `.page-note-narrow > div` rule resets them; extend it if a note uses another element.

- [ ] **Step 1: Write the failing checks**

Add to the `baseline` factory, with a per-route expectation:

```js
const NOTES = { home: 1, activity: 1, costs: 1, health: 2, project: 1, about: 0, day: 0, todos: 0 };
```

```js
      const base = name;                       // route name without the profile suffix
      const want = NOTES[base];
      if (profile === 'phone') {
        const notes = page.locator('[data-test="page-note"]');
        const n = await notes.count();
        t.ok(n === want, `${want} collapsed page note(s) (${n})`);
        const openNow = await notes.evaluateAll((els) => els.filter((e) => e.open).length);
        t.ok(openNow === 0, `notes start collapsed (${openNow} open)`);
        for (let i = 0; i < n; i++) {
          await notes.nth(i).locator('summary').tap();
          const overlap = await notes.nth(i).evaluate((d) => {
            const kids = [...d.children].filter((c) => c.tagName !== 'SUMMARY').map((c) => c.getBoundingClientRect());
            return kids.some((r, k) => k > 0 && r.top < kids[k - 1].bottom - 1);
          });
          t.ok(!overlap, `note ${i + 1}: its blocks do not overlap when expanded`);
        }
        const m2 = await pageOverflow(page);
        t.ok(m2.doc <= m2.vw, `no horizontal page overflow with notes expanded (${m2.doc}px)`);
      } else {
        const wide = await page.locator('[data-test="page-note-wide"]').evaluateAll(
          (els) => els.filter((e) => e.getBoundingClientRect().height > 0).length);
        t.ok(wide === want, `desktop shows ${want} explanation(s) in full (${wide})`);
        t.ok(!(await page.locator('[data-test="page-note"]').first().isVisible().catch(() => false)),
          'desktop has no disclosure');
      }
```

If a page's note count differs from `NOTES` after you have wrapped exactly the blocks the Behaviour list names, correct `NOTES` to match the Behaviour list and say so in the report. Do not change which blocks are wrapped to fit the number.

Add to the `health` phone check:

```js
      t.ok(await page.getByText(/Health emails paused/).isVisible(), 'the paused-emails status stays visible on a phone');
```

The `health_report` fixture must include a paused state for this; add it to the fixture if Task 2 did not.

Run: `node scripts/phone/check.mjs`
Expected: the note assertions FAIL (0 notes found). Record the output.

- [ ] **Step 2: Wrap the explanations** per the Behaviour list.

- [ ] **Step 3: Run everything**

Run: `node scripts/phone/check.mjs && node scripts/test_frontend_pure.mjs && /Users/nico/src/prompt-lab/.venv/bin/python scripts/test_web_api.py 2>&1 | tail -3 && /Users/nico/src/prompt-lab/.venv/bin/ruff check . --exclude .venv`
Expected: all pass.

Compare each desktop screenshot against its baseline by eye: the explanations must sit where they did, with the same spacing above and below.

- [ ] **Step 4: Commit**

```bash
git add web/index.html scripts/phone/checks.mjs scripts/phone/fixtures.mjs
git commit -m "feat(phone): page explanations collapse behind one line on every route"
```

---

### Task 8: Four phone overflows the new fixtures exposed (runs directly after Task 2)

Added during execution. Task 2's fixtures use a 40-character project name and a project with a site link, and with them four routes overflow a 390px viewport: `home` (529px), `todos` (532px), `day` (485px) and `project` (416px). Real project names are short, which is why the walk with real data did not show it.

**Files:**
- Modify: `web/index.html`
- Modify: `scripts/phone/checks.mjs` only if an assertion needs adding; never to loosen one.

**Interfaces:**
- Consumes: the `home`, `todos`, `day`, `project` baseline checks and their `-desktop` twins from Task 2; `LONG_PROJECT`; the baseline screenshots in `.playwright-mcp/phone/baseline/`.
- Produces: nothing new. Four failing checks turn green.

**Behaviour:**

1. The home stream row, the Todos project row, the day card header and the project header row each fit a 390px viewport with a 40-character unbroken project name and a site link.
2. Fix the cause in each: a flex or grid child that cannot shrink (`min-width: 0`), text that cannot wrap (`overflow-wrap: anywhere`) or that should truncate with an ellipsis. A long name wraps where the name is the row's content (stream row, day card header, Todos row) and truncates where it is a label beside controls. Do not hide overflow on a page-level container to mask it.
3. Counts and controls at the end of a row stay fully visible.
4. Desktop does not change: compare each desktop screenshot against its baseline.

- [ ] **Step 1: RED.** Run `node scripts/phone/check.mjs home todos day project` and record the four overflow failures with their measured widths.
- [ ] **Step 2:** For each route, find the element that sets the width (in the page, the widest element whose right edge passes the viewport and that is not inside a horizontal scroller) and fix its cause per Behaviour item 2.
- [ ] **Step 3: GREEN.** Run `node scripts/phone/check.mjs`. Expected: every check passes.
- [ ] **Step 4:** Read the four phone screenshots and confirm the long name is readable and nothing is cut off. Compare `home-desktop.png` and `project-desktop.png` against `.playwright-mcp/phone/baseline/`; report any difference. Re-save the baseline copies afterwards, so later tasks compare against the fixed pages.
- [ ] **Step 5:** Run `node scripts/test_frontend_pure.mjs`, the Python suite and ruff. Commit:

```bash
git add web/index.html
git commit -m "fix(phone): four rows that overflowed on a long project name or a site link"
```
