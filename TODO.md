# TODO

## Epic

- New landing page: pick a year, then a race. `index.html` already does the race picker (Giro/TdF/Vuelta/Femmes grid) — this adds a year selector in front of it, defaulting to the current year. One page is fine; needs a `<year>/<race>` or `?year=` scheme once a second season's pages exist (today everything is hardcoded to `*2026.html`).

#### Minor

- Fix stage-profile marker colors to match the official convention (climbs red, sprints green). Right now climbs and intermediate sprints render in the _same_ color family — climbs use `CAT_COLOR` (accent-derived shades) and sprints use `var(--color-accent)`, and the site accent is already a red/orange, so on the chart they're barely distinguishable. Marker code is duplicated per page in each `renderProfile()`: `tdf2026.html`, `giro2026.html`, `femmes2026.html` (all three already draw sprint markers), and `vuelta2026.html` (climbs only for now — sprint locations aren't published yet). Note that color are different for each race.

## Tooling / educational

- PWA support (service worker + manifest) so the race tracker is installable and usable offline/with a flaky connection at the roadside.
- Consider React (+ Vite) for the per-page rendering logic, which today is direct DOM manipulation in each page's inline `<script>`. Worth trying on a single page first (e.g. `tdf2026.html`) as a proof of concept before deciding whether to carry it to the rest — real tooling step up (adds a bundler/JSX) for what's currently a plain `tsc` compile.
