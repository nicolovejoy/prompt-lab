#!/usr/bin/env node
// Unit tests for the pure helpers in web/index.html. The dashboard is one file
// with no build step, so the helpers cannot be imported: this extracts the
// block between the `// <pure>` and `// </pure>` markers and evaluates it.
// Anything inside the markers must therefore stay free of window, document
// and html — a reference to any of them fails here, which is the point.
//
//   node scripts/test_frontend_pure.mjs

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const src = readFileSync(path.join(ROOT, 'web', 'index.html'), 'utf8');

const open = src.indexOf('// <pure>');
const close = src.indexOf('// </pure>');
if (open < 0 || close < 0 || close < open) {
  console.error('FAIL: no `// <pure>` … `// </pure>` block in web/index.html');
  process.exit(1);
}
if (src.indexOf('// <pure>', open + 1) >= 0) {
  console.error('FAIL: more than one `// <pure>` marker in web/index.html');
  process.exit(1);
}

const NAMES = ['fmtShortDate', 'fmtMonth', 'fmtMonthShort', 'addDays', 'mondayOf', 'bucketSizeFor',
               'bucketDates', 'bucketTotals', 'bucketIndexAt', 'fmtUsdAxis', 'fmtUsdFine', 'bucketUptime',
               'projectStatus', 'shownNames', 'costProjectLabel', 'sharePct'];
const pure = new Function(`"use strict";\n${src.slice(open, close)}\nreturn { ${NAMES.join(', ')} };`)();

const tests = [];
const test = (name, fn) => tests.push([name, fn]);

// Source-level guards share these. stripComments drops /* */ and // line
// comments (a // must follow whitespace, so https:// survives). The three
// colour token blocks are the dark :root and the light palette written twice.
const stripComments = (text) => text.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|\s)\/\/[^\n]*/g, '$1');
const TOKEN_BLOCK_RES = {
  dark: /:root\s*\{([^}]*)\}/,
  lightOs: /:root:not\(\[data-theme\]\)\s*\{([^}]*)\}/,
  lightSet: /:root\[data-theme="light"\]\s*\{([^}]*)\}/,
};
const tokenBlock = (which) => src.match(TOKEN_BLOCK_RES[which])[1];
// A block as a { '--name': 'value' } map (comments stripped).
const tokenMap = (which) => Object.fromEntries(
  [...stripComments(tokenBlock(which)).matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)].map((m) => [m[1], m[2].trim()]));
const tok = (block, name) => (block.match(new RegExp(`${name}\\s*:\\s*([^;]+);`)) || [])[1];

// Ascending run of calendar days, built with the helper under test's own
// arithmetic deliberately avoided: plain UTC math, so a bug in addDays cannot
// hide itself.
function days(from, count) {
  const [y, m, d] = from.split('-').map(Number);
  return Array.from({ length: count }, (_, i) => {
    const t = new Date(Date.UTC(y, m - 1, d + i));
    const p = (n) => String(n).padStart(2, '0');
    return `${t.getUTCFullYear()}-${p(t.getUTCMonth() + 1)}-${p(t.getUTCDate())}`;
  });
}

test('fmtShortDate and fmtMonth', () => {
  assert.equal(pure.fmtShortDate('2026-09-14'), 'Sep 14');
  assert.equal(pure.fmtShortDate('2026-01-05'), 'Jan 5');
  assert.equal(pure.fmtMonth('2026-09'), 'Sep 2026');
  assert.equal(pure.fmtMonth('2027-01'), 'Jan 2027');
});

test('addDays crosses months, years, leap days and both DST changes', () => {
  assert.equal(pure.addDays('2026-09-30', 1), '2026-10-01');
  assert.equal(pure.addDays('2026-12-31', 1), '2027-01-01');
  assert.equal(pure.addDays('2027-01-01', -1), '2026-12-31');
  assert.equal(pure.addDays('2028-02-28', 1), '2028-02-29');
  assert.equal(pure.addDays('2026-03-08', 1), '2026-03-09');   // US spring forward
  assert.equal(pure.addDays('2026-11-01', 1), '2026-11-02');   // US fall back
  assert.equal(pure.addDays('2026-09-14', 0), '2026-09-14');
});

