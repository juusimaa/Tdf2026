# TODO

## Epic
* New landing page: pick a year, then a race. `index.html` already does the race picker (Giro/TdF/Vuelta/Femmes grid) — this adds a year selector in front of it, defaulting to the current year. One page is fine; needs a `<year>/<race>` or `?year=` scheme once a second season's pages exist (today everything is hardcoded to `*2026.html`).

### Major
* Scheduled updates for the Vuelta while it's racing (22 Aug – 13 Sep 2026). Two gaps to close in `scripts/fetch_results.py`:
  1. `TOURS` only registers `tdf2026` (source `letour`, scraping letour.fr). There's no Vuelta source handler yet — letour.fr doesn't cover it, so this needs a new scraper against whatever site publishes La Vuelta's live standings.
  2. `.github/workflows/update-results.yml` had its `schedule:` trigger deliberately removed once the Tour ended (see the comment at the top of the file) — re-add a cron block once the Vuelta handler exists, so results actually get polled during the race instead of only on push.

#### Minor
* Fix stage-profile marker colors to match the official convention (climbs red, sprints green). Right now climbs and intermediate sprints render in the *same* color family — climbs use `CAT_COLOR` (accent-derived shades) and sprints use `var(--color-accent)`, and the site accent is already a red/orange, so on the chart they're barely distinguishable. Marker code is duplicated per page in each `renderProfile()`: `tdf2026.html`, `giro2026.html`, `femmes2026.html` (all three already draw sprint markers), and `vuelta2026.html` (climbs only for now — sprint locations aren't published yet). Note that color are different for each race.
