// Synthetic API responses for the phone layout check. The repo is public:
// nothing here is real traffic. Hostnames use the reserved .example TLD.

const PACIFIC = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Los_Angeles' });
export const labDay = (i) => PACIFIC.format(new Date(Date.now() - i * 86400000));

// One unbroken 70-character token. Layout must survive it without folding,
// so it is deliberately NOT a preview host.
export const LONG_HOST = 'offer-builder-staging-environment-for-the-spring-launch.shop.example';
export const LONG_PATH = '/projects/a-very-long-project-slug-that-keeps-going-and-going-without-a-break';

// Flipped by a check to reproduce a payload from before preview_hosts existed.
export const fixtureOptions = { omitPreviewHosts: false, noReferrers: false };

const SITES = [
  ['musicforge.example', 40], ['bakery.example', 22], ['builder.example', 14],
  ['previews', 5], [LONG_HOST, 3], ['piano.example', 2],
];

// Deterministic, so two runs produce the same screenshot.
function seeded(seed) {
  let s = seed;
  return () => (s = (s * 16807) % 2147483647) / 2147483647;
}

function visitorOverview(since) {
  const rnd = seeded(7);
  const daily = [];
  for (let i = 364; i >= 0; i--) {
    for (const [site, weight] of SITES) {
      const views = Math.round(weight * rnd());
      if (views > 0) daily.push({ date: labDay(i), site, views, uniques: Math.ceil(views * 0.6) });
    }
  }
  const out = {
    daily: daily.filter(r => !since || r.date >= since),
    paths: [
      ['/', 'musicforge.example', 406], ['/', 'bakery.example', 159],
      [LONG_PATH, 'builder.example', 52], ['/dashboard', 'musicforge.example', 110],
      ['/settings', 'musicforge.example', 84], ['/', LONG_HOST, 33],
      ['/custom-orders', 'bakery.example', 17], ['/', 'previews', 9],
    ].map(([path, site, views]) => ({ path, site, views })),
    referrers: [
      ['google.com', 'bakery.example', 136], ['google.com', 'musicforge.example', 28],
      ['duckduckgo.com', 'bakery.example', 11], ['github.com', 'musicforge.example', 7],
    ].map(([referrer, site, views]) => ({ referrer, site, views })),
    countries: [['US', 1189], ['AU', 8], ['DE', 5], ['FR', 4]]
      .map(([country, views]) => ({ country, views, uniques: Math.ceil(views * 0.6) })),
    preview_hosts: 4,
    logins: {
      total: 5,
      by_role: [{ role: 'admin', count: 5 }],
      by_day: [0, 12, 17, 27].map((i, k) => ({ date: labDay(i), count: k === 1 ? 2 : 1 })),
    },
  };
  if (fixtureOptions.omitPreviewHosts) delete out.preview_hosts;
  if (fixtureOptions.noReferrers) out.referrers = [];
  return out;
}

export function apiFixture(pathname, searchParams, method = 'GET') {
  const ok = (body) => ({ status: 200, body });
  if (pathname === '/api/login') return ok({ role: 'admin', email: null });
  if (pathname === '/api/info') return ok({});
  if (pathname === '/api/overview') return ok({ by_project: {}, all_projects: [], project_metadata: {} });
  if (pathname === '/api/beacon') return ok({});
  if (pathname === '/api/visitor_overview') return ok(visitorOverview(searchParams.get('since')));
  // Anything a check did not plan for fails loudly in the page, not silently.
  return { status: 404, body: { error: 'no fixture for ' + method + ' ' + pathname } };
}
