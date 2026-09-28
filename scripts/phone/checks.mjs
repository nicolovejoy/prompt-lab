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
