# Phone-first PR A — Visitors rework — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `#/visitors` work on a 390px phone: no sideways page scroll, preview hosts folded into one row, lists behind tabs, rows that wrap, and a collapsed page explanation.

**Architecture:** A local Playwright layout check (`scripts/phone/`) loads the real `web/index.html` against a stubbed API and asserts layout properties; it is the failing test the frontend tasks turn green. Preview-host folding happens server-side in `web/api/visitor_overview.py`, tested in the existing Python runner. Frontend changes are CSS-swapped at `max-width: 600px` so desktop is unchanged.

**Tech Stack:** Preact + HTM inline in `web/index.html` (no build step), Python `BaseHTTPRequestHandler` serverless endpoints, standalone Python test runners, Node 20 + Playwright (dev-only, local).

**Spec:** `docs/superpowers/specs/2026-09-28-phone-first-design.md`

## Global Constraints

- `web/index.html` stays a single file served as-is: no build step, no new runtime dependency, no separately served JS module.
- Desktop must not get worse. Layout changes are gated to `max-width: 600px`, except fixes that are correct at every width (the `.two-col` track fix).
- Follow the CSS-swap idiom: both markups render, CSS picks. No viewport-width state in JS in this plan.
- The repository is public. Fixtures are synthetic: hostnames use the `.example` TLD, no real project traffic, paths, or referrers. Screenshots go only to the gitignored `.playwright-mcp/phone/` directory.
- Turso returns aggregates as strings; every count is coerced with `int()` before arithmetic.
- The literal folded site name is `previews`. The payload key is `preview_hosts` (an int).
- Tests are standalone runners, not pytest. Python tests run as `/Users/nico/src/prompt-lab/.venv/bin/python scripts/test_web_api.py` (the venv lives in the main checkout; this worktree has none).
- Ruff must pass: `/Users/nico/src/prompt-lab/.venv/bin/ruff check . --exclude .venv` (if `ruff` is not in the venv, use `ruff` from PATH and report the version; CI pins 0.15.22).
- Match the surrounding code's comment density and voice: comments explain why, not what.
- Commit messages end with the line `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Never read `.env` files or any secret material. Never run `install.sh`.
- Work only inside this worktree: `/Users/nico/src/prompt-lab/.claude/worktrees/phone-first`. Do not push; the controller pushes.

## Review Focus

- A hostname or path longer than the viewport with no break characters (one 70-character token): the page must not widen and the count must stay visible. Pinned in Task 3's check.
- A payload with no `preview_hosts` key (an older deploy, or a cached response): the page renders, and a `previews` row shows no sub-label rather than "undefined preview hosts". Pinned in Task 3.
- An empty list (no referrers in the window): the Referrers tab shows "None yet." rather than a blank panel. Pinned in Task 4.
- A preview host and a real site sharing a date and path: the real site's views are unchanged by folding. Pinned in Task 2.
- Desktop width: the tab bar is hidden and all three lists are visible at once. Pinned in Task 4.

---

### Task 1: Phone layout check harness

**Files:**
- Create: `scripts/phone/package.json`
- Create: `scripts/phone/check.mjs`
- Create: `scripts/phone/fixtures.mjs`
- Create: `scripts/phone/checks.mjs`
- Modify: `.gitignore` (add `node_modules/`)
- Modify: `CLAUDE.md` (the `### Testing` section, project part only, never the shared-conventions block)

**Interfaces:**
- Produces: `node scripts/phone/check.mjs [check-name ...]` — runs all checks, or only the named ones. Prints one `PASS <check>: <message>` or `FAIL <check>: <message>` line per assertion, then `N passed, M failed`. Exit code 0 when nothing failed, 1 otherwise.
- Produces: `scripts/phone/checks.mjs` exports `CHECKS`, an array of `{ name, profile, hash, ready, run(page, t) }`. `profile` is `'phone'` or `'desktop'`. `ready` is a Playwright selector awaited before `run`. `t.ok(condition, message)` records one assertion.
- Produces: `scripts/phone/fixtures.mjs` exports `apiFixture(pathname, searchParams, method)` returning `{ status, body }`. Later tasks and plans add routes to it.
- Produces: screenshots at `.playwright-mcp/phone/<check-name>-<profile>.png` (full page).

- [ ] **Step 1: Create `scripts/phone/package.json`**

```json
{
  "name": "prompt-lab-phone-check",
  "private": true,
  "type": "module",
  "description": "Local-only phone layout check. Not part of the deployed app.",
  "scripts": {
    "check": "node check.mjs"
  },
  "devDependencies": {
    "playwright": "^1.50.0"
  }
}
```

