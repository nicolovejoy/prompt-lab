// Layout checks. Each entry loads one route under one device profile.
// t.ok(condition, message) records an assertion; the runner prints them.

import { LONG_HOST, LONG_PATH, fixtureOptions, labDay } from './fixtures.mjs';

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
