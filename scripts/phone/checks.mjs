// Layout checks. Each entry loads one route under one device profile.
// t.ok(condition, message) records an assertion; the runner prints them.

import { LONG_HOST, LONG_PATH, LONG_PROJECT, apiFixture, fixtureOptions, labDay } from './fixtures.mjs';

export async function pageOverflow(page) {
  return page.evaluate(() => ({
    doc: document.documentElement.scrollWidth,
    vw: window.innerWidth,
  }));
}

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

export const CHECKS = [
  {
    name: 'visitors',
    profile: 'phone',
    hash: '#/visitors',
    ready: 'text=By site',
    async run(page, t) {
      const m = await pageOverflow(page);
      t.ok(m.doc <= m.vw, `no horizontal page overflow (document ${m.doc}px, viewport ${m.vw}px)`);

      // Every count must be on screen: the bug put them all off the right edge.
      const values = await page.locator('.list-row-value, [data-test="share-row"] [data-test="share-value"]').evaluateAll(
        (els) => els.map((e) => Math.round(e.getBoundingClientRect().right)));
      t.ok(values.length > 0, `found list counts to measure (${values.length})`);
      t.ok(values.every((r) => r <= m.vw), `every count ends inside the viewport (max right edge ${Math.max(0, ...values)}px)`);

      const rows = page.locator('[data-test="by-site"] [data-test="share-row"]');
      const rowCount = await rows.count();
      const barCount = await page.locator('[data-test="by-site"] [data-test="share-bar"]').count();
      t.ok(rowCount === 6, `By site lists all 6 fixture sites (${rowCount})`);
      t.ok(barCount === rowCount, `each By site row has a share bar (${barCount} of ${rowCount})`);

      // A 70-character token with no break points must wrap, not clip.
      for (const [label, text] of [['host', LONG_HOST], ['path', LONG_PATH]]) {
        const box = await page.getByText(text, { exact: true }).first().evaluate((e) => {
          const r = e.getBoundingClientRect();
          return { right: Math.round(r.right), clipped: e.scrollWidth > e.clientWidth + 1 };
        });
        t.ok(box.right <= m.vw && !box.clipped, `long ${label} wraps inside the viewport (right ${box.right}px, clipped ${box.clipped})`);
      }

      const previews = page.locator('[data-test="share-row"]', { hasText: 'previews' });
      t.ok((await previews.innerText()).includes('4 preview hosts'), 'previews row says how many hosts it folds');

      const visible = async (sel) => page.locator(sel).first().isVisible();
      t.ok(await visible('[data-test="visitors-tabs"]'), 'tab bar is visible on a phone');
      t.ok(await visible('[data-test="panel-pages"]'), 'Pages is the default list');
      t.ok(!(await visible('[data-test="panel-referrers"]')) && !(await visible('[data-test="panel-countries"]')),
        'the other two lists are hidden until chosen');

      const tabHeights = await page.locator('[data-test="visitors-tabs"] button').evaluateAll(
        (els) => els.map((e) => Math.round(e.getBoundingClientRect().height)));
      t.ok(tabHeights.length === 3 && tabHeights.every((h) => h >= 44), `tabs are at least 44px tall (${tabHeights.join(', ')})`);
      const tabsBox = await page.locator('[data-test="visitors-tabs"]').evaluate(
        (e) => ({ scroll: e.scrollWidth, client: e.clientWidth }));
      t.ok(tabsBox.scroll <= tabsBox.client + 1, `all three tabs fit without scrolling (${tabsBox.scroll} in ${tabsBox.client}px)`);

      // aria-pressed, not tab roles: on desktop all three lists show at once, so
      // the buttons are toggles for a phone view, not a true tablist.
      const pressed = () => page.locator('[data-test="visitors-tabs"] button[aria-pressed="true"]').evaluateAll(
        (els) => els.map((e) => e.dataset.test));
      const pressedBefore = await pressed();
      t.ok(pressedBefore.length === 1 && pressedBefore[0] === 'tab-pages',
        `exactly one tab is pressed, Pages by default (${pressedBefore.join(', ') || 'none'})`);
      await page.locator('[data-test="tab-referrers"]').tap();
      t.ok(await visible('[data-test="panel-referrers"]') && !(await visible('[data-test="panel-pages"]')),
        'tapping Referrers swaps the list');
      const pressedAfter = await pressed();
      t.ok(pressedAfter.length === 1 && pressedAfter[0] === 'tab-referrers',
        `pressed state follows the tap (${pressedAfter.join(', ') || 'none'})`);
      await page.locator('[data-test="tab-countries"]').tap();
      t.ok(await visible('[data-test="panel-countries"]'), 'tapping Countries shows countries');
      const after = await pageOverflow(page);
      t.ok(after.doc <= after.vw, `still no page overflow after switching tabs (${after.doc}px)`);

      const note = page.locator('[data-test="page-note"]');
      t.ok(await note.isVisible(), 'page note disclosure is visible on a phone');
      // Scoped to the disclosure: the wide copy of the same text is always in the DOM.
      t.ok(!(await note.getByText('cookie-less', { exact: false }).isVisible()), 'explanation is collapsed by default');
      const summaryHeight = await note.locator('summary').evaluate((e) => Math.round(e.getBoundingClientRect().height));
      t.ok(summaryHeight >= 44, `disclosure is at least 44px tall (${summaryHeight})`);
      // flex on summary drops the native triangle, so the chevron is the only sign it opens.
      const chevron = () => note.locator('summary').evaluate((e) => {
        const cs = getComputedStyle(e, '::after');
        return { content: cs.content, transform: cs.transform };
      });
      const closedChevron = await chevron();
      t.ok(!['none', 'normal', ''].includes(closedChevron.content), `disclosure shows a chevron (content ${closedChevron.content})`);
      await note.locator('summary').tap();
      t.ok(await note.getByText('cookie-less', { exact: false }).isVisible(), 'tapping it shows the explanation');
      const openChevron = await chevron();
      t.ok(openChevron.transform !== closedChevron.transform,
        `chevron turns when opened (${closedChevron.transform} -> ${openChevron.transform})`);
      // Wrapped blocks bring inline margins written for the wide layout; inside the
      // disclosure they must stack below the summary with an even 12px between them.
      const noteBoxes = await note.evaluate((d) => {
        const box = (e) => { const r = e.getBoundingClientRect(); return { top: r.top, bottom: r.bottom }; };
        return {
          summary: box(d.querySelector(':scope > summary')),
          blocks: [...d.children].filter((e) => e.tagName !== 'SUMMARY').map(box),
        };
      });
      t.ok(noteBoxes.blocks.length >= 2 && noteBoxes.blocks[0].top >= noteBoxes.summary.bottom - 0.5,
        `first note block starts below the summary (${noteBoxes.blocks.length} blocks, top ${Math.round(noteBoxes.blocks[0]?.top)}, summary bottom ${Math.round(noteBoxes.summary.bottom)})`);
      const gaps = noteBoxes.blocks.slice(1).map((b, i) => Math.round((b.top - noteBoxes.blocks[i].bottom) * 10) / 10);
      t.ok(gaps.length > 0 && gaps.every((g) => Math.abs(g - 12) <= 1), `note blocks are 12px apart (${gaps.join(', ')})`);
      const small = await smallTargets(page);
      t.ok(small.length === 0, `every tap target is at least 44px tall (${small.length} too small: ${
        small.slice(0, 6).map((s) => `${s.what} ${s.w}x${s.h}`).join('; ')})`);
    },
  },
  {
    name: 'visitors-old-payload',
    profile: 'phone',
    hash: '#/visitors',
    ready: 'text=By site',
    async before() { fixtureOptions.omitPreviewHosts = true; },
    async after() { fixtureOptions.omitPreviewHosts = false; },
    async run(page, t) {
      const text = await page.locator('[data-test="share-row"]', { hasText: 'previews' }).innerText();
      t.ok(!/undefined|NaN/.test(text), `previews row renders without preview_hosts ("${text.replace(/\s+/g, ' ')}")`);
      t.ok(!/preview hosts/.test(text), 'previews row shows no host count when the payload has none');
    },
  },
  {
    name: 'visitors-no-referrers',
    profile: 'phone',
    hash: '#/visitors',
    ready: 'text=By site',
    async before() { fixtureOptions.noReferrers = true; },
    async after() { fixtureOptions.noReferrers = false; },
    async run(page, t) {
      await page.locator('[data-test="tab-referrers"]').tap();
      const panel = page.locator('[data-test="panel-referrers"]');
      t.ok(await panel.isVisible(), 'Referrers panel shows when chosen');
      t.ok((await panel.innerText()).includes('None yet.'), 'an empty list says "None yet." rather than showing nothing');
    },
  },
  {
    name: 'visitors-desktop',
    profile: 'desktop',
    hash: '#/visitors',
    ready: 'text=By site',
    async run(page, t) {
      const m = await pageOverflow(page);
      t.ok(m.doc <= m.vw, `no horizontal page overflow (document ${m.doc}px, viewport ${m.vw}px)`);
      // One-line rows on a wide screen: label and sub-label share a baseline.
      const row = page.locator('.list-row', { hasText: '/dashboard' }).first();
      const tops = await row.locator('.list-row-label, .list-row-sub').evaluateAll(
        (els) => els.map((e) => Math.round(e.getBoundingClientRect().bottom)));
      t.ok(tops.length === 2 && Math.abs(tops[0] - tops[1]) <= 4, `label and sub-label sit on one line (bottoms ${tops.join(', ')})`);

      // Desktop By site rows stay vertically centred; only a phone top-aligns them.
      // 1px, not 3: top-aligning moved the smaller share text by exactly 3px.
      const share = page.locator('[data-test="share-row"]').first();
      const mids = await share.locator('.list-row-label, [data-test="share-pct"], [data-test="share-value"]').evaluateAll(
        (els) => els.map((e) => { const r = e.getBoundingClientRect(); return Math.round(r.top + r.height / 2); }));
      t.ok(mids.length === 3 && Math.max(...mids) - Math.min(...mids) <= 1,
        `By site name, share and count are centred on one line (centres ${mids.join(', ')})`);

      const shown = async (sel) => page.locator(sel).first().isVisible();
      t.ok(!(await shown('[data-test="visitors-tabs"]')), 'tab bar is hidden on desktop');
      t.ok(await shown('[data-test="panel-pages"]') && await shown('[data-test="panel-referrers"]')
        && await shown('[data-test="panel-countries"]'), 'all three lists show at once on desktop');
      t.ok(await shown('[data-test="page-note-wide"]') && !(await shown('[data-test="page-note"]')),
        'desktop shows the explanation in full, no disclosure');
      for (const title of ['Top pages', 'Referrers', 'Countries']) {
        t.ok(await page.locator('[data-test^="panel-"]').getByText(title, { exact: true }).first().isVisible(),
          `desktop keeps the "${title}" heading`);
      }

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
      // Back to the chart, so this check's screenshot is the Visitors page:
      // it is the desktop baseline later chart work is compared against.
      await page.goBack();
      await page.locator('text=By site').first().waitFor();
      await page.mouse.move(0, 0);   // no bar left highlighted in the shot
    },
  },
];

