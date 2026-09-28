// Synthetic API responses for the phone layout check. The repo is public:
// nothing here is real traffic. Hostnames use the reserved .example TLD.

const PACIFIC = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Los_Angeles' });
export const labDay = (i) => PACIFIC.format(new Date(Date.now() - i * 86400000));

// One unbroken 70-character token. Layout must survive it without folding,
// so it is deliberately NOT a preview host.
export const LONG_HOST = 'offer-builder-staging-environment-for-the-spring-launch.shop.example';
export const LONG_PATH = '/projects/a-very-long-project-slug-that-keeps-going-and-going-without-a-break';

// Forty letters with no space or hyphen, so nothing offers the browser a
// break point: the project-name twin of LONG_HOST.
export const LONG_PROJECT = 'orchardweathersamplerandharvestledgerkit';

// Twelve invented projects, ranked roughly by weight. Charts colour the top
// eight and fold the rest into "other", so four always fold.
const PROJECTS = [
  ['alpha-app', 30], ['bravo-site', 24], ['charlie-tool', 19], ['delta-lab', 15],
  [LONG_PROJECT, 12], ['echo-notes', 10], ['foxtrot-api', 8], ['golf-cart', 6],
  ['hotel-desk', 5], ['india-ink', 4], ['juliet-cms', 3], ['kilo-board', 2],
];
export const PROJECT_NAMES = PROJECTS.map(([p]) => p);

// Flipped by a check to reproduce a payload from before preview_hosts existed,
// or one with an empty list, or a reader's session, or a site that only began
// reporting 40 days ago (so the oldest buckets of a 90-day chart are empty).
// The runner resets them after every check.
const DEFAULT_OPTIONS = { omitPreviewHosts: false, noReferrers: false, role: 'admin', quietStart: false };
export const fixtureOptions = { ...DEFAULT_OPTIONS };
export function resetFixtureOptions() { Object.assign(fixtureOptions, DEFAULT_OPTIONS); }

const SITES = [
  ['musicforge.example', 40], ['bakery.example', 22], ['builder.example', 14],
  ['previews', 5], [LONG_HOST, 3], ['piano.example', 2],
];

// Deterministic, so two runs produce the same screenshot.
function seeded(seed) {
  let s = seed;
  return () => (s = (s * 16807) % 2147483647) / 2147483647;
}

// A seed per string, so a fixture that answers for any date or project name
// is still the same answer on every run.
function seedOf(text) {
  let h = 7;
  for (const c of text) h = (h * 31 + c.charCodeAt(0)) % 2147483646;
  return h + 1;
}

// Exactly 600 characters of running prose: long text with ordinary break
// points, the counterpart to the unbroken names above.
const LONG_SUMMARY = (() => {
  const text = 'Reworked the import pipeline so a half-finished upload resumes from the '
    + 'last confirmed chunk instead of starting over, then spent the afternoon on the '
    + 'settings screen, which had grown three competing ways to save. Collapsed them '
    + 'into one explicit save button with an unsaved-changes marker, moved the rarely '
    + 'used export options behind a disclosure, and wrote tests for the resume path '
    + 'covering a dropped connection, a duplicate chunk and a server restart midway. '
    + 'Left open: whether the retry budget belongs in configuration or stays a '
    + 'constant, and a flaky timing test that passes alone but fails in the full '
    + 'suite roughly one run in ten, most likely a shared temp directory.';
  return (text + ' ' + text).slice(0, 600);
})();

const PHRASES = [
  'Tightened the onboarding copy and removed a redundant confirmation step.',
  'Added a nightly export and a test for the empty-account case.',
  'Fixed a rounding error in the invoice totals.',
  'Split the settings page into tabs and cached the slow lookup.',
  'Moved image resizing off the request path into a background job.',
  'Replaced the hand-rolled date picker with the native input.',
  'Wrote the migration for archived items and a rollback script.',
];

function summaryRow(project, date, rnd) {
  const prompts = 3 + Math.round(40 * rnd());
  const long = project === LONG_PROJECT;
  const phrase = PHRASES[Math.floor(rnd() * PHRASES.length)];
  return {
    project, date,
    summary: long ? LONG_SUMMARY : phrase + ' Also cleaned up two stale branches.',
    key_decisions: JSON.stringify(long ? [] : [phrase]),
    prompt_count: prompts,
    session_count: 1 + Math.floor(prompts / 12),
    commit_count: Math.round(prompts / 5),
  };
}