test('mondayOf: a Monday is its own week, a Sunday belongs to the week before', () => {
  assert.equal(pure.mondayOf('2026-09-14'), '2026-09-14');     // Monday
  assert.equal(pure.mondayOf('2026-09-13'), '2026-09-07');     // Sunday
  assert.equal(pure.mondayOf('2026-09-16'), '2026-09-14');     // Wednesday
  assert.equal(pure.mondayOf('2027-01-01'), '2026-12-28');     // Friday, across the year
  assert.equal(pure.mondayOf('2026-03-08'), '2026-03-02');     // Sunday of spring forward
  assert.equal(pure.mondayOf('2026-11-02'), '2026-11-02');     // Monday after fall back
});

test('bucketSizeFor: only a narrow screen buckets, and only long windows', () => {
  for (const d of [7, 30, 90, 365]) assert.equal(pure.bucketSizeFor(d, false), 'day');
  assert.equal(pure.bucketSizeFor(7, true), 'day');
  assert.equal(pure.bucketSizeFor(30, true), 'day');
  assert.equal(pure.bucketSizeFor(90, true), 'week');
  assert.equal(pure.bucketSizeFor(365, true), 'month');
});

test('bucketDates day: one bucket per date', () => {
  const b = pure.bucketDates(days('2026-09-01', 3), 'day');
  assert.deepEqual(b.map((x) => x.key), ['2026-09-01', '2026-09-02', '2026-09-03']);
  assert.deepEqual(b.map((x) => x.label), ['Sep 1', 'Sep 2', 'Sep 3']);
  assert.ok(b.every((x) => x.dates.length === 1 && x.size === 'day'));
});

test('bucketDates week: partial first and last buckets, Monday keys', () => {
  // 2026-09-01 is a Tuesday; 14 days ends on Monday 2026-09-14.
  const b = pure.bucketDates(days('2026-09-01', 14), 'week');
  assert.deepEqual(b.map((x) => x.key), ['2026-08-31', '2026-09-07', '2026-09-14']);
  assert.deepEqual(b.map((x) => x.dates.length), [6, 7, 1]);
  assert.deepEqual(b.map((x) => x.label), ['Sep 1–6', 'Sep 7–13', 'Sep 14']);
});

test('bucketDates week: a week spanning two months names both', () => {
  const b = pure.bucketDates(days('2026-09-28', 7), 'week');
  assert.equal(b.length, 1);
  assert.equal(b[0].label, 'Sep 28 – Oct 4');
});

test('bucketDates month: a 365-day window covers every date exactly once', () => {
  const all = days('2025-09-29', 365);
  const b = pure.bucketDates(all, 'month');
  assert.ok(b.length === 12 || b.length === 13, `month count ${b.length}`);
  assert.deepEqual(b.flatMap((x) => x.dates), all);
  assert.equal(b[0].label, 'Sep 2025');
  assert.equal(b[b.length - 1].label, 'Sep 2026');
  assert.equal(b[0].dates.length, 2, 'first bucket is partial: Sep 29 and 30');
});

test('bucketDates: empty input gives no buckets', () => {
  assert.deepEqual(pure.bucketDates([], 'week'), []);
});

test('bucketTotals merges segments, coerces strings, sorts largest first', () => {
  const [week] = pure.bucketDates(days('2026-09-07', 7), 'week');
  const got = pure.bucketTotals(week, {
    '2026-09-07': { a: 2, b: '5' },          // Turso hands counts back as strings
    '2026-09-09': { a: 3, c: 1 },
    '2026-09-20': { a: 100 },                // outside the bucket: ignored
  });
  assert.deepEqual(got, { total: 11, segs: [['a', 5], ['b', 5], ['c', 1]] });
});

// The wide chart stacked a day's segments by value with ties left in the
// order the rows arrived; a shared chart that reordered ties would repaint
// every desktop bar that has two equal slices.
test('bucketTotals: ties keep the order the segments first arrived in', () => {
  const [day] = pure.bucketDates(['2026-09-07'], 'day');
  const got = pure.bucketTotals(day, { '2026-09-07': { zed: 3, alpha: 1, mid: 3 } });
  assert.deepEqual(got.segs, [['zed', 3], ['mid', 3], ['alpha', 1]]);
});

