# Phone-first PR C — PWA install — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the dashboard be added to an iPhone home screen as an app, and give it a bottom tab bar when launched that way.

**Architecture:** A static web manifest and icons served from `web/`, with explicit `vercel.json` rewrites so the SPA catch-all cannot answer for them. Standalone mode is detected once in JS and written to `<html data-standalone>`, so all the layout that depends on it is plain CSS. The bar's fifth tab, More, is a real route (`#/more`), not an overlay.

**Tech Stack:** Preact + HTM inline in `web/index.html`, Vercel static hosting, standalone Python test runner, Playwright (dev-only, local).

**Spec:** `docs/superpowers/specs/2026-09-28-phone-first-design.md` (section "PR C")

## Global Constraints

- `web/index.html` stays a single file served as-is: no build step, no new runtime dependency, no separately served JS module.
- No service worker. The dashboard is auth-protected and live; an offline cache would show remembered state as current.
- Manifest values: `name` "Prompt Lab", `short_name` "Prompt Lab", `display` "standalone", `start_url` "/", `scope` "/", `background_color` "#111111", `theme_color` "#111111".
- Icon files: `web/icons/icon-180.png`, `web/icons/icon-192.png`, `web/icons/icon-512.png`, generated from `web/icons/icon.svg`. Design: the letters "PL" in white (`#ffffff`) on the accent colour `#6366f1`, full-bleed square with no transparency and no rounded corners (iOS rounds the corners itself and turns transparency black).
- Standalone mode is true when `window.matchMedia('(display-mode: standalone)').matches` or `window.navigator.standalone === true` (iOS). It is written to `document.documentElement.dataset.standalone = '1'` before first paint.
- The bottom tab bar shows only when standalone AND `max-width: 640px`. In a browser tab, and on a wide screen, nothing changes.
- Bottom tabs, in order: Home (`#/`), Activity (`#/activity`), Todos (`#/todos`), Costs (`#/costs`), More (`#/more`). Every tab is at least 44px tall and the bar adds `env(safe-area-inset-bottom)` padding beneath them.
- Visitors and Health are admin-only: a reader never sees them on the More page. This is presentation; the API already refuses a reader.
- On a phone, prefer a real route over a fixed overlay. The bar itself is the one fixed element this plan adds.
- The repository is public. Fixtures are synthetic.
- Tests are standalone runners, not pytest. Python: `/Users/nico/src/prompt-lab/.venv/bin/python scripts/test_web_api.py`. Pure JS: `node scripts/test_frontend_pure.mjs`. Layout: `node scripts/phone/check.mjs`. Ruff: `/Users/nico/src/prompt-lab/.venv/bin/ruff check . --exclude .venv`.
- Comments explain why, not what. Commit messages end with a `Co-Authored-By: Claude <model name> <noreply@anthropic.com>` trailer naming the model that wrote the commit.
- Never read `.env` files or any secret material. Never run `install.sh`. Work only inside `/Users/nico/src/prompt-lab/.claude/worktrees/phone-first`. Do not push.

## Review Focus

- A request for `/manifest.webmanifest` or an icon in production: the SPA catch-all must not answer with `index.html` and a 200. Pinned in Task 1 (rewrite order).
- The manifest and icons are fetched without the session cookie by the OS when installing: they must not sit behind auth. Pinned in Task 1 (static files, outside `/api/`).
- A reader account on the More page: no Visitors, no Health. Pinned in Task 2.
- The last rows of a long page hidden under the fixed bar. Pinned in Task 2 (bottom padding).
- The same phone in a browser tab: no bar, the Menu button as before. Pinned in Task 2.

---

### Task 1: Manifest, icons, and their rewrites

