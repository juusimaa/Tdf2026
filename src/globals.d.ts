// Globals that each page's own inline <script> defines (lang, STRINGS,
// RESULTS, stages, WEATHER, stageMap, expandState, tabButtons,
// resultRowHTML, mapExpanded, renderPanel, etc — see the header comment in
// race-page.ts). Those inline scripts are still plain JS, loaded right after
// race-page.js into the same non-module top-level scope, so race-page.ts
// can't see their real declarations. These ambient declarations exist only so
// tsc can check race-page.ts; they are not enforced against the inline scripts.
declare let lang: 'fi' | 'en' | 'fr';
declare const LANG_KEY: string;
declare const STRINGS: Record<'fi' | 'en' | 'fr', Record<string, any>>;
declare const tabButtons: HTMLElement[];
declare function syncStageListHeight(): void;
declare const expandState: Record<string, boolean>;
declare function renderResults(): void;
declare function renderPanel(stage: any): void;
declare let stageMap: any;
declare let stageMapFitBounds: any;
declare let routesData: any;
declare let routesPromise: Promise<any> | null;
declare const ROUTES_URL: string;
declare let WEATHER: any;
declare let mapExpanded: boolean;
declare const RESULTS: any;
declare const stages: any[];
declare function resultRowHTML(row: any): string;
declare const STAGE_COORDS: Record<number | string, [[number, number], [number, number]]>;
declare const CAT_COLOR: Record<string, string>;
declare const JERSEY: Record<string, string>;
declare const AUX_SWATCH: Record<string, string>;
declare const CLASS_KEYS: string[];