// Which projects did any work on a given day: the heavier the project, the
// likelier. Deterministic per date.
function activeOn(date) {
  const rnd = seeded(seedOf(date));
  return PROJECTS.filter(([, w]) => rnd() < 0.25 + w / 40).map(([p]) => p);
}

function overview() {
  const by_project = {}, activity_by_project = {};
  const week = { prompts: 0, sessions: 0, commits: 0 };
  for (let i = 29; i >= 0; i--) {
    const date = labDay(i);
    const rnd = seeded(seedOf('overview' + date));
    for (const p of activeOn(date)) {
      const row = summaryRow(p, date, rnd);
      (activity_by_project[p] ||= []).push({ date, prompts: row.prompt_count });
      if (i < 7) {
        (by_project[p] ||= { summaries: [], days: 0 }).summaries.unshift(row);
        by_project[p].days += 1;
        week.prompts += row.prompt_count;
        week.sessions += row.session_count;
        week.commits += row.commit_count;
      }
    }
  }
  return {
    week, by_project, latest_snapshots: {}, activity_by_project,
    all_projects: [...PROJECT_NAMES].sort(),
    project_metadata: {
      'alpha-app': { category: 'Tools', private: false, status: 'active' },
      'bravo-site': { category: 'Music', private: false, status: 'active' },
      'kilo-board': { category: 'Other', private: true, status: 'active' },
      'juliet-cms': { category: null, private: false, status: 'dormant' },
    },
  };
}

function info() {
  return {
    commit_sha: '0123abc', vercel_env: 'production', data_freshness: labDay(0),
    project_count: PROJECTS.length, build_time: new Date(Date.now() - 3 * 3600000).toISOString(),
  };
}

// 365 days of per-project daily counts, the window the page's 1y button asks for.
function activityTimeline(days) {
  const n = Math.min(Math.max(Number(days) || 30, 1), 365);
  const rows = [];
  for (let i = n - 1; i >= 0; i--) {
    const date = labDay(i);
    const rnd = seeded(seedOf('timeline' + date));
    for (const p of activeOn(date)) {
      const r = summaryRow(p, date, rnd);
      rows.push({ date, project: p, sessions: r.session_count, prompts: r.prompt_count, commits: r.commit_count });
    }
  }
  return { rows, days: n };
}

const MODELS = ['model-large', 'model-medium', 'model-small'];

function costRows(since, projects) {
  const rows = [];
  for (let i = 364; i >= 0; i--) {
    const date = labDay(i);
    if (since && date < since) continue;
    const rnd = seeded(seedOf('cost' + date));
    for (const [p, w] of PROJECTS) {
      if (projects && !projects.includes(p)) continue;
      if (rnd() > 0.2 + w / 50) continue;
      for (const model of MODELS) {
        const v = rnd() * w / 20;
        if (v > 0.02) rows.push({ date, project: p, model, cost_usd: Math.round(v * 1e6) / 1e6 });
      }
    }
  }
  return rows;
}

function costTimeline(project, since) {
  const costs = costRows(since, [project]).map(({ date, model, cost_usd }) => ({ date, model, cost_usd }));
  return { costs, usage: [] };
}

// Per-request rows for the cost detail page (`detail=1`): token type, service
// tier and context window on top of the date/model/cost the chart uses.
const TOKEN_TYPES = ['input', 'output', 'cache_read'];
const SERVICE_TIERS = ['standard', 'priority'];
const CONTEXT_WINDOWS = ['0-200k', '200k-1M'];

function costDetail(project, since) {
  const detail = [];
  for (const row of costRows(since, [project])) {
    const rnd = seeded(seedOf('detail' + row.date + row.model));
    for (const tokenType of TOKEN_TYPES) {
      const share = tokenType === 'input' ? 0.5 : tokenType === 'output' ? 0.4 : 0.1;
      const cost_usd = Math.round(row.cost_usd * share * 1e6) / 1e6;
      if (cost_usd <= 0) continue;
      detail.push({
        date: row.date, model: row.model, token_type: tokenType,
        service_tier: SERVICE_TIERS[Math.floor(rnd() * SERVICE_TIERS.length)],
        context_window: CONTEXT_WINDOWS[Math.floor(rnd() * CONTEXT_WINDOWS.length)],
        cost_usd,
      });
    }
  }
  return { detail };
}

