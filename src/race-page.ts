/* ============================================================================
   Race page shared logic — identical helper functions used by tdf2026.html,
   giro2026.html, vuelta2026.html, femmes2026.html. Compiled to
   dist/race-page.js and loaded as a classic (non-module) script right before
   each page's own inline <script>, so it shares the same top-level scope:
   these functions freely reference globals each page defines itself (lang,
   STRINGS, LANG_KEY, ROUTES_URL, RESULTS, stages, WEATHER, stageMap,
   expandState, tabButtons, resultRowHTML, etc — see globals.d.ts for their
   ambient declarations). Page-specific rendering logic (renderAll,
   renderResults, initStageMap, ...) stays inline per page since it depends
   on that page's data shape.
   ============================================================================ */

// A stage object's shape differs slightly per tour (e.g. dateIso vs date),
// so this only covers the fields the functions below actually read.
type StageLike = {
  km: number;
  type?: string;
  summit?: unknown;
  climbs?: { km: number | null }[];
};

// ---------- Language / i18n ----------
function detectLang(): 'fi' | 'en' | 'fr' {
  const saved = localStorage.getItem(LANG_KEY);
  if(saved==='fi' || saved==='en' || saved==='fr') return saved;
  const nav = (navigator.language||'en').toLowerCase();
  if(nav.startsWith('fi')) return 'fi';
  if(nav.startsWith('fr')) return 'fr';
  return 'en';
}
function localeTag(): string {
  return lang==='fi' ? 'fi-FI' : lang==='fr' ? 'fr-FR' : 'en-GB';
}
function t(key: string): any {
  const v = STRINGS[lang][key];
  return v !== undefined ? v : STRINGS.en[key];
}
function updateLangButtons(): void {
  document.querySelectorAll<HTMLButtonElement>('#langSel button').forEach(b=>{
    const active = b.dataset.lang===lang;
    b.classList.toggle('active', active);
    b.setAttribute('aria-pressed', active ? 'true' : 'false');
  });
}

