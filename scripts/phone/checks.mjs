// Layout checks. Each entry loads one route under one device profile.
// t.ok(condition, message) records an assertion; the runner prints them.

import { LONG_HOST, LONG_PATH, fixtureOptions } from './fixtures.mjs';

export async function pageOverflow(page) {
  return page.evaluate(() => ({
    doc: document.documentElement.scrollWidth,
    vw: window.innerWidth,
  }));
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
    },
  },
];
