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