// ---------- Formatting ----------
function fmtDate(iso: string): string {
  const d = new Date(iso+'T12:00:00');
  const opts: Intl.DateTimeFormatOptions = lang==='fi'
    ? {weekday:'short', day:'numeric', month:'numeric'}
    : {weekday:'short', day:'numeric', month:'short'};
  return new Intl.DateTimeFormat(localeTag(), opts).format(d);
}
function fmtKm(k: number): string {
  const s = (Math.round(k*10)/10).toString();
  // English uses a decimal point; fi and fr use a comma.
  return (lang==='en' ? s : s.replace('.',',')) + ' km';
}
function fmtGain(m: number): string {
  return m.toLocaleString(localeTag()) + ' m';
}
function fmtSpeed(v: number): string {
  const s = v.toFixed(1);
  return lang==='en' ? s : s.replace('.', ',');
}
function fmtUpdated(iso: string): string {
  // The "updated" field in the results JSON is an ISO timestamp; it is
  // always formatted in Finnish time (the race's official time zone), but
  // with language-appropriate text, since the file itself is not bilingual.
  const d = new Date(iso);
  const formatted = new Intl.DateTimeFormat(localeTag(), {
    day:'numeric', month:'numeric', year:'numeric', hour:'2-digit', minute:'2-digit',
    timeZone:'Europe/Helsinki'
  }).format(d);
  if(lang==='fi') return `Päivitetty ${formatted} (Suomen aikaa)`;
  if(lang==='fr') return `Mis à jour ${formatted} (heure d’Helsinki)`;
  return `Updated ${formatted} (Helsinki time)`;
}
function timeToHours(s: string | null | undefined): number | null {
  const m = /(\d+)h\s*(\d+)'\s*(\d+)/.exec(s||'');
  if(!m) return null;
  return (+m[1]) + (+m[2])/60 + (+m[3])/3600;
}
function esc(s: unknown): string {
  const entities: Record<string, string> = {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'};
  return String(s==null?'':s).replace(/[&<>"]/g, c=>entities[c]);
}

// ---------- Tabs / panel layout ----------
function activateTab(tab: HTMLElement, setFocus: boolean): void {
  tabButtons.forEach(x=>{
    const selected = x===tab;
    x.classList.toggle('active', selected);
    x.setAttribute('aria-selected', selected ? 'true' : 'false');
    x.tabIndex = selected ? 0 : -1; // roving tabindex
  });
  document.querySelectorAll('.view').forEach(v=>v.classList.remove('active'));
  document.getElementById('view-'+tab.dataset.view)!.classList.add('active');
  syncStageListHeight();
  if(setFocus) tab.focus();
}
function positionPanel(): void {
  const panel = document.getElementById('panel');
  const stagelayout = document.querySelector('.stagelayout');
  const list = document.getElementById('stageList');
  if(!panel || !stagelayout || !list) return;
  list.querySelectorAll('.stage-detail-row').forEach(row=>row.remove());
  if(window.innerWidth<=980){
    const activeBtn = list.querySelector('.stage-btn.active');
    const activeLi = activeBtn ? activeBtn.closest('.stage-item') : null;
    if(activeLi){
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
  if((i+1)%2!==0 && i!==n-1) s += 'border-right:2px solid var(--color-divider);';
  if(i < n - (n%2===0?2:1)) s += 'border-bottom:2px solid var(--color-divider);';
  return s;
}
function bindExpanders(grid: ParentNode): void {
  grid.querySelectorAll<HTMLButtonElement>('.expander').forEach(btn=>{
    btn.addEventListener('click', ()=>{
      expandState[btn.dataset.cls!] = !expandState[btn.dataset.cls!];
      renderResults();
    });
  });
}

// ---------- Stage map ----------
function destroyStageMap(): void {
  if(stageMap){ try{ stageMap.remove(); }catch(e){} stageMap = null; stageMapFitBounds = null; }
}
function mapLabel(): string { return lang==='fi' ? 'Reitti' : lang==='fr' ? 'Parcours' : 'Route'; }
function zoomWord(): string { return lang==='fi' ? 'zoomaus' : 'zoom'; }
function updateMapZoomLabel(): void {
  const el = document.getElementById('mapZoomLabel');
  if(el && stageMap) el.textContent = `${zoomWord()} ${stageMap.getZoom()}`;
}

// ---------- Data loading & shared helpers ----------
function loadRoutes(): Promise<any> {
  if(routesData) return Promise.resolve(routesData);
  if(!routesPromise){
    routesPromise = fetch(ROUTES_URL, {cache:'no-cache'})
      .then(r => r.ok ? r.json() : null)
      .then(d => { routesData = (d && d.stages) ? d : {stages:{}}; return routesData; })
      .catch(() => { routesData = {stages:{}}; return routesData; });
  }
  return routesPromise;
}
function wxFor(n: number | string): any {
  return (WEATHER && WEATHER.stages && WEATHER.stages[String(n)]) || null;
}
function riddenStages(): any[] {
  return RESULTS.stageWinners.filter((s: any)=>{
    const sr = RESULTS.stageResults[s.n];
    return (sr && Array.isArray(sr.rows) && sr.rows.length) || s.winner || s.cancelled;
  });
}
function stageAvgSpeed(n: number | string): number | null {
  const sr = RESULTS.stageResults[n];
  const st = stages.find(s=>s.n===Number(n));
  if(!sr || !st || !Array.isArray(sr.rows) || !sr.rows.length) return null;
  const h = timeToHours(sr.rows[0].val);
  return h ? st.km / h : null;
}
function stageStatTable(rows: any[], expKey: string): string {
  if(!rows.length) return `<p class="empty-cls">${t('stageStatEmpty')}</p>`;
  const expanded = !!expandState[expKey];
  const shown = expanded ? rows : rows.slice(0,10);
  let body = `<table class="results"><tbody>${shown.map(resultRowHTML).join('')}</tbody></table>`;
  if(rows.length>10){
    body += `<button class="expander" data-cls="${expKey}">${expanded ? t('expandLess') : t('expandMore')(rows.length)}</button>`;
  }
  return body;
}
function catLabel(c: string): any {
  return t('catLabels')[c] || c;
}
function catChip(cat: string | null | undefined): string { return cat ? esc(String(cat)) : '—'; }
function climbsWithKm(st: StageLike) { return (st.climbs||[]).filter(c=>c.km!=null).sort((a,b)=>a.km!-b.km!); }
function genericProfile(st: StageLike): [number, number][] {
  const k=st.km, P=(frac: number, h: number): [number, number] =>[+(k*frac).toFixed(1),h];
  if(st.type==='itt') return [P(0,20),P(.5,26),P(1,22)];
  if(st.type==='flat') return [P(0,20),P(.3,25),P(.5,19),P(.7,27),P(1,18)];
  if(st.type==='hilly') return [P(0,24),P(.2,46),P(.4,32),P(.6,55),P(.8,38),P(1,st.summit?88:44)];
  if(st.summit) return [P(0,24),P(.28,50),P(.48,34),P(.68,60),P(.82,46),P(1,94)];
  return [P(0,30),P(.25,62),P(.45,40),P(.65,74),P(.85,46),P(1,56)];
}
function profileLabel(): string { return lang==='fi' ? 'Korkeusprofiili' : lang==='fr' ? 'Profil' : 'Elevation profile'; }