function projectPage(name) {
  const rnd = seeded(seedOf('project' + name));
  const activity = [];
  const summaries = [];
  for (let i = 364; i >= 0; i--) {
    const date = labDay(i);
    if (!activeOn(date).includes(name)) continue;
    const row = summaryRow(name, date, rnd);
    activity.push({ date, prompt_count: row.prompt_count, session_count: row.session_count, commit_count: row.commit_count });
    if (i < 45) summaries.unshift(row);
  }
  const rollups = [1, 2, 3].map((k) => ({
    project: name, week_start: labDay(7 * k + 6),
    narrative: 'A steady week on the core flows. Most of the time went into the '
      + 'upload path and its tests; the rest into small copy fixes.',
    highlights: JSON.stringify(['resumable uploads', 'settings cleanup']),
  }));
  return {
    name,
    summaries: summaries.slice(0, 30),
    rollups,
    snapshot: {
      github_url: 'https://code.example/' + name,
      site_url: 'https://' + name + '.example',
      state_summary: name === LONG_PROJECT ? LONG_SUMMARY
        : 'Core flows are working end to end. Next is the export screen and a pass over empty states.',
      session_count_7d: 6, commit_count_7d: 14,
    },
    activity,
    inception: activity[0]?.date || null,
  };
}

function day(date) {
  const rnd = seeded(seedOf('day' + date));
  const projects = activeOn(date).slice(0, 5).map((p) => {
    const r = summaryRow(p, date, rnd);
    return {
      project: p, prompts: r.prompt_count, sessions: r.session_count, commits: r.commit_count,
      summary: r.summary, key_decisions: JSON.parse(r.key_decisions),
    };
  });
  // The long summary on every day, so the day page always carries it.
  if (!projects.some((p) => p.project === LONG_PROJECT)) {
    projects.push({ project: LONG_PROJECT, prompts: 9, sessions: 1, commits: 2, summary: LONG_SUMMARY, key_decisions: [] });
  }
  const sum = (k) => projects.reduce((s, p) => s + p[k], 0);
  const spend = [['alpha-app', 2.41], ['bravo-site', 0.87], [null, 0.12]];
  const sites = SITES.filter(([site]) => site !== 'previews')
    .map(([site, w]) => ({ site, views: Math.round(w * (0.5 + rnd())) }));
  return {
    date,
    totals: { prompts: sum('prompts'), sessions: sum('sessions'), commits: sum('commits') },
    projects,
    spend: {
      total_usd: spend.reduce((s, [, v]) => s + v, 0),
      by_project: spend.map(([project, usd]) => ({ project, usd })),
    },
    visitors: { views: sites.reduce((s, x) => s + x.views, 0), by_site: sites },
    uptime: MONITORS.slice(0, 4).map((monitor, k) => ({
      monitor, uptime_1d: k === 2 ? 98.75 : 100, status: 'up',
    })),
    provisional: date === labDay(0),
  };
}

const ISSUE_TITLES = [
  'Empty state on the export screen says nothing useful',
  'Upload resumes from the wrong chunk after a dropped connection',
  'Settings save button stays disabled after an undo',
  'Dark theme: chart axis labels are unreadable',
  'Add a keyboard shortcut for the search box',
  'Invoice totals round the wrong way on refunds',
  'Flaky timing test in the full suite',
];
const LABELS = [['bug'], ['enhancement'], [], ['bug', 'ux'], ['docs']];

function todos() {
  const projects = {};
  // One repo the overview does not know, so the "Show all repos" toggle renders.
  const names = [...PROJECT_NAMES.slice(0, 9), 'scratch-experiments'];
  names.forEach((p, k) => {
    const rnd = seeded(seedOf('todos' + p));
    const n = 1 + (k % 4);
    projects[p] = Array.from({ length: n }, (_, j) => ({
      title: ISSUE_TITLES[Math.floor(rnd() * ISSUE_TITLES.length)],
      number: 10 + k * 7 + j,
      repo: p,
      url: 'https://code.example/' + p + '/issues/' + (10 + k * 7 + j),
      labels: LABELS[(k + j) % LABELS.length],
      comments: j,
      created_at: labDay(40 + j) + 'T17:00:00Z',
      updated_at: labDay(k + j) + 'T17:00:00Z',
    }));
  });
  const total = Object.values(projects).reduce((s, l) => s + l.length, 0);
  return { configured: true, projects, total };
}

