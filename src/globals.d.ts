// Globals that each page's own inline <script> defines (lang, STRINGS,
// RESULTS, stages, WEATHER, stageMap, expandState, tabButtons,
// resultRowHTML, etc — see the header comment in race-page.ts). Those inline
// scripts are still plain JS, loaded right after race-page.js into the same
// non-module top-level scope, so race-page.ts can't see their real
// declarations. These ambient declarations exist only so tsc can check
// race-page.ts; they are not enforced against the inline scripts themselves.
declare let lang: 'fi' | 'en' | 'fr';
declare const LANG_KEY: string;
declare const STRINGS: Record<'fi' | 'en' | 'fr', Record<string, any>>;
declare const tabButtons: HTMLElement[];
declare function syncStageListHeight(): void;
declare const expandState: Record<string, boolean>;
declare function renderResults(): void;
declare let stageMap: any;
declare let stageMapFitBounds: any;
declare let routesData: any;
declare let routesPromise: Promise<any> | null;
declare const ROUTES_URL: string;
declare const WEATHER: any;
declare const RESULTS: any;
declare const stages: any[];
declare function resultRowHTML(row: any): string;
