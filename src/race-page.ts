/* ============================================================================
   Race page shared logic — identical helper functions used by tdf2026.html,
   giro2026.html, vuelta2026.html, femmes2026.html. Compiled to
   dist/race-page.js and loaded as a classic (non-module) script right before
   each page's own inline <script>, so it shares the same top-level scope:
   these functions freely reference globals each page defines itself (lang,
   STRINGS, LANG_KEY, ROUTES_URL, RESULTS, stages, WEATHER, stageMap,
   expandState, tabButtons, resultRowHTML, etc — see globals.d.ts for their
   ambient declarations). Page-specific rendering logic stays inline per page
   since it depends on that page's data shape.
   ============================================================================ */

// A stage object's shape differs slightly per tour (e.g. dateIso vs date),
// so this only covers the fields the functions below actually read.
type StageLike = {
  n?: number | string;
  km: number;
  type?: string;
  summit?: unknown;
  climbs?: { km: number | null; len?: number; grad?: number; cat?: string }[];
  sprints?: { km: number; pts?: string }[];
  profile?: [number, number][];
  startCEST?: string;
  dateIso?: string;
  date?: string;
};

// ---------- Language / i18n ----------
function detectLang(): 'fi' | 'en' | 'fr' {
  const saved = localStorage.getItem(LANG_KEY);
  if (saved === 'fi' || saved === 'en' || saved === 'fr') return saved;
  const nav = (navigator.language || 'en').toLowerCase();
  if (nav.startsWith('fi')) return 'fi';
  if (nav.startsWith('fr')) return 'fr';
  return 'en';
}
function localeTag(): string {
  return lang === 'fi' ? 'fi-FI' : lang === 'fr' ? 'fr-FR' : 'en-GB';
}
function t(key: string): any {
  const v = STRINGS[lang] ? STRINGS[lang][key] : undefined;
  return v !== undefined ? v : STRINGS.en[key];
}
function updateLangButtons(): void {
  document.querySelectorAll<HTMLButtonElement>('#langSel button').forEach((b) => {
    const active = b.dataset.lang === lang;
    b.classList.toggle('active', active);
    b.setAttribute('aria-pressed', active ? 'true' : 'false');
  });
}

