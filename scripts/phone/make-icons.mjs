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
