# TODO

## Epic

- Year picker in front of the race list. Race pages already live under a
  season folder (`2026/<race>.html`, see `design_handoff_year_selection/`),
  and `index.html` links straight into `2026/` since it's the only season —
  still needed: the actual year-selection screen (remembers the visitor's
  choice in `localStorage["gt-year"]`, `?year=` override, "Change year"
  button), which only makes sense once a second season's pages
  (`2027/<race>.html`) exist.

#### Minor

- Fix stage-profile marker colors to match the official convention (climbs red, sprints green) in `2026/tdf.html`, `2026/giro.html` and `2026/femmes.html`. In those three, climbs and intermediate sprints render in the _same_ color family — climbs use `CAT_COLOR` (accent-derived shades) and sprints use `var(--color-accent)`, and the site accent is already a red/orange, so on the chart they're barely distinguishable. `2026/vuelta.html` is already done (3a40e11): it draws sprints in a dedicated `SPRINT_COLOR = '#3e9b4f'` with a matching legend swatch, on the 19 of 21 stages whose sprint locations are published — copy that pattern. The marker code is still duplicated per page in each `renderProfile()` (`src/race-page.ts` shares the profile geometry, not the marker drawing), so the fix has to be made three times. Note that the climb categories, and their colors, differ per race.

## Tooling / educational

- PWA support (service worker + manifest) so the race tracker is installable and usable offline/with a flaky connection at the roadside.
- Consider React (+ Vite) for the per-page rendering logic, which today is direct DOM manipulation in each page's inline `<script>`. Worth trying on a single page first (e.g. `2026/tdf.html`) as a proof of concept before deciding whether to carry it to the rest — real tooling step up (adds a bundler/JSX) for what's currently a plain `tsc` compile.