// ---------- Formatting ----------
function fmtDate(iso: string): string {
  const d = new Date(iso + 'T12:00:00');
  const opts: Intl.DateTimeFormatOptions =
    lang === 'fi'
      ? { weekday: 'short', day: 'numeric', month: 'numeric' }
      : { weekday: 'short', day: 'numeric', month: 'short' };
  return new Intl.DateTimeFormat(localeTag(), opts).format(d);
}
function fmtKm(k: number): string {
  const s = (Math.round(k * 10) / 10).toString();
  // English uses a decimal point; fi and fr use a comma.
  return (lang === 'en' ? s : s.replace('.', ',')) + ' km';
}
function fmtGain(m: number): string {
  return m.toLocaleString(localeTag()) + ' m';
}
function fmtSpeed(v: number): string {
  const s = v.toFixed(1);
  return lang === 'en' ? s : s.replace('.', ',');
}
function fmtUpdated(iso: string): string {
  // The "updated" field in the results JSON is an ISO timestamp; it is
  // always formatted in Finnish time (the race's official time zone), but
  // with language-appropriate text, since the file itself is not bilingual.
  const d = new Date(iso);
  const formatted = new Intl.DateTimeFormat(localeTag(), {
    day: 'numeric',
    month: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Europe/Helsinki',
  }).format(d);
  if (lang === 'fi') return `Päivitetty ${formatted} (Suomen aikaa)`;
  if (lang === 'fr') return `Mis à jour ${formatted} (heure d’Helsinki)`;
  return `Updated ${formatted} (Helsinki time)`;
}
function fmtStartLocal(stage: StageLike): string | null {
  if (!stage.startCEST) return null;
  const dateStr = stage.dateIso || stage.date;
  if (!dateStr) return null;
  const d = new Date(`${dateStr}T${stage.startCEST}:00+02:00`);
  return new Intl.DateTimeFormat(localeTag(), {
    hour: '2-digit',
    minute: '2-digit',
    timeZoneName: 'short',
  }).format(d);
}
function timeToHours(s: string | null | undefined): number | null {
  if (!s) return null;
  const str = String(s).trim();
  const mHms = /(\d+)\s*h\s*(\d+)\s*'\s*(\d+)/.exec(str);
  if (mHms) return +mHms[1] + +mHms[2] / 60 + +mHms[3] / 3600;

  const mMs = /^(\d+)\s*'\s*(\d+)/.exec(str);
  if (mMs) return +mMs[1] / 60 + +mMs[2] / 3600;

  const colonParts = str.split(':').filter((p) => /^\d+$/.test(p));
  if (colonParts.length === 3) {
    return +colonParts[0] + +colonParts[1] / 60 + +colonParts[2] / 3600;
  }
  if (colonParts.length === 2) {
    return +colonParts[0] / 60 + +colonParts[1] / 3600;
  }
  return null;
}
function esc(s: unknown): string {
  const entities: Record<string, string> = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
  };
  return String(s == null ? '' : s).replace(/[&<>"]/g, (c) => entities[c]);
}

// ---------- Profile & SVG math ----------
function buildPath(
  points: [number, number][],
  totalKm: number,
  W: number,
  H: number,
  padL: number,
  padR: number,
  padT: number,
  padB: number,
) {
  const plotW = W - padL - padR,
    plotH = H - padT - padB;
  const xs = points.map((p) => padL + (p[0] / totalKm) * plotW);
  const ys = points.map((p) => padT + plotH - (p[1] / 100) * plotH);
  let d = `M ${xs[0]},${ys[0]}`;
  for (let i = 1; i < xs.length; i++) {
    const mx = (xs[i - 1] + xs[i]) / 2;
    d += ` Q ${xs[i - 1]},${ys[i - 1]} ${mx},${(ys[i - 1] + ys[i]) / 2}`;
  }
  d += ` L ${xs[xs.length - 1]},${ys[xs.length - 1]}`;
  return { d, xs, ys, plotW, plotH };
}

function xForKm(km: number, totalKm: number, W: number, padL: number, padR: number): number {
  const plotW = W - padL - padR;
  return padL + (km / totalKm) * plotW;
}

function climbHeight(c: { len?: number; grad?: number }): number {
  const gain = (c.len || 4) * (c.grad || 5);
  return Math.max(40, Math.min(95, 36 + gain * 0.4));
}

function genProfile(st: StageLike): [number, number][] {
  if (st.profile && Array.isArray(st.profile) && st.profile.length) {
    return st.profile;
  }
  const pts: [number, number][] = [[0, 20]];
  (st.climbs || []).forEach((c) => {
    if (c.km == null) return;
    const startKm = Math.max(0, c.km - (c.len || 4));
    pts.push([+startKm.toFixed(1), 22]);
    pts.push([+c.km.toFixed(1), climbHeight(c)]);
  });
  if (st.summit && (st.climbs || []).length) {
    pts.push([+st.km.toFixed(1), 92]);
  } else {
    pts.push([+st.km.toFixed(1), 20]);
  }
  pts.sort((a, b) => a[0] - b[0]);
  const deduped: [number, number][] = [];
  pts.forEach((p) => {
    if (!deduped.length || p[0] > deduped[deduped.length - 1][0] + 0.5) deduped.push(p);
  });
  if (deduped[deduped.length - 1][0] < st.km) deduped.push([+st.km.toFixed(1), 20]);
  return deduped;
}

function catLabel(c: string): any {
  return (t('catLabels') || {})[c] || c;
}
function catChip(cat: string | null | undefined): string {
  return cat ? esc(String(cat)) : '—';
}
function climbsWithKm(st: StageLike) {
  return (st.climbs || []).filter((c) => c.km != null).sort((a, b) => a.km! - b.km!);
}
function genericProfile(st: StageLike): [number, number][] {
  const k = st.km,
    P = (frac: number, h: number): [number, number] => [+(k * frac).toFixed(1), h];
  if (st.type === 'itt') return [P(0, 20), P(0.5, 26), P(1, 22)];
  if (st.type === 'flat') return [P(0, 20), P(0.3, 25), P(0.5, 19), P(0.7, 27), P(1, 18)];
  if (st.type === 'hilly')
    return [P(0, 24), P(0.2, 46), P(0.4, 32), P(0.6, 55), P(0.8, 38), P(1, st.summit ? 88 : 44)];
  if (st.summit) return [P(0, 24), P(0.28, 50), P(0.48, 34), P(0.68, 60), P(0.82, 46), P(1, 94)];
  return [P(0, 30), P(0.25, 62), P(0.45, 40), P(0.65, 74), P(0.85, 46), P(1, 56)];
}
function profileLabel(): string {
  return lang === 'fi' ? 'Korkeusprofiili' : lang === 'fr' ? 'Profil' : 'Elevation profile';
}

// ---------- Tabs / panel layout ----------
function activateTab(tab: HTMLElement, setFocus: boolean): void {
  tabButtons.forEach((x) => {
    const selected = x === tab;
    x.classList.toggle('active', selected);
    x.setAttribute('aria-selected', selected ? 'true' : 'false');
    x.tabIndex = selected ? 0 : -1; // roving tabindex
  });
  document.querySelectorAll('.view').forEach((v) => v.classList.remove('active'));
  const targetView = document.getElementById('view-' + tab.dataset.view);
  if (targetView) targetView.classList.add('active');
  syncStageListHeight();
  if (setFocus) tab.focus();
}

function setupTabs(buttons: HTMLElement[], onTabChange?: (tab: HTMLElement) => void): void {
  buttons.forEach((tab, i) => {
    tab.addEventListener('click', () => {
      activateTab(tab, false);
      if (onTabChange) onTabChange(tab);
    });
    tab.addEventListener('keydown', (e) => {
      let idx: number | null = null;
      if (e.key === 'ArrowRight' || e.key === 'ArrowDown') idx = (i + 1) % buttons.length;
      else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp')
        idx = (i - 1 + buttons.length) % buttons.length;
      else if (e.key === 'Home') idx = 0;
      else if (e.key === 'End') idx = buttons.length - 1;
      if (idx !== null) {
        e.preventDefault();
        activateTab(buttons[idx], true);
        if (onTabChange) onTabChange(buttons[idx]);
      }
    });
  });
}

function positionPanel(): void {
  const panel = document.getElementById('panel');
  const stagelayout = document.querySelector('.stagelayout');
  const list = document.getElementById('stageList');
  if (!panel || !stagelayout || !list) return;
  list.querySelectorAll('.stage-detail-row').forEach((row) => row.remove());
  if (window.innerWidth <= 980) {
    const activeBtn = list.querySelector('.stage-btn.active');
    const activeLi = activeBtn ? activeBtn.closest('.stage-item') : null;
    if (activeLi) {
      const row = document.createElement('li');
      row.className = 'stage-detail-row';
      row.appendChild(panel);
      activeLi.insertAdjacentElement('afterend', row);
      return;
    }
  }
  stagelayout.appendChild(panel);
}

function cardBorderStyle(i: number, n: number): string {
  let s = '';
  if ((i + 1) % 2 !== 0 && i !== n - 1) s += 'border-right:2px solid var(--color-divider);';
  if (i < n - (n % 2 === 0 ? 2 : 1)) s += 'border-bottom:2px solid var(--color-divider);';
  return s;
}

function bindExpanders(grid: ParentNode): void {
  grid.querySelectorAll<HTMLButtonElement>('.expander').forEach((btn) => {
    btn.addEventListener('click', () => {
      if (btn.dataset.cls) {
        expandState[btn.dataset.cls] = !expandState[btn.dataset.cls];
        renderResults();
      }
    });
  });
}

// ---------- Stage map & controls ----------
function destroyStageMap(): void {
  if (stageMap) {
    try {
      stageMap.remove();
    } catch {}
    stageMap = null;
    stageMapFitBounds = null;
  }
}
function mapLabel(): string {
  return lang === 'fi' ? 'Reitti' : lang === 'fr' ? 'Parcours' : 'Route';
}
function zoomWord(): string {
  return lang === 'fi' ? 'zoomaus' : 'zoom';
}
function updateMapZoomLabel(): void {
  const el = document.getElementById('mapZoomLabel');
  if (el && stageMap) el.textContent = `${zoomWord()} ${stageMap.getZoom()}`;
}

const ZOOM_LABELS: Record<'fi' | 'en' | 'fr', { in: string; out: string }> = {
  fi: { in: 'Lähennä', out: 'Loitonna' },
  fr: { in: 'Zoom avant', out: 'Zoom arrière' },
  en: { in: 'Zoom in', out: 'Zoom out' },
};

function mapControlsHTML(big: boolean): string {
  const zl = ZOOM_LABELS[lang] || ZOOM_LABELS.en;
  let html =
    `<button class="mapctrl-btn" data-map-zoomout title="${zl.out}" aria-label="${zl.out}">−</button>` +
    `<button class="mapctrl-btn" data-map-zoomin title="${zl.in}" aria-label="${zl.in}">+</button>` +
    `<button class="mapctrl-btn" data-map-recenter title="${t('minimapRecenter')}" aria-label="${t('minimapRecenter')}">◎</button>`;
  html += big
    ? `<button class="mapctrl-btn mapctrl-close" data-map-toggle title="${t('minimapCollapse')}" aria-label="${t('minimapCollapse')}">×</button>`
    : `<button class="mapctrl-btn" data-map-toggle title="${t('minimapExpand')}" aria-label="${t('minimapExpand')}">⤢</button>`;
  return html;
}

function mapCellHTML(stage: StageLike): string {
  return `
    <span class="maprow">
      <span class="maplabel">${mapLabel()}</span>
      <span class="mapctrls">${mapControlsHTML(false)}</span>
    </span>
    <div id="stage-map" role="application" aria-label="${t('minimapAria')(stage.n)}"></div>
    <span class="mapzoom" id="mapZoomLabel"></span>`;
}

function bigMapBoxHTML(stage: StageLike): string {
  return `<div id="bigmapbox">
    <span class="maprow">
      <span class="maplabel">${mapLabel()}</span>
      <span class="mapctrls">${mapControlsHTML(true)}</span>
    </span>
    <div id="stage-map" role="application" aria-label="${t('minimapAria')(stage.n)}"></div>
    <span class="mapmeta">
      <span class="mapzoom" id="mapZoomLabel"></span>
      <span class="mapcaption" id="stage-map-caption"></span>
    </span>
  </div>`;
}

function bindMapControls(stage: StageLike, onToggleMap?: () => void): void {
  const zoomOutBtn = document.querySelector('[data-map-zoomout]');
  const zoomInBtn = document.querySelector('[data-map-zoomin]');
  const recenterBtn = document.querySelector('[data-map-recenter]');
  const toggleBtn = document.querySelector('[data-map-toggle]');
  if (zoomOutBtn)
    zoomOutBtn.addEventListener('click', () => {
      if (stageMap) stageMap.zoomOut();
    });
  if (zoomInBtn)
    zoomInBtn.addEventListener('click', () => {
      if (stageMap) stageMap.zoomIn();
    });
  if (recenterBtn)
    recenterBtn.addEventListener('click', () => {
      if (stageMapFitBounds) stageMapFitBounds();
    });
  if (toggleBtn)
    toggleBtn.addEventListener('click', () => {
      if (typeof mapExpanded !== 'undefined') {
        mapExpanded = !mapExpanded;
      }
      if (onToggleMap) {
        onToggleMap();
      } else if (typeof renderPanel === 'function') {
        renderPanel(stage);
        syncStageListHeight();
      }
    });
}

function initStageMapCommon(
  stage: StageLike,
  stageCoords?: Record<number | string, [[number, number], [number, number]]>,
  startColor?: string,
): void {
  if (!(window as any).L) {
    setTimeout(() => initStageMapCommon(stage, stageCoords, startColor), 120);
    return;
  }
  const el = document.getElementById('stage-map');
  if (!el) return;
  destroyStageMap();

  const L = (window as any).L;
  const map = L.map(el, { scrollWheelZoom: false, attributionControl: true, zoomControl: false });
  stageMap = map;
  L.tileLayer('https://tiles.stadiamaps.com/tiles/alidade_smooth/{z}/{x}/{y}{r}.png', {
    maxZoom: 17,
    attribution:
      '&copy; <a href="https://www.stadiamaps.com/">Stadia Maps</a> &copy; <a href="https://openmaptiles.org/">OpenMapTiles</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }).addTo(map);
  map.on('zoomend', updateMapZoomLabel);

  const css = getComputedStyle(document.documentElement);
  const INK = css.getPropertyValue('--color-text').trim() || '#201e1d';
  const ACCENT = css.getPropertyValue('--color-accent').trim() || '#ec3013';
  const startFill = startColor || INK;

  const draw = () => {
    if (stageMap !== map) return;
    const pts = (routesData.stages || {})[stage.n as any];
    const c = stageCoords && stage.n != null ? stageCoords[stage.n] : null;
    let line: [number, number][],
      startLL: [number, number],
      finishLL: [number, number],
      approx = false;
    if (pts && pts.length) {
      line = pts;
      startLL = pts[0];
      finishLL = pts[pts.length - 1];
    } else if (c && c.length >= 2) {
      approx = true;
      startLL = [c[0][1], c[0][0]];
      finishLL = [c[1][1], c[1][0]];
      line = [startLL, finishLL];
    } else {
      return;
    }
    const poly = L.polyline(
      line,
      approx
        ? { color: INK, weight: 3, opacity: 0.85, dashArray: '6,8' }
        : { color: INK, weight: 3.5, opacity: 0.95 },
    ).addTo(map);
    const same =
      Math.abs(startLL[0] - finishLL[0]) < 1e-4 && Math.abs(startLL[1] - finishLL[1]) < 1e-4;
    if (!same) {
      L.circleMarker(startLL, {
        radius: 6,
        color: '#fff',
        weight: 2,
        fillColor: startFill,
        fillOpacity: 1,
      }).addTo(map);
    }
    L.circleMarker(finishLL, {
      radius: 7,
      color: '#fff',
      weight: 2,
      fillColor: ACCENT,
      fillOpacity: 1,
    }).addTo(map);
    map.fitBounds(poly.getBounds(), { padding: [24, 24] });
    map.invalidateSize();
    stageMapFitBounds = () => {
      if (stageMap === map) map.fitBounds(poly.getBounds(), { padding: [24, 24] });
    };
    const cap = document.getElementById('stage-map-caption');
    if (cap) cap.textContent = approx ? t('minimapCaptionApprox') : t('minimapCaption');
    updateMapZoomLabel();
  };

  if (routesData) draw();
  else
    loadRoutes().then(() => {
      if (stageMap === map) draw();
    });
  setTimeout(() => {
    if (stageMap === map) map.invalidateSize();
  }, 60);
}

// ---------- Weather helpers ----------
function wxFor(n: number | string): any {
  return (WEATHER && WEATHER.stages && WEATHER.stages[String(n)]) || null;
}
function wxCellHTML(d: any, kicker: string): string {
  const conds = t('wxConds') || {},
    dirs = t('wxDirs') || {};
  const rows = [
    { label: t('wxLow'), value: `${d.low}°` },
    { label: t('wxWind'), value: `${d.wind} km/h ${dirs[d.dir] || d.dir}` },
    { label: t('wxRain'), value: d.precip ? `${d.precip.toLocaleString(localeTag())} mm` : '—' },
    { label: t('wxHumidity'), value: `${d.humidity} %` },
  ];
  if (d.alt) rows.push({ label: t('wxAlt'), value: fmtGain(d.alt) });
  return `
    <div class="wxcell">
      <div class="wxhead">
        <span class="wxkicker">${kicker}</span>
        <span class="wxplace">${d.town}</span>
      </div>
      <div class="wxtempline">
        <span class="wxtemp">${d.temp}°</span>
        <div class="wxcondwrap">
          <span class="wxcond">${conds[d.cond] || d.cond}</span>
          <span class="wxfeels">${t('wxFeels')} ${d.feels}°</span>
        </div>
      </div>
      <div class="wxrows">
        ${rows.map((r) => `<div class="wxrowitem"><span class="label">${r.label}</span><span class="value">${r.value}</span></div>`).join('')}
      </div>
    </div>`;
}

function wxSectionHTML(stage: StageLike): string {
  const w = wxFor(stage.n as any);
  let deltaHTML = '';
  if (w && w.start && w.finish) {
    const diff = w.finish.temp - w.start.temp;
    const sign = diff > 0 ? '+' : diff < 0 ? '−' : '±';
    deltaHTML = `
      <span class="wxdelta">
        <span class="value">${sign}${Math.abs(diff)} °C</span>
        <span class="unit">${t('wxDelta')}</span>
      </span>`;
  }
  return `
    <div class="wxrow">
      <span class="label">${t('wxHeader')}</span>
      ${deltaHTML}
    </div>
    ${
      w && w.start && w.finish
        ? `<div class="wxgrid">${wxCellHTML(w.start, t('wxAtStart'))}${wxCellHTML(w.finish, t('wxAtFinish'))}</div>
         <p class="wxnote"><span>${t('wxNote')}</span></p>`
        : `<p class="wxnodata">${t('wxNoData')}</p>`
    }
  `;
}

// ---------- Results & start list helpers ----------
function loadRoutes(): Promise<any> {
  if (routesData) return Promise.resolve(routesData);
  if (!routesPromise) {
    routesPromise = fetch(ROUTES_URL, { cache: 'no-cache' })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        routesData = d && d.stages ? d : { stages: {} };
        return routesData;
      })
      .catch(() => {
        routesData = { stages: {} };
        return routesData;
      });
  }
  return routesPromise;
}

function riddenStages(): any[] {
  return RESULTS.stageWinners.filter((s: any) => {
    const sr = RESULTS.stageResults[s.n];
    return (sr && Array.isArray(sr.rows) && sr.rows.length) || s.winner || s.cancelled;
  });
}

function stageAvgSpeed(n: number | string): number | null {
  const sr = RESULTS.stageResults[n];
  const st = stages.find((s) => s.n === Number(n));
  if (!sr || !st || !Array.isArray(sr.rows) || !sr.rows.length) return null;
  const h = timeToHours(sr.rows[0].val);
  return h ? st.km / h : null;
}

function stageStatTable(rows: any[], expKey: string): string {
  if (!rows.length) return `<p class="empty-cls">${t('stageStatEmpty')}</p>`;
  const expanded = !!expandState[expKey];
  const shown = expanded ? rows : rows.slice(0, 10);
  let body = `<table class="results"><tbody>${shown.map(resultRowHTML).join('')}</tbody></table>`;
  if (rows.length > 10) {
    body += `<button class="expander" data-cls="${expKey}">${expanded ? t('expandLess') : t('expandMore')(rows.length)}</button>`;
  }
  return body;
}

function riderRowHTML(r: any): string {
  const out = !!r.status;
  const reasons = t('withdrawalReasons') || {};
  const sub = out
    ? `${reasons[r.status] || r.status} · ${r.statusStage ? t('riderOutOnStage')(r.statusStage) : t('riderOutUnknown')}`
    : r.nat || '';
  const gcPos = out ? '—' : r.gcPos || '—';
  const val = out ? '' : r.gcGap || r.gcVal || '';
  return `
    <tr class="${out ? 'out' : r.gcPos && r.gcPos <= 3 ? 'podium' : ''}">
      <td class="bib">${r.bib != null ? r.bib : '–'}</td>
      <td class="rider"><span class="rname">${r.name}</span>${sub ? `<span class="rsub">${sub}</span>` : ''}</td>
      <td class="gcpos">${gcPos}</td>
      <td class="val">${val}</td>
    </tr>`;
}
