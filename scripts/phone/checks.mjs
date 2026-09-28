// Layout checks. Each entry loads one route under one device profile.
// t.ok(condition, message) records an assertion; the runner prints them.

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
    },
  },
];
