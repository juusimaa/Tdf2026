# TODO

## Epic

- New landing page: pick a year, then a race. `index.html` already does the race picker (Giro/TdF/Vuelta/Femmes grid) — this adds a year selector in front of it, defaulting to the current year. One page is fine; needs a `<year>/<race>` or `?year=` scheme once a second season's pages exist (today everything is hardcoded to `*2026.html`).

#### Minor

- Fix stage-profile marker colors to match the official convention (climbs red, sprints green) in `tdf2026.html`, `giro2026.html` and `femmes2026.html`. In those three, climbs and intermediate sprints render in the _same_ color family — climbs use `CAT_COLOR` (accent-derived shades) and sprints use `var(--color-accent)`, and the site accent is already a red/orange, so on the chart they're barely distinguishable. `vuelta2026.html` is already done (3a40e11): it draws sprints in a dedicated `SPRINT_COLOR = '#3e9b4f'` with a matching legend swatch, on the 19 of 21 stages whose sprint locations are published — copy that pattern. The marker code is still duplicated per page in each `renderProfile()` (`src/race-page.ts` shares the profile geometry, not the marker drawing), so the fix has to be made three times. Note that the climb categories, and their colors, differ per race.

## Tooling / educational

- PWA support (service worker + manifest) so the race tracker is installable and usable offline/with a flaky connection at the roadside.
- Consider React (+ Vite) for the per-page rendering logic, which today is direct DOM manipulation in each page's inline `<script>`. Worth trying on a single page first (e.g. `tdf2026.html`) as a proof of concept before deciding whether to carry it to the rest — real tooling step up (adds a bundler/JSX) for what's currently a plain `tsc` compile.