test('fmtMonthShort fits a month axis: "Sep \'25"', () => {
  assert.equal(pure.fmtMonthShort('2025-09'), "Sep '25");
  assert.equal(pure.fmtMonthShort('2026-01'), "Jan '26");
});

test('bucketTotals: a bucket with no data is zero, not NaN', () => {
  const [week] = pure.bucketDates(days('2026-09-07', 7), 'week');
  assert.deepEqual(pure.bucketTotals(week, {}), { total: 0, segs: [] });
  assert.deepEqual(pure.bucketTotals(week, { '2026-09-07': { a: 'x' } }), { total: 0, segs: [['a', 0]] });
});

test('bucket totals across a window equal the daily total', () => {
  const all = days('2026-07-01', 90);
  const byDate = Object.fromEntries(all.map((d, i) => [d, { a: i % 5, b: 1 }]));
  const daily = all.reduce((s, d) => s + byDate[d].a + byDate[d].b, 0);
  for (const size of ['day', 'week', 'month']) {
    const sum = pure.bucketDates(all, size)
      .reduce((s, b) => s + pure.bucketTotals(b, byDate).total, 0);
    assert.equal(sum, daily, `${size} buckets lose or double-count`);
  }
});

test('bucketIndexAt clamps to the chart and refuses an empty one', () => {
  assert.equal(pure.bucketIndexAt(0, 300, 30), 0);
  assert.equal(pure.bucketIndexAt(299.9, 300, 30), 29);
  assert.equal(pure.bucketIndexAt(300, 300, 30), 29);    // the right edge itself
  assert.equal(pure.bucketIndexAt(-5, 300, 30), 0);      // finger slid off the left
  assert.equal(pure.bucketIndexAt(400, 300, 30), 29);    // and off the right
  assert.equal(pure.bucketIndexAt(155, 300, 30), 15);
  assert.equal(pure.bucketIndexAt(10, 0, 30), -1);       // not measured yet
  assert.equal(pure.bucketIndexAt(10, 300, 0), -1);      // no buckets
});

test('fmtUsdAxis on a wide screen: exact cents, and a bare "$0" at the baseline', () => {
  const cases = [[0, '$0'], [0.5, '$0.50'], [3.8, '$3.80'], [99.99, '$99.99'], [100, '$100.00'],
                 [240.4, '$240.40'], [999.5, '$999.50'], [1000, '$1,000.00'], [1234.56, '$1,234.56'],
                 [12500, '$12,500.00']];
  for (const [n, want] of cases) assert.equal(pure.fmtUsdAxis(n, false), want, String(n));
});

test('fmtUsdAxis on a phone: five characters at most, to fit a 44px gutter', () => {
  const cases = [[0, '$0'], [0.5, '$0.50'], [3.8, '$3.80'], [99.99, '$100'], [100, '$100'],
                 [240.4, '$240'], [999.5, '$1k'], [1000, '$1k'], [1234.56, '$1.2k'], [12500, '$13k']];
  for (const [n, want] of cases) assert.equal(pure.fmtUsdAxis(n, true), want, String(n));
  for (const n of [0.004, 9.994, 9.995, 10, 11.31, 99.5, 9949, 9950, 99999, 999000]) {
    const s = pure.fmtUsdAxis(n, true);
    assert.ok(s.length <= 5, `${n} -> "${s}" is ${s.length} characters`);
  }
});

test('fmtUsdFine keeps four decimals, so spend under half a cent is not "$0.00"', () => {
  const cases = [[0, '$0.0000'], [0.0004, '$0.0004'], [0.00449, '$0.0045'], [1.3766, '$1.3766'],
                 [1234.5, '$1,234.5000']];
  for (const [n, want] of cases) assert.equal(pure.fmtUsdFine(n), want, String(n));
  assert.notEqual(pure.fmtUsdFine(0.004), '$0.00');
});

test('bucketUptime: the worst day decides, response is the mean, gaps are not zero', () => {
  const [week] = pure.bucketDates(days('2026-09-07', 7), 'week');
  assert.deepEqual(pure.bucketUptime(week, {
    '2026-09-07': { uptime: 100, ms: 100 },
    '2026-09-08': { uptime: 97.5, ms: 300 },
    '2026-09-09': { uptime: 100, ms: null },      // up, but no response sample
    '2026-09-20': { uptime: 0, ms: 9999 },        // outside the bucket
  }), { uptime: 97.5, ms: 200, days: 3 });
});