**Files:**
- Create: `web/manifest.webmanifest`
- Create: `web/icons/icon.svg`, `web/icons/icon-180.png`, `web/icons/icon-192.png`, `web/icons/icon-512.png`
- Create: `scripts/phone/make-icons.mjs`
- Modify: `web/index.html` (the `<head>` only)
- Modify: `web/vercel.json`
- Modify: `scripts/phone/check.mjs` (the static server's content types)
- Test: `scripts/test_web_api.py` (add a new section at the end, directly above `if __name__ == "__main__":`)

**Interfaces:**
- Produces: `GET /manifest.webmanifest` and `GET /icons/icon-{180,192,512}.png` as static files.
- Produces: `<link rel="manifest">`, `<link rel="apple-touch-icon">` and `<meta name="mobile-web-app-capable">` in the page head.

- [ ] **Step 1: Write the failing tests**

Add to `scripts/test_web_api.py`. `ROOT` and `test` already exist in that file; `json` is already imported.

```python
# === PWA install: manifest, icons, rewrites ===

def _png_size(path):
    """(width, height) from a PNG's IHDR chunk. No image library: the header
    is fixed-layout, and a wrong-size icon is the failure worth catching."""
    import struct
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", f"{path.name} is not a PNG"
    assert data[12:16] == b"IHDR", f"{path.name} has no IHDR chunk first"
    return struct.unpack(">II", data[16:24])


@test("pwa: manifest is valid and says what the spec says")
def _():
    m = json.loads((ROOT / "web" / "manifest.webmanifest").read_text())
    assert m["name"] == "Prompt Lab"
    assert m["short_name"] == "Prompt Lab"
    assert m["display"] == "standalone"
    assert m["start_url"] == "/"
    assert m["scope"] == "/"
    assert m["background_color"] == "#111111"
    assert m["theme_color"] == "#111111"
    got = {(i["src"], i["sizes"], i["type"]) for i in m["icons"]}
    assert got == {
        ("/icons/icon-192.png", "192x192", "image/png"),
        ("/icons/icon-512.png", "512x512", "image/png"),
    }, f"manifest icons: {got}"


@test("pwa: every icon exists at the size its name claims, with no transparency")
def _():
    for size in (180, 192, 512):
        path = ROOT / "web" / "icons" / f"icon-{size}.png"
        assert path.exists(), f"missing {path.name}"
        assert _png_size(path) == (size, size), f"{path.name} is {_png_size(path)}"
        # Colour type lives at byte 25: 2 is RGB, 6 is RGBA. iOS paints
        # transparent pixels black, so the icon must carry no alpha channel.
        assert path.read_bytes()[25] == 2, (
            f"{path.name} has colour type {path.read_bytes()[25]}, expected 2 (RGB, no alpha)")


@test("pwa: the page head links the manifest and the touch icon")
def _():
    src = (ROOT / "web" / "index.html").read_text()
    head = src[:src.index("</head>")]
    assert '<link rel="manifest" href="/manifest.webmanifest">' in head
    assert '<link rel="apple-touch-icon" href="/icons/icon-180.png">' in head
    assert '<meta name="mobile-web-app-capable" content="yes">' in head
    assert '<meta name="apple-mobile-web-app-capable" content="yes">' in head, (
        "keep the Apple meta: older iOS reads only that one")
    assert '<meta name="apple-mobile-web-app-title" content="Prompt Lab">' in head


@test("pwa: no service worker is registered")
def _():
    src = (ROOT / "web" / "index.html").read_text()
    assert "serviceWorker" not in src, (
        "the dashboard is live and auth-protected — an offline cache would "
        "show remembered state as current")


@test("pwa: manifest and icons are rewritten to themselves before the SPA catch-all")
def _():
    cfg = json.loads((ROOT / "web" / "vercel.json").read_text())
    sources = [r["source"] for r in cfg["rewrites"]]
    catch_all = sources.index("/(.*)")
    for source, dest in (("/manifest.webmanifest", "/manifest.webmanifest"),
                         ("/icons/(.*)", "/icons/$1")):
        assert source in sources, f"no rewrite for {source}"
        assert sources.index(source) < catch_all, (
            f"{source} sits after the catch-all, which would answer with index.html")
        rule = cfg["rewrites"][sources.index(source)]
        assert rule["destination"] == dest, f"{source} -> {rule['destination']}"
    assert sources[-1] == "/(.*)", "the catch-all must stay last"
    assert not any(s.startswith("/api/") for s in ("/manifest.webmanifest", "/icons/")), (
        "install assets are fetched without the session cookie: never behind /api/")


@test("pwa: the manifest is served with the manifest content type")
def _():
    cfg = json.loads((ROOT / "web" / "vercel.json").read_text())
    rule = next((h for h in cfg["headers"] if h["source"] == "/manifest.webmanifest"), None)
    assert rule is not None, "no headers rule for /manifest.webmanifest"
    got = {h["key"]: h["value"] for h in rule["headers"]}
    assert got.get("Content-Type") == "application/manifest+json", got
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `/Users/nico/src/prompt-lab/.venv/bin/python scripts/test_web_api.py 2>&1 | tail -30`
Expected: the six new tests FAIL (`FileNotFoundError` on the manifest and icons, assertion failures on the head and rewrites); `pwa: no service worker is registered` PASSES already and must keep passing. Every pre-existing test passes.

- [ ] **Step 3: Create the manifest**

`web/manifest.webmanifest`:

```json
{
  "name": "Prompt Lab",
  "short_name": "Prompt Lab",
  "description": "Agent sessions, costs and health across projects.",
  "start_url": "/",
  "scope": "/",
  "display": "standalone",
  "background_color": "#111111",
  "theme_color": "#111111",
  "icons": [
    { "src": "/icons/icon-192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png" }
  ]
}
```

- [ ] **Step 4: Create the icon source and generator**

`web/icons/icon.svg`:

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
  <rect width="512" height="512" fill="#6366f1"/>
  <text x="256" y="256" text-anchor="middle" dominant-baseline="central"
        font-family="-apple-system, 'SF Pro Display', 'Helvetica Neue', Arial, sans-serif"
        font-size="248" font-weight="700" letter-spacing="-8" fill="#ffffff">PL</text>
</svg>
```

`scripts/phone/make-icons.mjs`:

```js
#!/usr/bin/env node
// Renders web/icons/icon.svg to the PNG sizes the manifest and iOS want.
// Run by hand when the icon changes; the PNGs are committed, so neither the
// deploy nor CI needs a browser.
//
//   node scripts/phone/make-icons.mjs

import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const ICONS = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', 'web', 'icons');
const svg = await readFile(path.join(ICONS, 'icon.svg'), 'utf8');

const browser = await chromium.launch();
try {
  for (const size of [180, 192, 512]) {
    const page = await browser.newPage({ viewport: { width: size, height: size }, deviceScaleFactor: 1 });
    await page.setContent(
      `<style>html,body{margin:0;background:#6366f1}svg{display:block;width:${size}px;height:${size}px}</style>${svg}`);
    // omitBackground: false writes an opaque RGB PNG. iOS paints transparent
    // pixels black, so an alpha channel would put a black frame on the icon.
    await page.screenshot({ path: path.join(ICONS, `icon-${size}.png`), omitBackground: false });
    await page.close();
    console.log(`wrote icon-${size}.png`);
  }
} finally {
  await browser.close();
}
```

Run: `node scripts/phone/make-icons.mjs`
Expected: three `wrote icon-….png` lines. Read `web/icons/icon-512.png` with the Read tool and confirm it shows white "PL" centred on an indigo square.

If the colour-type test then fails because Chromium wrote RGBA (colour type 6), convert in the generator rather than loosening the test: screenshot as `type: 'jpeg', quality: 100` is not acceptable (the file must be PNG). Instead decode and re-encode with Node's `zlib` to drop the alpha channel, or render through a `<canvas>` created with `getContext('2d', { alpha: false })` and export `canvas.toDataURL('image/png')`. Report which you used.

- [ ] **Step 5: Link them from the page head**

In `web/index.html`, replace the two Apple meta lines and the theme-color line with:

```html
  <!-- Both capable metas: the unprefixed one is current, older iOS reads only
       the Apple one. -->
  <meta name="mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-title" content="Prompt Lab">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <meta name="theme-color" content="#111">
  <link rel="manifest" href="/manifest.webmanifest">
  <link rel="apple-touch-icon" href="/icons/icon-180.png">
