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
               'bucketDates', 'bucketTotals', 'bucketIndexAt', 'fmtUsdAxis'];
const pure = new Function(`"use strict";\n${src.slice(open, close)}\nreturn { ${NAMES.join(', ')} };`)();

const tests = [];
const test = (name, fn) => tests.push([name, fn]);

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