// One baseline per route and profile. Each `ready` selector waits on
// something that only renders once the route's own data has arrived, so a
// check never measures a skeleton or a loading placeholder. The obvious
// labels ("Active projects", "back", "Uptime archive") render before the data
// does, or on the error path, so they are not used.
const ROUTES = [
  ['home', '#/', '.timeline-entry'],                   // the stream needs /api/overview
  ['activity', '#/activity', 'text=By project'],
  ['costs', '#/costs', 'text=By project'],
  ['todos', '#/todos', 'text=open across'],
  ['health', '#/health', 'text=Reading the strip'],    // needs the report AND the archive
  ['about', '#/about', 'text=Ask a question'],         // needs the admin login
  ['day', '#/day/' + labDay(1), 'text=API spend'],
  ['project', '#/project/alpha-app', 'text=API cost'], // needs the project AND its costs
];

function baseline([name, hash, ready], profile) {
  const checkName = profile === 'phone' ? name : `${name}-${profile}`;
  return {
    name: checkName,
    profile, hash, ready,
    async run(page, t) {
      const m = await pageOverflow(page);
      t.ok(m.doc <= m.vw, `no horizontal page overflow (document ${m.doc}px, viewport ${m.vw}px)`);
      const errors = await page.evaluate(() => /Couldn't load|no fixture for/.test(document.body.innerText));
      t.ok(!errors, 'page rendered its data, not an error placeholder');
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
      await BASELINE_EXTRA[checkName]?.(page, t, ready);
    },
  };
}

// Route-specific assertions riding on a baseline check, keyed by check name.
// Filled in below, next to the chart checks they belong with.
const BASELINE_EXTRA = {};

CHECKS.push(...ROUTES.flatMap((r) => [baseline(r, 'phone'), baseline(r, 'desktop')]));

// Drive a chart the way a thumb does. Returns the bar-row box.
async function chartBox(page, id) {
  return page.locator(`[data-chart="${id}"] [data-test="chart-bars"]`).boundingBox();
}
async function tapAt(page, x, y) { await page.touchscreen.tap(x, y); }

// A window button, looked up inside the innermost element holding both the
// chart and a button with that label: the home page and the project page carry
// more than one chart, and a bare label could name another chart's button.
function windowButton(page, id, label) {
  const button = () => page.getByRole('button', { name: label, exact: true });
  return page.locator('div')
    .filter({ has: page.locator(`[data-chart="${id}"]`) })
    .filter({ has: button() })
    .last()
    .getByRole('button', { name: label, exact: true });
}

// `picker: false` is a chart with one fixed window and no buttons (the
// project page's cost chart): its single entry is checked as it loads.
function chartCheck({ name, hash, ready, id, windows, picker = true }) {
  return {
    name, profile: 'phone', hash, ready,
    async run(page, t) {
      for (const [label, expectMin, expectMax] of windows) {
        if (picker) await windowButton(page, id, label).tap();
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

    // Cleared, not hidden: rotating back must not bring the old week back.
    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForTimeout(400);
    t.ok(!(await chart.locator('[data-test="chart-readout"]').isVisible()), 'rotating back does not restore the readout');
    const back = await chart.locator('[data-test="chart-bar"][data-selected="true"]').count();
    t.ok(back === 0, `rotating back leaves no bar selected (${back})`);

    // Same for a window round trip: a cached window keeps the chart mounted.
    const again = await chartBox(page, 'visitors');
    await tapAt(page, again.x + again.width / 2, again.y + again.height / 2);
    t.ok(await chart.locator('[data-test="chart-readout"]').isVisible(), 'a weekly bucket is selected again');
    await page.getByRole('button', { name: '30d', exact: true }).tap();
    await page.waitForTimeout(400);
    await page.getByRole('button', { name: '90d', exact: true }).tap();
    await page.waitForTimeout(400);
    const round = await chart.locator('[data-test="chart-bar"][data-selected="true"]').count();
    t.ok(round === 0 && !(await chart.locator('[data-test="chart-readout"]').isVisible()),
      `90d -> 30d -> 90d leaves nothing selected (${round} selected)`);
  },
});

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

// Playwright's touchscreen can only tap, so a drag is dispatched as the
// pointer events the chart listens to. Each case starts from a fresh load.
CHECKS.push({
  name: 'visitors-chart-drag', profile: 'phone', hash: '#/visitors', ready: 'text=By site',
  async run(page, t) {
    const chart = page.locator('[data-chart="visitors"]');
    const fresh = async () => {
      await page.reload();
      await page.locator('text=By site').first().waitFor();
      await chart.scrollIntoViewIfNeeded();
      const n = await chart.locator('[data-test="chart-bar"][data-selected="true"]').count();
      return { box: await chartBox(page, 'visitors'), none: n === 0 };
    };
    const send = (steps) => chart.locator('[data-test="chart-bars"]').evaluate((row, steps) => {
      for (const [type, clientX, clientY] of steps) {
        row.dispatchEvent(new PointerEvent(type, {
          pointerType: 'touch', pointerId: 1, clientX, clientY, bubbles: true, isPrimary: true,
        }));
      }
    }, steps);
    // Settle the render before reading, then name the bar drawn as selected
    // and the bar under an x, both by data-key.
    const selectedKey = async () => {
      await page.waitForTimeout(100);
      const sel = chart.locator('[data-test="chart-bar"][data-selected="true"]');
      return (await sel.count()) === 1 ? sel.getAttribute('data-key') : null;
    };
    const keyAt = (x) => chart.locator('[data-test="chart-bar"]').evaluateAll((bars, x) => {
      const hit = bars.find((b) => { const r = b.getBoundingClientRect(); return x >= r.left && x < r.right; });
      return hit ? hit.dataset.key : null;
    }, x);

    // 1. A horizontal drag scrubs: the selection follows to where it ends.
    let { box, none } = await fresh();
    let y = box.y + box.height / 2;
    let x0 = box.x + box.width * 0.25 + 2, x1 = box.x + box.width * 0.75 + 2;
    await send([['pointerdown', x0, y], ['pointermove', x1, y], ['pointerup', x1, y]]);
    let want = await keyAt(x1), got = await selectedKey();
    t.ok(none && want && got === want && want !== await keyAt(x0),
      `a horizontal drag selects the bar under its end (${got}, expected ${want})`);

    // 2. A drag that drifts 30px down is a scroll: the selection stays put.
    ({ box, none } = await fresh());
    y = box.y + box.height / 2;
    x0 = box.x + box.width * 0.25 + 2;
    await send([['pointerdown', x0, y], ['pointermove', x0 + 80, y + 30]]);
    want = await keyAt(x0); got = await selectedKey();
    t.ok(none && want && got === want && want !== await keyAt(x0 + 80),
      `a vertical drift keeps the bar under pointerdown (${got}, expected ${want})`);

    // 3. ...and for the rest of that gesture, even back on the original line.
    await send([['pointermove', x0 + 160, y], ['pointerup', x0 + 160, y]]);
    got = await selectedKey();
    t.ok(got === want, `after drifting, the gesture no longer moves the selection (${got}, expected ${want})`);

    // 4. pointercancel (the browser taking the gesture) ends following too.
    ({ box, none } = await fresh());
    y = box.y + box.height / 2;
    x0 = box.x + box.width * 0.25 + 2;
    await send([['pointerdown', x0, y], ['pointercancel', x0, y], ['pointermove', x0 + 120, y]]);
    want = await keyAt(x0); got = await selectedKey();
    t.ok(none && want && got === want && want !== await keyAt(x0 + 120),
      `after pointercancel a move does not change the selection (${got}, expected ${want})`);
  },
});

// The four charts that moved onto StackedBars after Visitors. The window
// buttons each page offers, with the bars a phone draws for each.
CHECKS.push(
  chartCheck({ name: 'costs-chart', hash: '#/costs', ready: 'text=By project', id: 'costs',
    windows: [['30d', 30, 30], ['90d', 13, 14], ['1y', 12, 13], ['7d', 7, 7]] }),
  chartCheck({ name: 'activity-chart', hash: '#/activity', ready: 'text=By project', id: 'activity',
    windows: [['30d', 30, 30], ['90d', 13, 14], ['1y', 12, 13], ['7d', 7, 7]] }),
  chartCheck({ name: 'home-chart', hash: '#/', ready: '.timeline-entry', id: 'home',
    windows: [['30d', 30, 30], ['7d', 7, 7]] }),
  // The project page's cost chart has one fixed 30-day window and no buttons.
  chartCheck({ name: 'project-cost-chart', hash: '#/project/alpha-app', ready: 'text=API cost', id: 'project-cost',
    windows: [['30d', 30, 30]], picker: false }),
);

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const shortDate = (iso) => MONTHS[Number(iso.slice(5, 7)) - 1] + ' ' + Number(iso.slice(8));

// Today's bar on the home chart is still filling in; its readout says so, as
// the desktop tooltip always has, and yesterday's does not.
CHECKS.push({
  name: 'home-chart-today', profile: 'phone', hash: '#/', ready: '.timeline-entry',
  async run(page, t) {
    const chart = page.locator('[data-chart="home"]');
    await chart.scrollIntoViewIfNeeded();
    const head = chart.locator('.chart-readout-head');
    const box = await chartBox(page, 'home');
    await tapAt(page, box.x + box.width - 3, box.y + box.height / 2);
    const today = await head.innerText();
    t.ok(today.startsWith(shortDate(labDay(0)) + ' · ') && today.endsWith(' prompts so far'),
      `today's readout ends "so far" ("${today}")`);
    const yesterday = await chart.locator(`[data-test="chart-bar"][data-key="${labDay(1)}"]`).boundingBox();
    await tapAt(page, yesterday.x + yesterday.width / 2, box.y + box.height / 2);
    const prev = await head.innerText();
    t.ok(prev.startsWith(shortDate(labDay(1)) + ' · ') && !/so far/.test(prev),
      `yesterday's readout does not ("${prev}")`);
  },
});

// Desktop keeps the old chart: a bar per day at every window, a hover tooltip,
// and a click that opens the day. `windows` ends on the page's default, so the
// check's screenshot is the page as it loads.
function desktopChart(id, windows, tip) {
  return async (page, t, ready) => {
    const chart = page.locator(`[data-chart="${id}"]`);
    for (const [label, n] of windows) {
      if (label) await windowButton(page, id, label).click();
      await page.waitForTimeout(400);
      const bars = await chart.locator('[data-test="chart-bar"]').count();
      t.ok(bars === n, `desktop ${label || 'chart'}: a bar per day (${bars}, expected ${n})`);
    }
    const heading = chart.getByText(new RegExp('^' + shortDate(labDay(0)) + ' · '));
    t.ok(!(await heading.first().isVisible()), 'desktop: no tooltip before hovering');
    const last = chart.locator('[data-test="chart-bar"]').last();
    await last.hover();
    const text = (await heading.first().isVisible()) ? await heading.first().innerText() : '';
    t.ok(tip.test(text), `desktop: hovering the newest bar shows its tooltip ("${text}")`);
    await last.click();
    await page.waitForFunction(() => location.hash.startsWith('#/day/'));
    t.ok(page.url().endsWith('#/day/' + labDay(0)), 'desktop: clicking the newest bar opens today');
    await page.goBack();
    await page.locator(ready).first().waitFor();
    await page.mouse.move(0, 0);   // no bar left highlighted in the shot
  };
}

BASELINE_EXTRA['costs-desktop'] = desktopChart('costs',
  [['7d', 7], ['90d', 90], ['1y', 365], ['30d', 30]], /^\w{3} \d+ · \$[\d,]+\.\d\d$/);
BASELINE_EXTRA['activity-desktop'] = async (page, t, ready) => {
  await desktopChart('activity', [['7d', 7], ['90d', 90], ['1y', 365], ['30d', 30]], / sessions$/)(page, t, ready);
  // The unit follows the metric sub-tab.
  await page.locator('.sub-tab', { hasText: 'commits' }).click();
  await page.waitForTimeout(400);
  const chart = page.locator('[data-chart="activity"]');
  await chart.locator('[data-test="chart-bar"]').last().hover();
  const tipText = await chart.getByText(new RegExp('^' + shortDate(labDay(0)) + ' · ')).first().innerText();
  t.ok(/ commits$/.test(tipText), `desktop: the tooltip's unit follows the metric ("${tipText}")`);
  await page.locator('.sub-tab', { hasText: 'sessions' }).click();
  await page.locator(ready).first().waitFor();
  await page.mouse.move(0, 0);
};
BASELINE_EXTRA['home-desktop'] = async (page, t, ready) => {
  t.ok(await page.getByText('tap a bar for that day').isVisible(), 'home subtitle is unchanged on desktop');
  await desktopChart('home', [['7d', 7], ['30d', 30]], / prompts so far$/)(page, t, ready);
};
// A project's daily spend is often under a cent, so its amounts keep four
// decimals; "$0.00" for real spend reads as none.
BASELINE_EXTRA['project-desktop'] = async (page, t, ready) => {
  await desktopChart('project-cost', [[null, 30]], /^\w{3} \d+ · \$[\d,]+\.\d{4}$/)(page, t, ready);

  // "last 30d" is the 30 days the chart draws, and the per-model legend adds up
  // to it. The fetch's `since` is inclusive and returns a 31st day, which the
  // chart does not draw and the total must not count.
  const { body } = apiFixture('/api/cost_timeline',
    new URLSearchParams({ project: 'alpha-app', since: labDay(30) }), 'GET');
  const drawn = body.costs.filter((r) => r.date >= labDay(29)).reduce((s, r) => s + r.cost_usd, 0);
  const money = (s) => Number(s.replace(/[^\d.]/g, ''));
  const total = money(await page.locator('[data-test="cost-total"]').innerText());
  t.ok(total === Number(drawn.toFixed(2)), `cost total is the 30 days drawn ($${total}, expected $${drawn.toFixed(2)})`);
  const legend = await page.locator('[data-test="cost-legend"] span').allInnerTexts();
  const sum = legend.reduce((s, x) => s + money(x.split(':').pop()), 0);
  t.ok(legend.length > 0 && Math.abs(sum - total) < 0.005 * legend.length + 1e-9,
    `per-model legend sums to the total ($${sum.toFixed(2)} over ${legend.length} models, total $${total})`);
};

CHECKS.push({
  name: 'project-cost-chart-fine', profile: 'phone', hash: '#/project/alpha-app', ready: 'text=API cost',
  async run(page, t) {
    const chart = page.locator('[data-chart="project-cost"]');
    await chart.scrollIntoViewIfNeeded();
    const box = await chartBox(page, 'project-cost');
    await tapAt(page, box.x + box.width - 3, box.y + box.height / 2);
    const head = await chart.locator('.chart-readout-head').innerText();
    const values = await chart.locator('.chart-readout-value').allInnerTexts();
    t.ok(/ · \$[\d,]+\.\d{4}$/.test(head), `readout total has four decimals ("${head}")`);
    t.ok(values.length > 0 && values.every((v) => /^\$[\d,]+\.\d{4}$/.test(v)),
      `readout amounts have four decimals (${values.join(', ')})`);
  },
});
BASELINE_EXTRA.home = async (page, t) => {
  t.ok(await page.getByText('tap a bar for its breakdown').isVisible(), 'home subtitle describes what a tap does on a phone');
};

// Twelve uptime cards, each fully expanded with its own chart, made Health
// more than eight screens long on a phone. There they collapse to one row
// each, and the chart inside an opened card buckets like every other chart.
CHECKS.push({
  name: 'health-cards', profile: 'phone', hash: '#/health', ready: 'text=Reading the strip',
  async run(page, t) {
    const cards = page.locator('[data-test="uptime-card"]');
    const n = await cards.count();
    t.ok(n === 12, `twelve uptime cards (${n})`);
    const open = await page.locator('[data-test="uptime-detail"]').evaluateAll(
      (els) => els.filter((e) => e.getBoundingClientRect().height > 0).length);
    t.ok(open === 0, `every card starts collapsed on a phone (${open} open)`);
    const heights = await page.locator('[data-test="uptime-toggle"]').evaluateAll(
      (els) => els.map((e) => Math.round(e.getBoundingClientRect().height)));
    t.ok(heights.length === 12 && heights.every((h) => h >= 44 && h <= 72), `each collapsed row is one tappable line (${Math.min(...heights)}–${Math.max(...heights)}px)`);
    const pageH = await page.evaluate(() => document.documentElement.scrollHeight);
    t.ok(pageH < 844 * 5, `the page is under five screens tall (${pageH}px, ${(pageH / 844).toFixed(1)} screens)`);

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

// A wide screen keeps every card open, as it always was.
BASELINE_EXTRA['health-desktop'] = async (page, t, ready) => {
  const details = await page.locator('[data-test="uptime-detail"]').evaluateAll(
    (els) => els.filter((e) => e.getBoundingClientRect().height > 0).length);
  t.ok(details === 12, `desktop shows every uptime card expanded (${details} of 12)`);
  t.ok(await page.locator('[data-test="uptime-toggle"]').count() === 0
    || !(await page.locator('[data-test="uptime-toggle"]').first().isVisible()), 'desktop has no collapse toggle');
  const chart = page.locator('[data-test="uptime-card"]').first().locator('[data-test="chart"]');
  const bars = await chart.locator('[data-test="chart-bar"]').count();
  t.ok(bars === 30, `desktop uptime chart: a column per day (${bars})`);
  await chart.locator('[data-test="chart-bar"]').last().click();
  await page.waitForFunction(() => location.hash.startsWith('#/day/'));
  t.ok(page.url().endsWith('#/day/' + labDay(0)), 'desktop: clicking an uptime column opens that day');
  await page.goBack();
  await page.locator(ready).first().waitFor();
  await page.mouse.move(0, 0);
};

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
