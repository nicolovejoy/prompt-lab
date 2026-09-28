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
import { apiFixture, resetFixtureOptions } from './fixtures.mjs';

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

// Chromium takes a full-page screenshot by briefly resizing the viewport
// (it reports 1x1 for a moment), which fires the page's (max-width: 640px)
// query and re-buckets every chart mid-capture as if on a phone. So desktop
// grows its viewport to the whole document instead and takes a plain shot.
// WebKit on the phone profile fires no media-query change during a
// full-page capture (checked), so phone keeps fullPage.
const DESKTOP_SHOT_MAX_H = 16000;
async function screenshot(page, profile, file) {
  if (profile !== 'desktop') return page.screenshot({ path: file, fullPage: true });
  const { width } = page.viewportSize();
  const height = await page.evaluate(() => document.documentElement.scrollHeight);
  await page.setViewportSize({ width, height: Math.min(Math.max(height, 1), DESKTOP_SHOT_MAX_H) });
  // Two frames for layout and paint, then the charts' 0.1s opacity transitions.
  await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
  await page.waitForTimeout(250);
  return page.screenshot({ path: file });
}

async function runCheck(check, base, browsers, results) {
  const profile = PROFILES[check.profile];
  if (!profile) throw new Error(`unknown profile "${check.profile}"`);
  if (!browsers[check.profile]) browsers[check.profile] = await profile.engine.launch();
  const context = await browsers[check.profile].newContext(profile.options);
  const missing = new Set();
  await context.route('**/api/**', (route) => {
    const url = new URL(route.request().url());
    const method = route.request().method();
    const { status, body, missing: unplanned } = apiFixture(url.pathname, url.searchParams, method);
    if (unplanned) missing.add(`${method} ${url.pathname}`);
    return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
  });
  const page = await context.newPage();
  const t = { ok: (cond, msg) => results.push({ check: check.name, pass: Boolean(cond), msg }) };
  try {
    await check.before?.();
    await page.goto(`${base}/${check.hash}`);
    await page.locator(check.ready).first().waitFor({ timeout: 15000 });
    await check.run(page, t);
  } catch (e) {
    results.push({ check: check.name, pass: false, msg: `check crashed: ${e.message.split('\n')[0]}` });
  } finally {
    // A throwing hook must not skip the screenshot and close, and no check may
    // leak a fixture flag into the next one, whatever its hooks did.
    try {
      await check.after?.();
    } catch (e) {
      results.push({ check: check.name, pass: false, msg: `after hook crashed: ${e.message.split('\n')[0]}` });
    }
    resetFixtureOptions();
    // Reported even when the check crashed: a missing fixture is often why.
    for (const route of missing) t.ok(false, `no fixture for ${route}`);
    // A check already named for its profile (visitors-desktop) keeps its name as is.
    const shot = check.name.endsWith(`-${check.profile}`) ? check.name : `${check.name}-${check.profile}`;
    await screenshot(page, check.profile, path.join(SHOTS, `${shot}.png`)).catch(() => {});
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
