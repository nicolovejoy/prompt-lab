#!/usr/bin/env node
// Design-review screenshots: every main route, desktop (Edge 1280) and phone
// (WebKit iPhone 14), dark and light, full page, headless. Output names are
// <route>-<profile>-<scheme>.png so two runs diff by name.
//
//   node scripts/design-review/shots.mjs <output-dir>
//
// Same serving and fixtures as scripts/phone/check.mjs (synthetic data only).

import http from 'node:http';
import { mkdir, readFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium, devices, webkit } from '../phone/node_modules/playwright/index.mjs';
import { apiFixture, resetFixtureOptions } from '../phone/fixtures.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const WEB = path.resolve(HERE, '..', '..', 'web');

const PROFILES = {
  desktop: { engine: chromium, launch: { channel: 'msedge' }, options: { viewport: { width: 1280, height: 800 } } },
  phone: { engine: webkit, options: { ...devices['iPhone 14'] } },
};
const SCHEMES = ['dark', 'light'];
const ROUTES = [
  ['home', '#/', '.timeline-entry'],
  ['costs', '#/costs', 'text="By project"'],
  ['health', '#/health', 'text=Reading the strip'],
  ['project', '#/project/alpha-app', 'text=Trajectory'],
  ['activity', '#/activity', 'text="By project"'],
  ['visitors', '#/visitors', 'text=By site'],
  ['todos', '#/todos', null],
  ['login', '#/', 'text=Sign in to continue', { loggedOut: true }],
];

const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.png': 'image/png', '.svg': 'image/svg+xml', '.webmanifest': 'application/manifest+json' };

function serveWeb() {
  const server = http.createServer(async (req, res) => {
    const pathname = new URL(req.url, 'http://local').pathname;
    const full = path.join(WEB, pathname === '/' ? 'index.html' : pathname.slice(1));
    try {
      if (!full.startsWith(WEB + path.sep)) throw new Error('outside web/');
      const body = await readFile(full);
      res.writeHead(200, { 'Content-Type': TYPES[path.extname(full)] || 'application/octet-stream' });
      res.end(body);
    } catch {
      res.writeHead(200, { 'Content-Type': TYPES['.html'] });
      res.end(await readFile(path.join(WEB, 'index.html')));
    }
  });
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server)));
}

// Chromium's fullPage capture resizes the viewport and trips the phone media
// query mid-shot, so desktop grows the viewport to the document instead.
async function shoot(page, profile, file) {
  if (profile !== 'desktop') return page.screenshot({ path: file, fullPage: true });
  const { width } = page.viewportSize();
  const height = await page.evaluate(() => document.documentElement.scrollHeight);
  await page.setViewportSize({ width, height: Math.min(Math.max(height, 1), 16000) });
  await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
  await page.waitForTimeout(250);
  return page.screenshot({ path: file });
}

async function main() {
  const arg = process.argv[2];
  if (!arg) { console.error('usage: shots.mjs <output-dir>'); process.exit(2); }
  const out = path.resolve(arg.replace(/^~(?=$|\/)/, os.homedir()));
  await mkdir(out, { recursive: true });
  const server = await serveWeb();
  const base = `http://127.0.0.1:${server.address().port}`;
  const failures = [];
  let written = 0;
  try {
    for (const [pname, profile] of Object.entries(PROFILES)) {
      const browser = await profile.engine.launch(profile.launch);
      for (const scheme of SCHEMES) {
        for (const [name, hash, ready, opts = {}] of ROUTES) {
          const context = await browser.newContext({ ...profile.options, colorScheme: scheme });
          await context.route('**/api/**', (route) => {
            const url = new URL(route.request().url());
            const method = route.request().method();
            if (opts.loggedOut && url.pathname === '/api/login' && method === 'GET') {
              return route.fulfill({ status: 401, contentType: 'application/json', body: JSON.stringify({ password_login: true, google_login: true }) });
            }
            const { status, body } = apiFixture(url.pathname, url.searchParams, method);
            return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
          });
          const page = await context.newPage();
          const file = `${name}-${pname}-${scheme}.png`;
          try {
            await page.goto(`${base}/${hash}`);
            if (ready) await page.locator(ready).first().waitFor({ timeout: 15000 });
            else await page.waitForLoadState('networkidle');
            await page.waitForTimeout(400);
            await shoot(page, pname, path.join(out, file));
            written++;
          } catch (e) {
            failures.push(`${file}: ${e.message.split('\n')[0]}`);
          } finally {
            resetFixtureOptions();
            await context.close();
          }
        }
      }
      await browser.close();
    }
  } finally {
    server.close();
  }
  console.log(`${written} screenshots in ${out}`);
  for (const f of failures) console.error(`FAILED ${f}`);
  process.exit(failures.length ? 1 : 0);
}

main();