```

- [ ] **Step 6: Add the rewrites and the header**

In `web/vercel.json`, insert into `rewrites` directly after the `/beacon.js` rule and before the `/(.*)` catch-all:

```json
    {
      "source": "/manifest.webmanifest",
      "destination": "/manifest.webmanifest"
    },
    {
      "source": "/icons/(.*)",
      "destination": "/icons/$1"
    },
```

and into `headers`, directly after the `/beacon.js` rule:

```json
    {
      "source": "/manifest.webmanifest",
      "headers": [
        {
          "key": "Content-Type",
          "value": "application/manifest+json"
        }
      ]
    },
```

- [ ] **Step 7: Teach the local static server the two new types**

In `scripts/phone/check.mjs`, extend `TYPES` with `'.webmanifest': 'application/manifest+json'`, `'.png': 'image/png'` and `'.svg': 'image/svg+xml'`.

- [ ] **Step 8: Run the tests to verify they pass**

Run: `/Users/nico/src/prompt-lab/.venv/bin/python scripts/test_web_api.py 2>&1 | tail -8`
Expected: all pass.

Run: `/Users/nico/src/prompt-lab/.venv/bin/ruff check . --exclude .venv && node scripts/phone/check.mjs`
Expected: `All checks passed!` and every layout check PASS.

- [ ] **Step 9: Commit**

```bash
git add web/manifest.webmanifest web/icons web/index.html web/vercel.json scripts/phone/make-icons.mjs scripts/phone/check.mjs scripts/test_web_api.py
git commit -m "feat(pwa): manifest, icons and their rewrites so the dashboard installs to a home screen"
```

---

### Task 2: Bottom tab bar and the More route, in standalone mode

**Files:**
- Modify: `web/index.html` — the early inline `<script>` in the head; `parseHash`; a new `MoreView` and `TabBar` component; `App`'s render; CSS.
- Modify: `scripts/phone/check.mjs` — a `standalone` profile.
- Modify: `scripts/phone/checks.mjs`
- Modify: `CLAUDE.md` — one paragraph in the `## Deploy (cloud dashboard)` section.