Then add `node_modules/` on its own line to `.gitignore`, and install:

```bash
cd scripts/phone && npm install && npx playwright install webkit chromium
```

Commit `package-lock.json` alongside `package.json`.

- [ ] **Step 2: Write `scripts/phone/fixtures.mjs`**

Synthetic data only. Dates are generated relative to now in Pacific time, because the page builds its axis from `labDay()`.

```js
// Synthetic API responses for the phone layout check. The repo is public:
// nothing here is real traffic. Hostnames use the reserved .example TLD.

const PACIFIC = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Los_Angeles' });
export const labDay = (i) => PACIFIC.format(new Date(Date.now() - i * 86400000));

// One unbroken 70-character token. Layout must survive it without folding,
// so it is deliberately NOT a preview host.
export const LONG_HOST = 'offer-builder-staging-environment-for-the-spring-launch.shop.example';
export const LONG_PATH = '/projects/a-very-long-project-slug-that-keeps-going-and-going-without-a-break';

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
  return {
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
```

- [ ] **Step 3: Write `scripts/phone/checks.mjs` with the first check**

```js
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
```

- [ ] **Step 4: Write `scripts/phone/check.mjs`**

```js
#!/usr/bin/env node
// Phone layout check: serves web/ locally, stubs /api/** with synthetic
// fixtures, and asserts layout properties no source grep can see (a page that
// scrolls sideways, a control too small to tap). Local only, not CI-gated:
// it needs browser binaries and the esm.sh CDN the page imports Preact from.
//
//   node scripts/phone/check.mjs            # every check
//   node scripts/phone/check.mjs visitors   # named checks only

import http from 'node:http';
import { mkdir, readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium, devices, webkit } from 'playwright';
import { CHECKS } from './checks.mjs';
import { apiFixture } from './fixtures.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..', '..');
const WEB = path.join(ROOT, 'web');
const SHOTS = path.join(ROOT, '.playwright-mcp', 'phone');

// WebKit under the iPhone descriptor is the closest local stand-in for both
// Safari and Chrome on iOS (Chrome on iOS is WebKit too).
const PROFILES = {
  phone: { engine: webkit, options: { ...devices['iPhone 14'] } },
  desktop: { engine: chromium, options: { viewport: { width: 1280, height: 800 } } },
};

const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.txt': 'text/plain' };

function serveWeb() {
  const index = () => readFile(path.join(WEB, 'index.html'));
  const server = http.createServer(async (req, res) => {
    const pathname = new URL(req.url, 'http://local').pathname;
    const full = path.join(WEB, pathname === '/' ? 'index.html' : pathname.slice(1));
    try {
      if (!full.startsWith(WEB + path.sep)) throw new Error('outside web/');
      const body = await readFile(full);
      res.writeHead(200, { 'Content-Type': TYPES[path.extname(full)] || 'application/octet-stream' });
      res.end(body);
    } catch {
      // Production's SPA catch-all serves index.html for unknown paths.
      res.writeHead(200, { 'Content-Type': TYPES['.html'] });
      res.end(await index());
    }
  });
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server)));
}

async function runCheck(check, base, browsers, results) {
  const profile = PROFILES[check.profile];
  if (!profile) throw new Error(`unknown profile "${check.profile}"`);
  if (!browsers[check.profile]) browsers[check.profile] = await profile.engine.launch();
  const context = await browsers[check.profile].newContext(profile.options);
  await context.route('**/api/**', (route) => {
    const url = new URL(route.request().url());
    const { status, body } = apiFixture(url.pathname, url.searchParams, route.request().method());
    return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
  });
  const page = await context.newPage();
  const t = { ok: (cond, msg) => results.push({ check: check.name, pass: Boolean(cond), msg }) };
  try {
    await page.goto(`${base}/${check.hash}`);
    await page.locator(check.ready).first().waitFor({ timeout: 15000 });
    await check.run(page, t);
  } catch (e) {
    results.push({ check: check.name, pass: false, msg: `check crashed: ${e.message.split('\n')[0]}` });
  } finally {
    await page.screenshot({ path: path.join(SHOTS, `${check.name}-${check.profile}.png`), fullPage: true })
      .catch(() => {});
    await context.close();
  }
}

async function main() {
  const wanted = process.argv.slice(2);
  const unknown = wanted.filter((w) => !CHECKS.some((c) => c.name === w));
  if (unknown.length) {
    console.error(`unknown check(s): ${unknown.join(', ')}. Known: ${CHECKS.map((c) => c.name).join(', ')}`);
    process.exit(2);
  }
  const checks = wanted.length ? CHECKS.filter((c) => wanted.includes(c.name)) : CHECKS;

  await mkdir(SHOTS, { recursive: true });
  const server = await serveWeb();
  const base = `http://127.0.0.1:${server.address().port}`;
  const browsers = {};
  const results = [];
  try {
    for (const check of checks) await runCheck(check, base, browsers, results);
  } finally {
    await Promise.all(Object.values(browsers).map((b) => b.close()));
    server.close();
  }

  for (const r of results) console.log(`${r.pass ? 'PASS' : 'FAIL'} ${r.check}: ${r.msg}`);
  const failed = results.filter((r) => !r.pass).length;
  console.log(`${results.length - failed} passed, ${failed} failed`);
  // Zero assertions is a failure: a check that asserted nothing proved nothing.
  process.exit(failed || results.length === 0 ? 1 : 0);
}