test('bucketUptime: no data is null, never 0% and never NaN', () => {
  const [week] = pure.bucketDates(days('2026-09-07', 7), 'week');
  assert.deepEqual(pure.bucketUptime(week, {}), { uptime: null, ms: null, days: 0 });
  assert.deepEqual(pure.bucketUptime(week, { '2026-09-07': { uptime: null, ms: null } }),
    { uptime: null, ms: null, days: 0 });
});

test('bucketUptime: string values from the API are coerced', () => {
  const [day] = pure.bucketDates(['2026-09-07'], 'day');
  assert.deepEqual(pure.bucketUptime(day, { '2026-09-07': { uptime: '99.9', ms: '120' } }),
    { uptime: 99.9, ms: 120, days: 1 });
});

// by_project holds exactly the projects with work in the last 7 days.
const overviewWith = (worked, meta = {}) => ({
  by_project: Object.fromEntries(worked.map((p) => [p, { summaries: [] }])),
  project_metadata: meta,
});

test('projectStatus: active means worked on in the last 7 days', () => {
  const o = overviewWith(['worked']);
  assert.equal(pure.projectStatus(o, 'worked'), 'active');
  assert.equal(pure.projectStatus(o, 'idle'), 'dormant');
});

test('projectStatus: a metadata row changes nothing', () => {
  // Hiding a project writes a row. That once made it count as active for good.
  const o = overviewWith(['worked'], {
    worked: { private: true, status: 'dormant' },
    hidden: { private: true, status: 'active' },
  });
  assert.equal(pure.projectStatus(o, 'worked'), 'active');
  assert.equal(pure.projectStatus(o, 'hidden'), 'dormant');
});

test('projectStatus: an overview that has not loaded is dormant, not a crash', () => {
  assert.equal(pure.projectStatus(null, 'p'), 'dormant');
  assert.equal(pure.projectStatus({}, 'p'), 'dormant');
});

test('shownNames: drops what the private toggle hides, keeps order', () => {
  const list = ['a', 'b', 'c'];
  assert.deepEqual(pure.shownNames(list, new Set(['b'])), ['a', 'c']);
  assert.deepEqual(pure.shownNames(list, new Set()), list);
  assert.deepEqual(pure.shownNames(list, undefined), list);
});

test('costProjectLabel: names the unmapped bucket, leaves real projects alone', () => {
  assert.equal(pure.costProjectLabel('__unmapped__'), 'Unmapped');
  assert.equal(pure.costProjectLabel('prompt-lab'), 'prompt-lab');
});

test('sharePct: a whole-number percentage, and nothing when the total is 0', () => {
  assert.equal(pure.sharePct(1, 4), '25%');
  assert.equal(pure.sharePct(2, 3), '67%');
  assert.equal(pure.sharePct(5, 5), '100%');
  // A nav-only window has sites but no page loads: no NaN%, no Infinity%.
  assert.equal(pure.sharePct(0, 0), '');
  assert.equal(pure.sharePct(3, 0), '');
  assert.equal(pure.sharePct(0, NaN), '');
});