**Interfaces:**
- Consumes: `NAV`, `Header`, `navigate`, `useRoute`, `parseHash`, the `role` state in `App`, `smallTargets(page)`, `pageOverflow(page)`, `fixtureOptions.role`.
- Produces: route `#/more` → `{ view: 'more' }`. Components `TabBar({ route })` and `MoreView({ role, email, info, theme, onToggleTheme, onLogout })`. Test hooks: `data-test="tab-bar"`, `data-test="tab"` with `data-view=<home|activity|todos|costs|more>`, `data-test="more-list"`.
- Produces: harness profile `standalone` — the `phone` profile plus an init script that makes `navigator.standalone` read `true`.

**Behaviour:**

1. Detection. In the head's existing early inline `<script>` (the one that applies the saved theme before first paint), add: if `matchMedia('(display-mode: standalone)').matches` or `navigator.standalone === true`, set `document.documentElement.dataset.standalone = '1'`. Wrap it in its own `try`/`catch` so a failure cannot stop the theme from applying.
2. `TabBar` renders in `App` on every authenticated route. CSS hides it unless `html[data-standalone]` and `max-width: 640px`. It is `position: fixed; left: 0; right: 0; bottom: 0`, with a top border, the page background colour, five equal-width tabs, each at least 44px tall, and `padding-bottom: env(safe-area-inset-bottom)`. Text labels, no icons. The tab for the current view is drawn in the accent colour and has `aria-current="page"`. A project page or a day page highlights no tab; `visitors`, `health`, `about` and `more` highlight More.
3. When the bar is showing, the page content gets bottom padding of the bar's height plus the safe-area inset, so the last rows of a long page are not hidden under it.
4. When the bar is showing, the header's Menu button and its dropdown are hidden: the bar replaces them. The logo and the theme toggle stay.
5. `#/more` is a real route. `MoreView` lists, as full-width rows at least 44px tall: Visitors and Health (admin only), About, the theme toggle, the signed-in email (plain text, when present), the build stamp (plain text, when present), and Log out last, separated by a rule. It works at every width and in a browser tab too, since it is only a page; the wide-screen nav does not link to it.
6. In a browser tab on a phone, and on any wide screen, nothing changes: no bar, the Menu button as before.

- [ ] **Step 1: Add the `standalone` profile to the harness**

In `scripts/phone/check.mjs`, add to `PROFILES`:

```js
  // Launched from the home screen. iOS reports it through navigator.standalone;
  // Playwright cannot put a page in display-mode: standalone, so the check
  // sets the property the page reads.
  standalone: { engine: webkit, options: { ...devices['iPhone 14'] }, standalone: true },
```

and in `runCheck`, directly after the context is created:

```js
  if (profile.standalone) {
    await context.addInitScript(() => {
      Object.defineProperty(Navigator.prototype, 'standalone', { get: () => true, configurable: true });
    });
  }
```

- [ ] **Step 2: Write the failing checks**

```js
const TABS = ['home', 'activity', 'todos', 'costs', 'more'];

CHECKS.push({
  name: 'tabbar', profile: 'standalone', hash: '#/', ready: 'text=Active projects',
  async run(page, t) {
    const bar = page.locator('[data-test="tab-bar"]');
    t.ok(await bar.isVisible(), 'the tab bar shows when launched from the home screen');
    const views = await bar.locator('[data-test="tab"]').evaluateAll((els) => els.map((e) => e.dataset.view));
    t.ok(JSON.stringify(views) === JSON.stringify(TABS), `tabs in order (${views.join(', ')})`);
    const boxes = await bar.locator('[data-test="tab"]').evaluateAll((els) => els.map((e) => {
      const r = e.getBoundingClientRect(); return { w: Math.round(r.width), h: Math.round(r.height), right: Math.round(r.right) };
    }));
    t.ok(boxes.every((b) => b.h >= 44), `every tab is at least 44px tall (${boxes.map((b) => b.h).join(', ')})`);
    t.ok(Math.max(...boxes.map((b) => b.w)) - Math.min(...boxes.map((b) => b.w)) <= 2, 'tabs are equal width');
    t.ok(boxes.every((b) => b.right <= 390), 'all five fit the screen');
    const pinned = await bar.evaluate((e) => ({
      position: getComputedStyle(e).position,
      gap: Math.round(window.innerHeight - e.getBoundingClientRect().bottom),
    }));
    t.ok(pinned.position === 'fixed' && pinned.gap === 0, `the bar is pinned to the bottom edge (${pinned.position}, gap ${pinned.gap}px)`);
    t.ok(await bar.locator('[data-view="home"]').getAttribute('aria-current') === 'page', 'Home is current on the home page');
    t.ok(!(await page.locator('.nav-toggle').isVisible()), 'the Menu button is hidden: the bar replaces it');

    // The end of a long page must clear the bar.
    await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
    await page.waitForTimeout(200);
    const clear = await page.evaluate(() => {
      const barTop = document.querySelector('[data-test="tab-bar"]').getBoundingClientRect().top;
      const app = document.querySelector('#app') || document.body;
      let last = app;
      while (last.lastElementChild && last.lastElementChild.getBoundingClientRect().height > 0
             && !last.lastElementChild.matches('[data-test="tab-bar"]')) last = last.lastElementChild;
      return { barTop: Math.round(barTop), lastBottom: Math.round(last.getBoundingClientRect().bottom) };
    });
    t.ok(clear.lastBottom <= clear.barTop, `the last content clears the bar (content ends ${clear.lastBottom}px, bar starts ${clear.barTop}px)`);

    for (const [view, hash] of [['activity', '#/activity'], ['todos', '#/todos'], ['costs', '#/costs'], ['more', '#/more'], ['home', '#/']]) {
      await bar.locator(`[data-view="${view}"]`).tap();
      await page.waitForFunction((h) => (location.hash || '#/') === h, hash);
      t.ok(await bar.locator(`[data-view="${view}"]`).getAttribute('aria-current') === 'page', `${view}: tab goes there and becomes current`);
      const m = await pageOverflow(page);
      t.ok(m.doc <= m.vw, `${view}: no horizontal page overflow (${m.doc}px)`);
    }
  },
});

CHECKS.push({
  name: 'more-admin', profile: 'standalone', hash: '#/more', ready: '[data-test="more-list"]',
  async run(page, t) {
    const text = await page.locator('[data-test="more-list"]').innerText();
    for (const label of ['Visitors', 'Health', 'About', 'Log out']) t.ok(text.includes(label), `More lists ${label}`);
    const small = await smallTargets(page);
    t.ok(small.length === 0, `every row is at least 44px tall (${small.map((s) => `${s.what} ${s.h}`).join('; ')})`);
    await page.locator('[data-test="more-list"]').getByText('Visitors', { exact: true }).tap();
    await page.waitForFunction(() => location.hash === '#/visitors');
    t.ok(await page.locator('[data-test="tab-bar"] [data-view="more"]').getAttribute('aria-current') === 'page',
      'Visitors keeps More highlighted');
  },
});

CHECKS.push({
  name: 'more-reader', profile: 'standalone', hash: '#/more', ready: '[data-test="more-list"]',
  async before() { fixtureOptions.role = 'reader'; },
  async after() { fixtureOptions.role = 'admin'; },
  async run(page, t) {
    const text = await page.locator('[data-test="more-list"]').innerText();
    t.ok(!text.includes('Visitors') && !text.includes('Health'), 'a reader is offered no Visitors or Health');
    t.ok(text.includes('About') && text.includes('Log out'), 'a reader keeps About and Log out');
  },
});

CHECKS.push({
  name: 'tabbar-browser-tab', profile: 'phone', hash: '#/', ready: 'text=Active projects',
  async run(page, t) {
    t.ok(!(await page.locator('[data-test="tab-bar"]').isVisible()), 'in a browser tab there is no tab bar');
    t.ok(await page.locator('.nav-toggle').isVisible(), 'and the Menu button is there as before');
  },
});

CHECKS.push({
  name: 'tabbar-project', profile: 'standalone', hash: '#/project/alpha-app', ready: 'text=Trajectory',
  async run(page, t) {
    const current = await page.locator('[data-test="tab"][aria-current="page"]').count();
    t.ok(current === 0, `a project page highlights no tab (${current})`);
  },
});
```