main();
```

- [ ] **Step 5: Run it and confirm the expected failure (this is the RED for Task 3)**

Run: `node scripts/phone/check.mjs`
Expected: exit code 1 and exactly one line of the form
`FAIL visitors: no horizontal page overflow (document NNNpx, viewport 390px)` with NNN well above 390, then `0 passed, 1 failed`.
Open `.playwright-mcp/phone/visitors-phone.png` (Read tool) and confirm it shows the Visitors page with data, not a login screen or an error.

If the check instead crashes or passes, stop and diagnose: a pass here means the harness is not reproducing the bug and every later task's evidence would be worthless.

Also confirm two negative paths:
Run: `node scripts/phone/check.mjs nope` — expected exit code 2 and the "unknown check(s)" message.

- [ ] **Step 6: Document the runner in `CLAUDE.md`**

In the `### Testing` section, after the paragraph that ends "No test should use the real history database or publish data.", add:

```markdown
Phone layout is checked by a separate local runner, because a page that scrolls
sideways or a control too small to tap is invisible to a source grep:

```bash
cd scripts/phone && npm install && npx playwright install webkit chromium   # once
node scripts/phone/check.mjs
```

It serves `web/` locally, stubs `/api/**` with synthetic fixtures
(`scripts/phone/fixtures.mjs` — the repo is public, so never real data), loads
each route under Playwright's `iPhone 14` profile, and writes screenshots to the
gitignored `.playwright-mcp/phone/`. It is not CI-gated: it needs browser
binaries and the esm.sh CDN.
```

- [ ] **Step 7: Commit**

```bash
git add .gitignore CLAUDE.md scripts/phone/package.json scripts/phone/package-lock.json scripts/phone/check.mjs scripts/phone/fixtures.mjs scripts/phone/checks.mjs
git commit -m "test: phone layout check harness, failing on visitors overflow"
```

---

### Task 2: Fold preview hosts into one `previews` row (server)

**Files:**
- Modify: `web/api/visitor_overview.py`
- Test: `scripts/test_web_api.py` (add tests directly after the test named `visitor_overview #52: every query excludes agent-flagged rows`)

**Interfaces:**
- Produces: `/api/visitor_overview` payload where any site whose hostname ends in `.vercel.app` or begins with `preview.` appears as the site `previews` in `daily`, `paths` and `referrers`; plus a new top-level key `preview_hosts` (int, count of distinct hostnames folded, taken from the `daily` rows).
- Produces: module-level `PREVIEWS = "previews"`, `_site_label(host)`, `_fold(rows, keys, sums)` in `web/api/visitor_overview.py`.

- [ ] **Step 1: Write the failing tests**

Add to `scripts/test_web_api.py`, following the file's existing `@test("...")` / `def _():` style and its `load_endpoint`, `patch_turso_query`, `patch`, `invoke`, `access_helper.Access` helpers:

```python
# === visitor_overview: preview hosts fold into one row ===

def _visov_fold(daily=(), paths=(), referrers=()):
    """Invoke visitor_overview with the three site-bearing queries stubbed.
    Turso hands counts back as strings, so the stubs do too."""
    mod = load_endpoint("web/api/visitor_overview.py", "endpoint_visov_fold")

    def fake_turso(sql, args=None):
        if "'login'" in sql:
            return []
        if "GROUP BY date, site" in sql:
            return [dict(r) for r in daily]
        if "GROUP BY site, path" in sql:
            return [dict(r) for r in paths]
        if "GROUP BY site, referrer" in sql:
            return [dict(r) for r in referrers]
        return []

    restore_q = patch_turso_query(mod, fake_turso)
    restore_a = patch(mod, resolve_access=lambda h: access_helper.Access(
        "admin", "a@b.c", None, None))
    try:
        h = invoke(mod, "/api/visitor_overview")
        assert h.status_code == 200, f"got {h.status_code}"
        return mod, h.body
    finally:
        restore_a()
        restore_q()


@test("visitor_overview fold: _site_label recognises preview hosts only")
def _():
    mod = load_endpoint("web/api/visitor_overview.py", "endpoint_visov_label")
    label = mod._site_label
    assert label("app-git-feat-x-someone.vercel.app") == "previews"
    assert label("APP.VERCEL.APP") == "previews", "hostname match must ignore case"
    assert label("preview.musicforge.example") == "previews"
    # Near misses stay themselves: a suffix or prefix that merely resembles one.
    assert label("notvercel.app") == "notvercel.app"
    assert label("previews.example.com") == "previews.example.com"
    assert label("musicforge.example") == "musicforge.example"
    assert label(None) is None
    assert label("") == ""


@test("visitor_overview fold: daily rows merge per date, real sites untouched")
def _():
    _, body = _visov_fold(daily=[
        {"date": "2026-09-01", "site": "a-git-x.vercel.app", "views": "2", "uniques": "1"},
        {"date": "2026-09-01", "site": "musicforge.example", "views": "40", "uniques": "9"},
        {"date": "2026-09-01", "site": "preview.musicforge.example", "views": "3", "uniques": "2"},
        {"date": "2026-09-02", "site": "a-git-x.vercel.app", "views": "1", "uniques": "1"},
    ])
    rows = {(r["date"], r["site"]): r for r in body["daily"]}
    assert len(body["daily"]) == 3, f"expected 3 rows after folding: {body['daily']}"
    assert rows[("2026-09-01", "previews")]["views"] == 5
    assert rows[("2026-09-01", "previews")]["uniques"] == 3
    assert rows[("2026-09-02", "previews")]["views"] == 1
    assert rows[("2026-09-01", "musicforge.example")]["views"] == 40, (
        "folding must never change a real site's numbers")
    assert body["preview_hosts"] == 2, f"distinct folded hosts: {body['preview_hosts']}"
    assert isinstance(body["preview_hosts"], int)


@test("visitor_overview fold: paths merge on (site, path) and stay sorted by views")
def _():
    _, body = _visov_fold(paths=[
        {"site": "musicforge.example", "path": "/", "views": "10"},
        {"site": "a-git-x.vercel.app", "path": "/", "views": "7"},
        {"site": "b-git-y.vercel.app", "path": "/", "views": "6"},
        {"site": "a-git-x.vercel.app", "path": "/settings", "views": "1"},
    ])
    got = [(r["site"], r["path"], r["views"]) for r in body["paths"]]
    assert got == [
        ("previews", "/", 13),
        ("musicforge.example", "/", 10),
        ("previews", "/settings", 1),
    ], f"paths after fold: {got}"


@test("visitor_overview fold: referrers relabel and merge")
def _():
    _, body = _visov_fold(referrers=[
        {"site": "a-git-x.vercel.app", "referrer": "github.com", "views": "2"},
        {"site": "b-git-y.vercel.app", "referrer": "github.com", "views": "3"},
        {"site": "musicforge.example", "referrer": "github.com", "views": "4"},
    ])
    got = [(r["site"], r["referrer"], r["views"]) for r in body["referrers"]]
    assert got == [("previews", "github.com", 5), ("musicforge.example", "github.com", 4)], (
        f"referrers after fold: {got}")


@test("visitor_overview fold: no preview hosts means zero and unchanged rows")
def _():
    _, body = _visov_fold(daily=[
        {"date": "2026-09-01", "site": "musicforge.example", "views": "40", "uniques": "9"},
    ])
    assert body["preview_hosts"] == 0
    assert body["daily"] == [
        {"date": "2026-09-01", "site": "musicforge.example", "views": 40, "uniques": 9}]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `/Users/nico/src/prompt-lab/.venv/bin/python scripts/test_web_api.py 2>&1 | tail -30`
Expected: the five new tests FAIL (`AttributeError: ... has no attribute '_site_label'`, and `KeyError: 'preview_hosts'` or assertion failures). Every pre-existing test still passes.

- [ ] **Step 3: Implement**

In `web/api/visitor_overview.py`, update the module docstring's second paragraph so it no longer claims that no folding applies. Replace the sentence beginning "Sites are hostnames" with:

```
Sites are hostnames (from the Origin header), not project names, so no
alias folding applies here. One fold does: preview deployments
(`*.vercel.app`, `preview.*`) collapse into a single `previews` site, because
each branch deploy gets its own hostname and a dozen one-view "sites" bury
the real ones. It is a rule on the hostname's shape, not a list of names.
```

Add below `LOGIN_ROLES`:

```python
PREVIEWS = "previews"


def _site_label(host):
    """A preview deployment's hostname -> "previews"; anything else unchanged."""
    h = (host or "").lower()
    if h.endswith(".vercel.app") or h.startswith("preview."):
        return PREVIEWS
    return host


def _fold(rows, keys, sums):
    """Relabel each row's site, then merge rows that now share `keys`,
    adding up `sums`. Counts must already be ints. Summed uniques can count
    one visitor twice across two preview hosts — accepted: the hash is
    per-site-per-day by design, so there is nothing to dedupe on."""
    out, seen = [], {}
    for row in rows:
        row = dict(row)
        row["site"] = _site_label(row.get("site"))
        key = tuple(row.get(k) for k in keys)
        if key in seen:
            for s in sums:
                seen[key][s] += row[s]
        else:
            seen[key] = row
            out.append(row)
    return out
```

In `do_GET`, replace the `payload = {` block's first three entries so the folded rows are used, and add `preview_hosts`. Immediately before `payload = {`, add:

```python
        daily = _ints(daily, ["views", "uniques"])
        preview_hosts = len({r["site"] for r in daily
                             if _site_label(r["site"]) == PREVIEWS})
        def by_views(r):
            return -r["views"]

        folded_paths = sorted(_fold(_ints(paths, ["views"]), ["site", "path"], ["views"]),
                              key=by_views)
        folded_referrers = sorted(
            _fold(_ints(referrers, ["views"]), ["site", "referrer"], ["views"]),
            key=by_views)
```

and change the payload entries to:

```python
            "daily": _fold(daily, ["date", "site"], ["views", "uniques"]),
            "paths": folded_paths,
            "referrers": folded_referrers,
            "countries": _ints(countries, ["views", "uniques"]),
            "preview_hosts": preview_hosts,
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `/Users/nico/src/prompt-lab/.venv/bin/python scripts/test_web_api.py 2>&1 | tail -15`
Expected: all tests pass, including the five new ones and the existing `visitor_overview: 200 shape, since bound, int coercion`.

Run: `/Users/nico/src/prompt-lab/.venv/bin/ruff check . --exclude .venv`
Expected: `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git add web/api/visitor_overview.py scripts/test_web_api.py
git commit -m "feat(visitors): fold preview hosts into one previews row"
```

---

### Task 3: Overflow fix, wrapping rows, share-bar "By site"

**Files:**
- Modify: `web/index.html` — the `.two-col` rule (around line 356), new `.list-row*` and `.share-row*` CSS next to it, and `VisitorsOverview` (starts around line 2912): `listRow`, and the "By site" block.
- Modify: `scripts/phone/checks.mjs`

**Interfaces:**
- Consumes: `node scripts/phone/check.mjs visitors` from Task 1 (currently failing on overflow); `data.preview_hosts` and the `previews` site name from Task 2; fixtures `LONG_HOST` and `LONG_PATH` exported by `scripts/phone/fixtures.mjs`.
- Produces: CSS classes `list-row`, `list-row-text`, `list-row-label`, `list-row-sub`, `list-row-value`; `data-test="by-site"` on the By site container and `data-test="share-row"` on each of its rows, each containing an element with `data-test="share-bar"`.

- [ ] **Step 1: Extend the check (RED)**

In `scripts/phone/checks.mjs`, import the two long strings and add assertions to the `visitors` check's `run`, after the overflow assertion:

```js
import { LONG_HOST, LONG_PATH } from './fixtures.mjs';
```

```js
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
```

Add a second check that pins the missing-key case. It needs a fixture variant, so add to `scripts/phone/fixtures.mjs` a module-level switch and honour it in `visitorOverview`:

```js
// Flipped by a check to reproduce a payload from before preview_hosts existed.
export const fixtureOptions = { omitPreviewHosts: false };
```

In `visitorOverview`, build the object as `const out = { ... }` and before returning: `if (fixtureOptions.omitPreviewHosts) delete out.preview_hosts;`.

Add to `CHECKS`:

```js
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
```

and import `fixtureOptions` in `checks.mjs`. In `scripts/phone/check.mjs`, call the optional hooks in `runCheck`: `await check.before?.()` as the first statement inside the `try`, and `await check.after?.()` as the first statement inside the `finally`.

Run: `node scripts/phone/check.mjs`
Expected: FAIL lines for overflow, counts outside the viewport, By site rows (0 found, the `data-test` hooks do not exist yet), long host, long path, and the `visitors-old-payload` check crashing on a missing locator. Exit code 1. Record this output for the report.

- [ ] **Step 2: Fix `.two-col` and add the row classes**

Replace the existing `.two-col` rules in `web/index.html`:

```css
    /* minmax(0, …), not a bare 1fr: a 1fr track's minimum is its content, so one
       long unwrapped hostname set the width of the whole page (767px in a 390px
       viewport on #/visitors). */
    .two-col { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 16px; margin-top: 16px; }
    .chart-scroll { overflow-x: auto; }
    @media (max-width: 600px) {
      .two-col { grid-template-columns: minmax(0, 1fr); }
    }

    /* One-line rows with an ellipsis on a wide screen; on a phone the label wraps
       and its sub-label drops underneath, because an ellipsis there hides the
       only part of a path that tells two pages apart. */
    .list-row {
      display: flex; align-items: center; gap: 8px; padding: 5px 0;
      border-bottom: 1px solid var(--border);
    }
    .list-row-text { display: flex; align-items: baseline; gap: 8px; min-width: 0; flex: 1 1 auto; }
    .list-row-label { font-size: 1.12rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .list-row-sub {
      font-size: 0.85rem; color: var(--text-secondary);
      overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }
    .list-row-value { margin-left: auto; flex: none; font-size: 1.12rem; font-variant-numeric: tabular-nums; }
    @media (max-width: 600px) {
      .list-row { align-items: flex-start; padding: 8px 0; }
      .list-row-text { flex-direction: column; gap: 1px; }
      .list-row-label, .list-row-sub { white-space: normal; overflow-wrap: anywhere; }
    }
```

- [ ] **Step 3: Rewrite `listRow` in `VisitorsOverview` to use the classes**

```js
      const listRow = (label, sub, v) => html`
        <div class="list-row">
          <div class="list-row-text">
            <span class="list-row-label">${label}</span>
            ${sub && html`<span class="list-row-sub">${sub}</span>`}
          </div>
          <span class="list-row-value">${v.toLocaleString()}</span>
        </div>`;
```

`listRow` is also used by the Sign-ins panel; it keeps working unchanged.

- [ ] **Step 4: Rebuild "By site" as share-bar rows**

Replace the `ranked.map(...)` block under `sectionTitle('By site')` and give its container the test hook. The markup follows Costs' "By project" rows (see `CostsOverview`, the `legend.map` block) but is not a link, because a site has no page of its own:

```js
            <div data-test="by-site">
              ${sectionTitle('By site')}
              ${ranked.map(([s, v]) => html`
                <div data-test="share-row" class="list-row" style="display: block">
                  <div style="display: flex; align-items: flex-start; gap: 8px">
                    <span style="width: 9px; height: 9px; border-radius: 2px; margin-top: 7px;
                                 background: ${segColor(s)}; flex: none"></span>
                    <div class="list-row-text">
                      <span class="list-row-label">${s}</span>
                      ${s === 'previews' && Number.isFinite(Number(data.preview_hosts)) && Number(data.preview_hosts) > 0 && html`
                        <span class="list-row-sub">
                          ${Number(data.preview_hosts)} preview host${Number(data.preview_hosts) === 1 ? '' : 's'}
                        </span>`}
                    </div>
                    <span style="margin-left: auto; flex: none; font-size: 0.85rem; color: var(--text-secondary)">
                      ${(v / totalViews * 100).toFixed(0)}%</span>
                    <span data-test="share-value" style="flex: none; font-size: 1.12rem; font-variant-numeric: tabular-nums;
                                 min-width: 56px; text-align: right">${v.toLocaleString()}</span>
                  </div>
                  <div data-test="share-bar" style="height: 3px; border-radius: 2px; margin-top: 3px;
                              width: ${(v / maxSite * 100).toFixed(1)}%;
                              background: ${segColor(s)}; opacity: 0.6"></div>
                </div>`)}
            </div>
```

Define `maxSite` next to `ranked`: `const maxSite = Math.max(...ranked.map(([, v]) => v), 1);`.

`Number(undefined)` is `NaN`, so a payload without `preview_hosts` shows no sub-label: that is the old-payload case the second check pins.

- [ ] **Step 5: Run the checks (GREEN)**

Run: `node scripts/phone/check.mjs`
Expected: every line PASS, `0 failed`, exit code 0.

Read `.playwright-mcp/phone/visitors-phone.png` and confirm by eye: nothing is cut off at the right edge, the long host and long path wrap onto several lines with their counts visible, each By site row has a coloured bar.

- [ ] **Step 6: Confirm desktop is unchanged**

Add a desktop check to `CHECKS`:

```js
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
```

Run: `node scripts/phone/check.mjs`
Expected: all PASS. Read `.playwright-mcp/phone/visitors-desktop.png` and confirm the two-column layout is intact.

- [ ] **Step 7: Run the Python suite (a source guard in it reads `web/index.html`)**

Run: `/Users/nico/src/prompt-lab/.venv/bin/python scripts/test_web_api.py 2>&1 | tail -5`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add web/index.html scripts/phone/check.mjs scripts/phone/checks.mjs scripts/phone/fixtures.mjs
git commit -m "fix(visitors): stop the page scrolling sideways on a phone; wrap rows, share bars"
```

---

### Task 4: Tabs for the three lists, and a collapsed page note

**Files:**
- Modify: `web/index.html` — new CSS next to the `.list-row` rules; a new `PageNote` component placed directly above `function VisitorsOverview()`; `VisitorsOverview`'s `header` and its two `.two-col` blocks.
- Modify: `scripts/phone/checks.mjs`
- Modify: `scripts/phone/fixtures.mjs`

**Interfaces:**
- Consumes: the `visitors` and `visitors-desktop` checks, `fixtureOptions`, and the `before`/`after` hooks from Task 3.
- Produces: `PageNote({ summary, children })`, reused by a later plan on other pages. Test hooks: `data-test="visitors-tabs"` on the tab bar, `data-test="tab-pages" | "tab-referrers" | "tab-countries"` on its buttons, `data-test="panel-pages" | "panel-referrers" | "panel-countries"` on the list containers, `data-test="page-note"` on the phone disclosure, `data-test="page-note-wide"` on the desktop paragraphs.

- [ ] **Step 1: Extend the checks (RED)**

Add to the `visitors` (phone) check's `run`:

```js
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

      await page.locator('[data-test="tab-referrers"]').tap();
      t.ok(await visible('[data-test="panel-referrers"]') && !(await visible('[data-test="panel-pages"]')),
        'tapping Referrers swaps the list');
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
      await note.locator('summary').tap();
      t.ok(await note.getByText('cookie-less', { exact: false }).isVisible(), 'tapping it shows the explanation');
```

Add to the `visitors-desktop` check's `run`:

```js
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
```

Add an empty-list check. In `scripts/phone/fixtures.mjs` extend the switch to `{ omitPreviewHosts: false, noReferrers: false }` and honour it: `if (fixtureOptions.noReferrers) out.referrers = [];`. Then in `CHECKS`:

```js
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
```

Run: `node scripts/phone/check.mjs`
Expected: the new assertions FAIL (locators not found, reported as crashed checks or failed assertions); the Task 3 assertions that run before them still PASS. Exit code 1. Record the output.

- [ ] **Step 2: Add the CSS**

Directly after the `.list-row` rules:

```css
    /* Three lists stacked on a phone ran to 2,800px. Below 600px they share one
       slot behind a tab bar; above it the bar is hidden and all three show, so
       the wide layout is exactly what it was. Both markups always render and
       CSS picks — no viewport state in JS to desync on rotate. */
    .vis-tabs { display: none; }
    .page-note-narrow { display: none; }
    @media (max-width: 600px) {
      .vis-tabs { display: flex; gap: 4px; margin-top: 4px; }
      .vis-tabs .sub-tab { flex: 1 1 0; min-height: 44px; padding: 7px 6px; }
      .vis-panel { display: none; }
      .vis-panel.active { display: block; }
      /* The active tab already names the list. */
      .vis-panel .vis-panel-title { display: none; }
      .two-col.vis-second { margin-top: 0; }

      .page-note-wide { display: none; }
      .page-note-narrow { display: block; margin: 0 0 16px; }
      .page-note-narrow summary {
        display: flex; align-items: center; min-height: 44px; cursor: pointer;
        font-size: 1.02rem; color: var(--accent);
      }
      .page-note-narrow > div { margin: 0 0 12px; }
    }
```

- [ ] **Step 3: Add `PageNote`**

Directly above `function VisitorsOverview()`:

```js
    // A page's standing explanation. On a wide screen it sits above the data as
    // it always has. On a phone it took the top half of the first screen on
    // every visit, so it folds behind one line — read once, then out of the way.
    // Rendered twice and CSS picks, the same idiom as the two navs.
    function PageNote({ summary = 'About this data', children }) {
      return html`
        <div class="page-note-wide" data-test="page-note-wide">${children}</div>
        <details class="page-note-narrow" data-test="page-note">
          <summary>${summary}</summary>
          ${children}
        </details>`;
    }
```

- [ ] **Step 4: Use it in the Visitors header**

In `VisitorsOverview`'s `header`, wrap the two explanation blocks (the paragraph beginning "Anonymous page views" and the `heatmap-note` beginning "Browser automation is excluded") in `<${PageNote}>…<//>`. Keep their text and their existing inline styles unchanged so the wide layout renders as before. The `heatmap-note` carries `margin: -12px 0 20px`, which pulls it up under the paragraph; inside the phone disclosure that negative margin would overlap the paragraph, so the `.page-note-narrow > div` rule above resets it there. Confirm in the phone screenshot that the two blocks do not overlap when expanded.

- [ ] **Step 5: Add the tab state and restructure the lists**

Add state at the top of `VisitorsOverview`, next to the other `useState` calls:

```js
      const [tab, setTab] = useState('pages');
```

Add a title helper next to `sectionTitle` (the tab names the list on a phone, so the heading hides there):

```js
      const panelTitle = (t) => html`<div class="vis-panel-title">${sectionTitle(t)}</div>`;
      const TABS = [['pages', 'Pages'], ['referrers', 'Referrers'], ['countries', 'Countries']];
      const tabBar = html`
        <div class="sub-tabs vis-tabs" data-test="visitors-tabs" role="tablist">
          ${TABS.map(([k, label]) => html`
            <button class="sub-tab ${tab === k ? 'active' : ''}" role="tab"
                    aria-selected=${tab === k} data-test=${'tab-' + k}
                    onClick=${() => setTab(k)}>${label}</button>`)}
        </div>`;
      const panelClass = (k) => 'vis-panel' + (tab === k ? ' active' : '');
```

Replace the two `.two-col` blocks that follow the chart panel with:

```js
          <div class="two-col">
            <div data-test="by-site">
              …the By site block from Task 3, unchanged…
            </div>
            ${tabBar}
            <div class=${panelClass('pages')} data-test="panel-pages">
              ${panelTitle('Top pages')}
              ${paths.map(r => listRow(r.path, r.site, r.views))}
            </div>
          </div>

          <div class="two-col vis-second">
            <div class=${panelClass('referrers')} data-test="panel-referrers">
              ${panelTitle('Referrers')}
              ${referrers.length ? referrers.map(r => listRow(r.referrer, r.site, r.views))
                : html`<div style="font-size: 1.06rem; color: var(--text-secondary)">None yet.</div>`}
            </div>
            <div class=${panelClass('countries')} data-test="panel-countries">
              ${panelTitle('Countries')}
              ${countries.length ? countries.map(r => listRow(r.country, null, r.views))
                : html`<div style="font-size: 1.06rem; color: var(--text-secondary)">None yet.</div>`}
            </div>
          </div>
```

On a wide screen the tab bar is `display: none`, so it takes no grid cell and the first grid is still By site beside Top pages. Do not leave the literal "…the By site block…" line in the file: keep the real block there.

The existing `.sub-tabs` rule at `max-width: 600px` sets `overflow-x: auto; flex-wrap: nowrap` and `.sub-tab` sets `white-space: nowrap; flex-shrink: 0`. The `.vis-tabs .sub-tab { flex: 1 1 0 }` rule above must win so three equal tabs fit in 342px; if the check reports the tab bar scrolling, raise that rule's specificity rather than shrinking the font.

- [ ] **Step 6: Run the checks (GREEN)**

Run: `node scripts/phone/check.mjs`
Expected: every line PASS, `0 failed`, exit code 0.

Read `.playwright-mcp/phone/visitors-phone.png`, `.playwright-mcp/phone/visitors-desktop.png` and `.playwright-mcp/phone/visitors-no-referrers-phone.png` and confirm by eye: on the phone one list shows under the tab bar and the expanded note's two blocks do not overlap; on desktop the layout is the two-column one with all three lists and the full explanation.

- [ ] **Step 7: Run the Python suite and ruff**

Run: `/Users/nico/src/prompt-lab/.venv/bin/python scripts/test_web_api.py 2>&1 | tail -5`
Expected: all pass.

Run: `/Users/nico/src/prompt-lab/.venv/bin/ruff check . --exclude .venv`
Expected: `All checks passed!`

- [ ] **Step 8: Commit**

```bash
git add web/index.html scripts/phone/checks.mjs scripts/phone/fixtures.mjs
git commit -m "feat(visitors): tabs for the three lists and a collapsed page note on a phone"
```