test('font sizes: every font-size is a --fs-* token, and every token used is defined', () => {
  const root = src.match(/:root\s*\{([^}]*)\}/)[1];
  const defined = new Set([...root.matchAll(/(--fs-[\w-]+)\s*:\s*[0-9.]+rem\s*;/g)].map((m) => m[1]));
  assert.equal(defined.size, 12, `expected 12 --fs-* tokens in :root, found ${defined.size}`);
  // Strip comments, then drop the token definitions themselves; what is left
  // must declare font-size only through var(--fs-*).
  const body = src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/--fs-[\w-]+\s*:[^;]*;/g, '');
  const raw = [...body.matchAll(/font-size\s*:\s*([^;"'`}]*)/g)]
    .map((m) => m[1].trim()).filter((v) => !/^var\(--fs-[\w-]+\)$/.test(v));
  assert.deepEqual(raw, [], `font-size must use var(--fs-*), found: ${raw.join(', ')}`);
  const used = new Set([...body.matchAll(/var\((--fs-[\w-]+)\)/g)].map((m) => m[1]));
  const undef = [...used].filter((t) => !defined.has(t));
  assert.deepEqual(undef, [], `undefined tokens: ${undef.join(', ')}`);
  assert.ok(used.size > 0);
});

test('opacity is not used as a text colour', () => {
  // Limits: this only sees ONE declaration block at a time (a CSS {...} body or
  // one style="..." string). It cannot see a parent's opacity dimming a child
  // that sets its own colour, nor opacity applied by a different rule to the
  // same element. A computed value (opacity: ${...}, a loading/disabled state)
  // is skipped on purpose. It catches the common slip: color: var(--text...) and
  // opacity: written together.
  const stripped = src.replace(/\/\*[\s\S]*?\*\//g, '');
  const blocks = [
    ...[...stripped.matchAll(/\{([^{}]*)\}/g)].map((m) => m[1]),
    ...[...stripped.matchAll(/style="([^"]*)"/g)].map((m) => m[1]),
  ];
  const bad = blocks.filter((b) => /color\s*:\s*var\(--text/.test(b) && /(^|[;\s])opacity\s*:(?!\s*\$\{)/.test(b));
  assert.deepEqual(bad.map((b) => b.trim().slice(0, 80)), [], 'use --text-muted instead of opacity on text');
});

test('accent roles: text uses --link, text on a fill uses --on-accent', () => {
  // --accent is for fills, borders and rings; accent-coloured text is --link, and
  // text on an accent (or any coloured) fill is --on-accent. Only colour
  // declarations are checked: background-color and border-color are excluded by
  // the lookbehind. A JS key (color: 'var(--accent)') is caught via the quote.
  const stripped = stripComments(src);
  const values = [...stripped.matchAll(/(?<![-\w])color\s*:\s*['"]?([^;"'`}\n]*)/g)].map((m) => m[1].trim());
  const accent = values.filter((v) => /var\(--accent\)/.test(v));
  assert.deepEqual(accent, [], 'color: var(--accent) on text; use var(--link)');
  const white = values.filter((v) => /(^|[^\w-])(#fff(fff)?|white)(?![\w-])/i.test(v));
  assert.deepEqual(white, [], 'color: #fff/white; use var(--on-accent)');
  const dark = tokenBlock('dark');
  const lightOs = tokenBlock('lightOs');
  const lightSet = tokenBlock('lightSet');
  for (const name of ['--link', '--on-accent']) {
    assert.ok(tok(dark, name), `dark :root must define ${name}`);
    assert.ok(tok(lightOs, name), `OS-light block must define ${name}`);
    assert.ok(tok(lightSet, name), `data-theme="light" block must define ${name}`);
  }
});

test('chart palette: tokens in all three blocks, no palette hex outside them', () => {
  const names = [...Array.from({ length: 8 }, (_, i) => `--chart-${i + 1}`), '--chart-other'];
  const dark = tokenBlock('dark');
  const lightOs = tokenBlock('lightOs');
  const lightSet = tokenBlock('lightSet');
  for (const name of names) {
    assert.ok(tok(dark, name), `dark :root must define ${name}`);
    assert.ok(tok(lightOs, name), `OS-light block must define ${name}`);
    assert.ok(tok(lightSet, name), `data-theme="light" block must define ${name}`);
  }
  // A palette hex anywhere but the token blocks is a colour that ignores the
  // theme. The lookahead keeps #555 from matching #5558e6.
  let rest = stripComments(src);
  for (const re of Object.values(TOKEN_BLOCK_RES)) rest = rest.replace(re, '');
  const HEX = ['06b6d4', '6366f1', '22c55e', 'eab308', 'ef4444', 'ec4899', 'f97316', 'a855f7', '555'];
  const found = [...rest.matchAll(new RegExp(`#(${HEX.join('|')})(?![0-9a-f])`, 'gi'))].map((m) => m[0]);
  assert.deepEqual(found, [], `palette hex outside :root; use var(--chart-N): ${found.join(', ')}`);
});

// ---- contrast ---------------------------------------------------------------
const lum = (hex) => {
  let h = hex.replace('#', '');
  if (h.length === 3) h = [...h].map((c) => c + c).join('');
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255)
    .map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const ratio = (a, b) => {
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};
const THEMES = () => ({ dark: tokenMap('dark'), light: tokenMap('lightSet') });
const checkRatios = (pairs, min) => {
  const out = [], low = [];
  for (const [theme, map] of Object.entries(THEMES())) {
    for (const [fg, bg] of pairs) {
      assert.match(map[fg] || '', /^#[0-9a-f]{3}([0-9a-f]{3})?$/i, `${theme} ${fg} must be a hex value`);
      assert.match(map[bg] || '', /^#[0-9a-f]{3}([0-9a-f]{3})?$/i, `${theme} ${bg} must be a hex value`);
      const r = ratio(map[fg], map[bg]);
      out.push(`${theme} ${fg} on ${bg}: ${r.toFixed(2)}`);
      if (r < min) low.push(`${theme} ${fg} ${map[fg]} on ${bg} ${map[bg]} = ${r.toFixed(2)} (< ${min})`);
    }
  }
  if (process.env.SHOW_RATIOS) console.log(out.join('\n'));
  assert.deepEqual(low, [], `contrast below ${min}:1`);
};

test('light palette is written identically in both places', () => {
  const a = tokenMap('lightOs'), b = tokenMap('lightSet');
  assert.ok(Object.keys(a).length > 10, 'OS-light block parsed empty');
  for (const k of new Set([...Object.keys(a), ...Object.keys(b)])) {
    assert.ok(k in a, `${k} missing from the OS-light block`);
    assert.ok(k in b, `${k} missing from the data-theme="light" block`);
    assert.equal(a[k], b[k], `${k} differs between the two light blocks`);
  }
});

test('every light token has a dark definition', () => {
  const dark = tokenMap('dark');
  const missing = Object.keys(tokenMap('lightSet')).filter((k) => !(k in dark));
  assert.deepEqual(missing, [], 'light-only tokens');
});

test('text tokens pass 4.5:1 on bg and card', () => {
  const pairs = [];
  for (const t of ['--text', '--text-secondary', '--text-muted', '--link', '--green', '--yellow', '--red']) {
    pairs.push([t, '--bg'], [t, '--card']);
  }
  checkRatios(pairs, 4.5);
});

test('--on-accent on --accent passes 4.5:1', () => {
  checkRatios([['--on-accent', '--accent']], 4.5);
});

test('chart tokens pass 3:1 on bg', () => {
  const names = [...Array.from({ length: 8 }, (_, i) => `--chart-${i + 1}`), '--chart-other'];
  checkRatios(names.map((n) => [n, '--bg']), 3);
});

test('radius, shadow and z-index are tokens: no raw values outside :root', () => {
  // Comments stripped and the dark :root (where the tokens are defined) removed.
  // 50% stays: an element with equal width and height may be a circle.
  const body = stripComments(src).replace(TOKEN_BLOCK_RES.dark, '');
  const decl = (prop) => [...body.matchAll(new RegExp(`(?<![-\\w])${prop}\\s*:\\s*([^;"'\`}\\n]*)`, 'g'))].map((m) => m[1].trim());
  const radius = decl('border-radius').filter((v) => v.split(/\s+/).some((x) => x !== '0' && x !== '50%' && !/^var\(--r-[\w-]+\)$/.test(x)));
  assert.deepEqual(radius, [], 'border-radius must use var(--r-*) (or 50%)');
  const shadow = decl('box-shadow').filter((v) => /rgba?\(/.test(v));
  assert.deepEqual(shadow, [], 'box-shadow must use var(--shadow-*)');
  const z = decl('z-index').filter((v) => /^-?\d+$/.test(v));
  assert.deepEqual(z, [], 'z-index must use var(--z-*)');
  const dark = tokenMap('dark');
  for (const n of ['--r-sm', '--r-md', '--r-lg', '--r-pill', '--shadow-pop', '--shadow-modal', '--shadow-tip',
                   '--z-tip', '--z-dropdown', '--z-bar', '--z-modal']) assert.ok(dark[n], `:root must define ${n}`);
});

let failed = 0;
for (const [name, fn] of tests) {
  try {
    fn();
    console.log(`PASS ${name}`);
  } catch (e) {
    failed++;
    console.log(`FAIL ${name}\n     ${String(e.message).split('\n').join('\n     ')}`);
  }
}
console.log(`${tests.length - failed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