// Eleven health targets and twelve uptime monitors, all on .example hosts.
const TARGETS = [
  'alpha-app.example', 'bravo-site.example', 'charlie-tool.example', 'delta-lab.example',
  LONG_PROJECT + '.example', 'echo-notes.example', 'foxtrot-api.example', 'golf-cart.example',
  'hotel-desk.example', 'india-ink.example', 'juliet-cms.example',
];
const MONITORS = [...TARGETS, 'status.kilo-board.example'];

function healthReport() {
  const rnd = seeded(11);
  return {
    targets: TARGETS.map((name, k) => (k === 7
      ? { name, ok: false, status: 503, note: '2/3 checks ok — db DOWN', ms: 2140 }
      : { name, ok: true, status: 200, note: k % 3 === 0 ? 'db ok' : '', ms: 80 + Math.round(400 * rnd()) })),
    heartbeats: [
      ['daily summaries', 2, 0], ['weekly rollups', 8, 2], ['review email', 2, 1],
      ['uptime archive', 2, 0], ['nightly run', 2, 3],
    ].map(([name, max, age]) => ({
      name, max_age_days: max, last: labDay(age), age_days: age, ok: age <= max,
      note: age > max ? 'older than its ' + max + '-day limit' : '',
    })),
    // In the future, so Health renders its paused banner.
    paused_until: new Date(Date.now() + 3 * 86400000).toISOString(),
    would_send: true,
  };
}

function uptimeOverview(days) {
  const n = Math.min(Math.max(Number(days) || 30, 1), 365);
  const monitors = MONITORS.map((name, k) => {
    const rnd = seeded(seedOf('uptime' + name));
    // The last monitor joined the archive ten days ago; older days are grey.
    const start = k === MONITORS.length - 1 ? 9 : n - 1;
    const series = [];
    for (let i = Math.min(start, n - 1); i >= 0; i--) {
      series.push({
        date: labDay(i),
        uptime: k === 3 && i === 4 ? 97.2 : k === 5 && i === 12 ? 99.95 : 100,
        ms: 120 + Math.round(300 * rnd()) + k * 15,
      });
    }
    const low = series.some((p) => p.uptime < 100);
    return {
      name, uptime_30d: low ? 99.72 : 100, uptime_7d: k === 3 ? 99.41 : 100, uptime_1d: 100,
      avg_response_ms: 150 + k * 20, status: k === 7 ? 'DOWN' : 'UP', series,
    };
  });
  return { days: n, monitors, generated_at: new Date().toISOString() };
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
    daily: daily.filter(r => (!since || r.date >= since)
      && (!fixtureOptions.quietStart || r.date >= labDay(40))),
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
  if (pathname === '/api/login') return ok({ role: fixtureOptions.role, email: null });
  if (pathname === '/api/info') return ok(info());
  if (pathname === '/api/overview') return ok(overview());
  if (pathname === '/api/beacon') return ok({});
  if (pathname === '/api/visitor_overview') return ok(visitorOverview(searchParams.get('since')));
  if (pathname === '/api/activity_timeline') return ok(activityTimeline(searchParams.get('days')));
  if (pathname === '/api/cost_overview') return ok({ rows: costRows(searchParams.get('since')) });
  if (pathname === '/api/cost_timeline') {
    if (searchParams.get('detail') === '1') {
      return ok(costDetail(searchParams.get('project'), searchParams.get('since')));
    }
    return ok(costTimeline(searchParams.get('project'), searchParams.get('since')));
  }
  // The app prefetches the most recently active project at idle, whatever the
  // route, so this answers for any name.
  if (pathname === '/api/project') return ok(projectPage(searchParams.get('name')));
  // Likewise today and the two days before it: any date gets a full day.
  if (pathname === '/api/day') return ok(day(searchParams.get('date')));
  if (pathname === '/api/todos') return ok(todos());
  if (pathname === '/api/health_report') return ok(healthReport());
  if (pathname === '/api/uptime_overview') return ok(uptimeOverview(searchParams.get('days')));
  // Anything a check did not plan for is marked missing; the runner turns each
  // one into a failed result, since a page that degrades quietly would pass.
  return { status: 404, body: { error: 'no fixture for ' + method + ' ' + pathname }, missing: true };
}