Add to the existing `home-desktop` check:

```js
      t.ok(!(await page.locator('[data-test="tab-bar"]').isVisible()), 'desktop has no tab bar');
```

If the app's root element is not `#app`, use the real one in the clearance measurement.

Run: `node scripts/phone/check.mjs tabbar more-admin more-reader tabbar-browser-tab tabbar-project home-desktop`
Expected: `tabbar`, `more-admin`, `more-reader` and `tabbar-project` FAIL or crash on missing locators; `tabbar-browser-tab` and the new desktop assertion PASS already (there is no bar yet) and must keep passing. Record the output.

- [ ] **Step 3: Implement** per the Behaviour list.

- [ ] **Step 4: Run everything**

Run: `node scripts/phone/check.mjs && node scripts/test_frontend_pure.mjs && /Users/nico/src/prompt-lab/.venv/bin/python scripts/test_web_api.py 2>&1 | tail -3 && /Users/nico/src/prompt-lab/.venv/bin/ruff check . --exclude .venv`
Expected: all pass.

Read `.playwright-mcp/phone/tabbar-standalone.png` and `.playwright-mcp/phone/more-admin-standalone.png`. Full-page screenshots place a fixed bar oddly; to judge the bar, also take a viewport screenshot in the `tabbar` check (`page.screenshot({ path: …/tabbar-viewport.png })` before scrolling) and read that one. Confirm the bar sits at the bottom edge, the labels are not truncated, and the current tab is visibly distinct.

- [ ] **Step 5: Document installing**

In `CLAUDE.md`, at the end of the `## Deploy (cloud dashboard)` section, add:

```markdown
**Installing on a phone.** The dashboard installs to an iPhone home screen from
Safari or Chrome (Share, then "Add to Home Screen"). Launched from there it gets a
bottom tab bar; in a browser tab it keeps the Menu button. There is deliberately
no service worker: the dashboard is live and auth-protected, and an offline
cache would show remembered state as current. Icons are generated from
`web/icons/icon.svg` by `node scripts/phone/make-icons.mjs` and committed.
```

- [ ] **Step 6: Commit**

```bash
git add web/index.html scripts/phone/check.mjs scripts/phone/checks.mjs CLAUDE.md
git commit -m "feat(pwa): bottom tab bar and a More page when launched from the home screen"
```
