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
import vm, { runInThisContext } from 'node:vm';
import { beforeAll, describe, expect, it } from 'vitest';

const distPath = resolve(process.cwd(), 'dist/race-page.js');
let distCode = '';

beforeAll(() => {
  try {
    distCode = readFileSync(distPath, 'utf8');
  } catch {
    throw new Error(`${distPath} is missing — run "npm run build" before "npm test".`);
  }
  runInThisContext(distCode, { filename: distPath });
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

describe('timeToHours (extended)', () => {
  it("parses times without hours (e.g. \"18' 42''\")", () => {
    expect(g.timeToHours("18' 42''")).toBeCloseTo(18 / 60 + 42 / 3600, 10);
  });
  it('parses HH:MM:SS format', () => {
    expect(g.timeToHours('83:22:51')).toBeCloseTo(83 + 22 / 60 + 51 / 3600, 10);
  });
  it('parses MM:SS format', () => {
    expect(g.timeToHours('12:30')).toBeCloseTo(12 / 60 + 30 / 3600, 10);
  });
});

describe('buildPath and xForKm', () => {
  it('calculates proportional x for km', () => {
    expect(g.xForKm(50, 100, 900, 30, 16)).toBe(30 + 0.5 * (900 - 30 - 16));
  });
  it('builds SVG path string from points', () => {
    const pts = [
      [0, 20],
      [50, 60],
      [100, 20],
    ];
    const path = g.buildPath(pts, 100, 900, 250, 30, 16, 22, 30);
    expect(path.d).toMatch(/^M \d+(\.\d+)?,\d+(\.\d+)? Q/);
    expect(path.plotW).toBe(900 - 30 - 16);
    expect(path.plotH).toBe(250 - 22 - 30);
  });
});

describe('climbHeight and genProfile', () => {
  it('calculates climb height bounded between 40 and 95', () => {
    expect(g.climbHeight({ len: 10, grad: 8 })).toBeGreaterThanOrEqual(40);
    expect(g.climbHeight({ len: 10, grad: 8 })).toBeLessThanOrEqual(95);
  });
  it('generates elevation profile keypoints', () => {
    const st = { km: 100, climbs: [{ km: 50, len: 5, grad: 6 }] };
    const prof = g.genProfile(st);
    expect(prof.length).toBeGreaterThan(2);
    expect(prof[0]).toEqual([0, 20]);
    expect(prof[prof.length - 1][0]).toBe(100);
  });
});

describe('fmtStartLocal', () => {
  it('formats CEST start time into local time', () => {
    g.lang = 'en';
    const res = g.fmtStartLocal({ dateIso: '2026-07-04', startCEST: '13:00' });
    expect(res).toBeTruthy();
    expect(typeof res).toBe('string');
  });
  it('returns null if startCEST is missing', () => {
    expect(g.fmtStartLocal({ dateIso: '2026-07-04' })).toBeNull();
  });
});

describe('mapControlsHTML', () => {
  it('renders zoom and recenter buttons', () => {
    g.lang = 'en';
    g.STRINGS = {
      en: { minimapRecenter: 'Center map', minimapCollapse: 'Collapse', minimapExpand: 'Expand' },
    };
    const htmlSmall = g.mapControlsHTML(false);
    expect(htmlSmall).toContain('data-map-zoomout');
    expect(htmlSmall).toContain('data-map-zoomin');
    expect(htmlSmall).toContain('data-map-recenter');
    expect(htmlSmall).toContain('data-map-toggle');
    expect(htmlSmall).toContain('⤢');

    const htmlBig = g.mapControlsHTML(true);
    expect(htmlBig).toContain('×');
  });
});

describe('riderRowHTML', () => {
  it('renders active rider row', () => {
    g.lang = 'en';
    g.STRINGS = { en: { withdrawalReasons: {} } };
    const html = g.riderRowHTML({
      bib: 1,
      name: 'Tadej POGACAR',
      nat: 'SLO',
      gcPos: 1,
      gcVal: "83h 22' 51''",
    });
    expect(html).toContain('Tadej POGACAR');
    expect(html).toContain('podium');
    expect(html).toContain('SLO');
  });
  it('renders dropped out rider row', () => {
    g.lang = 'en';
    g.STRINGS = {
      en: {
        withdrawalReasons: { DNF: 'DNF' },
        riderOutOnStage: (n: number) => `Stage ${n}`,
        riderOutUnknown: 'DNF',
      },
    };
    const html = g.riderRowHTML({ bib: 42, name: 'Test RIDER', status: 'DNF', statusStage: 5 });
    expect(html).toContain('out');
    expect(html).toContain('Stage 5');
  });
});

describe('HTML page scripts initialization', () => {
  const pages = ['tdf2026.html', 'giro2026.html', 'femmes2026.html', 'vuelta2026.html'];

  pages.forEach((page) => {
    it(`executes ${page} without syntax or runtime initialization errors`, () => {
      const html = readFileSync(resolve(__dirname, '..', page), 'utf8');
      const scriptRegex = /<script\b[^>]*>([\s\S]*?)<\/script>/gi;
      let match;
      const scripts: string[] = [];
      while ((match = scriptRegex.exec(html)) !== null) {
        if (match[0].includes('src="dist/race-page.js"')) {
          scripts.push(distCode);
        } else if (!match[0].includes('src=')) {
          scripts.push(match[1]);
        }
      }

      const elements: Record<string, any> = {};
      const makeMock = (name: string) => ({
        id: name,
        innerHTML: '',
        textContent: '',
        value: '',
        dataset: { view: 'results' },
        style: {},
        classList: { add: () => {}, remove: () => {}, toggle: () => {}, contains: () => false },
        setAttribute: () => {},
        getAttribute: () => null,
        addEventListener: () => {},
        appendChild: () => {},
        insertAdjacentElement: () => {},
        remove: () => {},
        scrollIntoView: () => {},
        focus: () => {},
        closest: () => null,
        querySelector: (sel: string) => makeMock(sel),
        querySelectorAll: (sel: string) => [makeMock(sel)],
        contains: () => false,
        offsetHeight: 600,
      });

      const polyMock = {
        addTo: function () {
          return this;
        },
        getBounds: () => ({}),
      };

      const context: Record<string, any> = {
        getComputedStyle: () => ({ getPropertyValue: () => '#201e1d' }),
        window: {
          addEventListener: () => {},
          innerWidth: 1200,
          getComputedStyle: () => ({ getPropertyValue: () => '#201e1d' }),
          L: {
            map: () => ({
              addTo: () => {},
              on: () => {},
              remove: () => {},
              setView: () => {},
              fitBounds: () => {},
              invalidateSize: () => {},
              zoomIn: () => {},
              zoomOut: () => {},
              getZoom: () => 10,
            }),
            tileLayer: () => ({ addTo: () => {} }),
            polyline: () => polyMock,
            circleMarker: () => ({ addTo: () => {} }),
          },
        },
        document: {
          documentElement: { lang: 'en' },
          getElementById: (id: string) => (elements[id] = elements[id] || makeMock(id)),
          querySelector: (sel: string) => makeMock(sel),
          querySelectorAll: (sel: string) => [makeMock(sel)],
          createElement: (tag: string) => makeMock(tag),
        },
        localStorage: { getItem: () => null, setItem: () => {} },
        navigator: { language: 'en' },
        fetch: () => Promise.resolve({ ok: false }),
        Intl,
        Date,
        Math,
        String,
        Number,
        Array,
        Object,
        RegExp,
        console,
        setTimeout: (fn: () => void) => fn(),
      };
      context.window.document = context.document;
      context.window.window = context.window;
      context.globalThis = context.window;

      vm.createContext(context);
      expect(() => {
        for (const s of scripts) {
          vm.runInContext(s, context);
        }
        if (typeof context.selectStage === 'function') {
          context.selectStage(0);
        }
        if (typeof context.setLang === 'function') {
          context.setLang('fi');
          context.setLang('en');
        }
      }).not.toThrow();
    });
  });
});
