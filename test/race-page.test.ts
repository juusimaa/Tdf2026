// Unit tests for the pure formatting/parsing helpers in src/race-page.ts.
//
// race-page.ts compiles to a classic (non-module) script — its functions are
// plain top-level declarations, not exports (see the header comment in
// src/race-page.ts). To test them without changing how the four HTML pages
// load dist/race-page.js, this file runs the compiled output with
// vm.runInThisContext, which evaluates it as a Script in the real global
// scope, exactly like a <script> tag would: top-level function declarations
// land on globalThis, from where the tests below call them.
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { runInThisContext } from 'node:vm';
import { beforeAll, describe, expect, it } from 'vitest';

const distPath = resolve(process.cwd(), 'dist/race-page.js');

beforeAll(() => {
  let code: string;
  try {
    code = readFileSync(distPath, 'utf8');
  } catch {
    throw new Error(`${distPath} is missing — run "npm run build" before "npm test".`);
  }
  runInThisContext(code, { filename: distPath });
});

const g = globalThis as any;

describe('esc', () => {
  it('escapes HTML-significant characters', () => {
    expect(g.esc('<a href="x">A & B</a>')).toBe('&lt;a href=&quot;x&quot;&gt;A &amp; B&lt;/a&gt;');
  });
  it('treats null/undefined as an empty string', () => {
    expect(g.esc(null)).toBe('');
    expect(g.esc(undefined)).toBe('');
  });
  it('coerces non-string values', () => {
    expect(g.esc(42)).toBe('42');
  });
});

describe('timeToHours', () => {
  it('parses "Xh Y\' Z" gap/time strings', () => {
    expect(g.timeToHours("3h 24' 15")).toBeCloseTo(3 + 24 / 60 + 15 / 3600, 10);
  });
  it('returns null for unparsable input', () => {
    expect(g.timeToHours('DNF')).toBeNull();
    expect(g.timeToHours('')).toBeNull();
  });
  it('returns null for null/undefined', () => {
    expect(g.timeToHours(null)).toBeNull();
    expect(g.timeToHours(undefined)).toBeNull();
  });
});

describe('fmtKm', () => {
  it('rounds to one decimal and appends the unit', () => {
    g.lang = 'en';
    expect(g.fmtKm(178.049)).toBe('178 km');
    expect(g.fmtKm(21.55)).toBe('21.6 km');
  });
  it('uses a comma for fi/fr instead of a decimal point', () => {
    g.lang = 'fi';
    expect(g.fmtKm(21.55)).toBe('21,6 km');
    g.lang = 'fr';
    expect(g.fmtKm(21.55)).toBe('21,6 km');
  });
});

describe('fmtDate', () => {
  it('formats an ISO date in the current language', () => {
    g.lang = 'en';
    expect(g.fmtDate('2026-07-04')).toMatch(/Sat.*4.*Jul/);
    g.lang = 'fi';
    expect(g.fmtDate('2026-07-04')).toMatch(/la.*4\.7\.?/);
  });
});

describe('fmtGain', () => {
  it('locale-formats a metre count and appends the unit', () => {
    g.lang = 'en';
    expect(g.fmtGain(3200)).toBe('3,200 m');
    g.lang = 'fi';
    // fi-FI groups thousands with a non-breaking space; normalize to a
    // plain space before comparing so the test isn't ICU-formatting-fragile.
    expect(g.fmtGain(3200).replace(' ', ' ')).toBe('3 200 m');
  });
});

describe('fmtSpeed', () => {
  it('formats to one decimal, with locale-appropriate separator', () => {
    g.lang = 'en';
    expect(g.fmtSpeed(41.234)).toBe('41.2');
    g.lang = 'fr';
    expect(g.fmtSpeed(41.234)).toBe('41,2');
  });
});

describe('cardBorderStyle', () => {
  it('adds a right border to odd-positioned, non-last cards', () => {
    expect(g.cardBorderStyle(0, 4)).toContain('border-right');
  });
  it('omits the right border for the last card', () => {
    expect(g.cardBorderStyle(3, 4)).not.toContain('border-right');
  });
  it('omits the bottom border for cards in the final row', () => {
    expect(g.cardBorderStyle(2, 4)).not.toContain('border-bottom');
    expect(g.cardBorderStyle(3, 4)).not.toContain('border-bottom');
  });
});

describe('climbsWithKm', () => {
  it('drops climbs with no known km and sorts the rest ascending', () => {
    const st = { km: 180, climbs: [{ km: 120 }, { km: null }, { km: 30 }] };
    expect(g.climbsWithKm(st)).toEqual([{ km: 30 }, { km: 120 }]);
  });
  it('returns an empty array when there are no climbs', () => {
    expect(g.climbsWithKm({ km: 180 })).toEqual([]);
  });
});
