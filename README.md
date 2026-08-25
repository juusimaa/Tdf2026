# Grand tour — self-updating results page

A results site for the 2026 grand tours: Tour de France, Giro d'Italia, Tour
de France Femmes and Vuelta a España. Results, start lists, routes and
weather all live in per-tour files (`data/<tour>-*.json`), so the whole site
covers all four races from one **tour-aware** codebase. Only the Vuelta is
still being raced (22 Aug – 13 Sep 2026); it keeps its own results and
weather current automatically, while the other three are finished and serve
static data.

```
index.html                            # "Grand Tours" landing page (race picker)
tdf2026.html                          # Tour de France — stages, profiles, map & final results (static)
giro2026.html                         # Giro d'Italia — stages, profiles, map & final results (static)
femmes2026.html                       # Tour de France Femmes — stages, profiles, map & final results (static)
vuelta2026.html                       # Vuelta a España — stages, profiles, map & auto-updating results (live)
src/race-page.ts                      # helper functions shared by all four race pages (i18n, formatting, rendering) — compiles to dist/race-page.js
src/globals.d.ts                      # ambient types for the globals each page's own inline <script> defines
dist/race-page.js                     # build output (gitignored) — what the HTML pages actually load, via `npm run build`
race-page.css                         # shared component styles for all four race pages, layered on modernist.css
modernist.css                         # shared design tokens (colour, type, spacing) used by every page
theme.css                             # earlier colour theme — no longer linked from any page, kept for reference

data/<tour>-results.json              # classifications + stage winners — auto-updated for vuelta2026, static for the rest
data/<tour>-riders.json               # start list: teams, riders, each rider's GC position/gap
data/<tour>-routes.json               # per-stage route tracks for the map, from GPX/komoot (see fetch_routes.py)
data/tdf2026-weather.json             # actual race-day weather, all 21 stages (race is over)
data/vuelta2026-weather.json          # actual race-day weather, raced stages only — auto-updated

scripts/fetch_results.py              # results fetch script (scrapes letour.fr / lavuelta.es); also holds cancelled-stage overrides
scripts/fetch_riders.py               # start-list fetch script (letour.fr, letourfemmes.fr, lavuelta.es, giroditalia.it)
scripts/fetch_routes.py               # route fetch script (cyclingstage.com GPX, or komoot for the Vuelta) — run by hand
scripts/fetch_weather.py              # race-day weather fetch script (Open-Meteo historical archive)
.github/workflows/update-results.yml  # GitHub Actions build & publish workflow
```

`index.html` lets the visitor pick a race; each tour page has a back arrow to
the landing page.

### Local development

The four race pages' own per-page logic is still plain JS, inline in each
HTML file — only the shared helpers in `src/race-page.ts` are TypeScript.
Browsers can't run `.ts` directly, so it needs a build step:

```
npm install       # once
npm run build     # compiles src/race-page.ts -> dist/race-page.js
npm run watch     # or: rebuild on every save, while editing
```

`dist/` is gitignored (build output, not source) — run `npm run build` after
a fresh clone before opening any page locally, or nothing will render. CI
does this automatically (see the workflow) before every deploy, so
`dist/race-page.js` is always rebuilt fresh from `src/race-page.ts`.

### Live vs. static tours

- **Vuelta a España** (`vuelta2026`) is the only *live* tour right now: it is
  registered in the `TOURS` dict in `scripts/fetch_results.py` (scraping
  lavuelta.es) and in `scripts/fetch_weather.py`, so the scheduled workflow
  keeps `data/vuelta2026-results.json` and `data/vuelta2026-weather.json`
  current as stages are raced.
- **Tour de France** (`tdf2026`) is a *finished* race but stays registered in
  `fetch_results.py`'s `TOURS`: the workflow still polls letour.fr for it on
  every run, but the final data never changes, so it just re-confirms the
  same result and never produces an empty commit (see "How it works" below).
- **Giro d'Italia** (`giro2026`) and **Tour de France Femmes** (`femmes2026`)
  are *finished* and **static**: their classifications and stage winners are
  stored once in `data/<tour>-results.json` (same schema as the others) and
  never refetched, because they are **not** in `fetch_results.py`'s `TOURS`
  registry at all. (They *are* registered in `fetch_riders.py`, which is only
  ever run by hand — see below.) Their Stages tabs (routes, distances,
  illustrative profiles) are built from a small hardcoded `stages` array in
  each page itself.

To add a live tour, register it in `fetch_results.py`'s `TOURS` (with a
source handler) and point a page at its `data/<tour>-results.json`. To add a
finished race, drop a static `data/<tour>-results.json` in place and build a
page that reads it — no script or registry entry needed.

## How it works

1. GitHub Actions runs the workflow on every push to `main` and on demand
   from the Actions tab. While the Vuelta is being raced it also runs on a
   schedule (every 30 minutes, 14:00–19:30 UTC on race days, plus a light
   run at 06:15 UTC for late corrections) — see the `cron:` entries at the top of
   `.github/workflows/update-results.yml`. That schedule block is meant to be
   removed once the Vuelta finishes (13 Sep 2026), the same way it was
   removed after the Tour de France, so the workflow doesn't keep polling a
   site with nothing left to fetch.
2. The workflow runs `fetch_results.py`, which scrapes the official rankings
   pages of every tour in its `TOURS` registry (currently letour.fr for
   `tdf2026`, lavuelta.es for `vuelta2026`): general classification, points,
   mountains, youth and team classifications, plus the winner of every stage
   raced so far.
3. The script writes `data/<tour>-results.json` for each registered tour. If
   the content changed, the workflow commits it back to the repo.
4. GitHub Pages serves the site, and each tour page fetches the JSON for its
   tour in the browser (e.g. `vuelta2026.html` → `fetch('data/vuelta2026-results.json')`).
   The page therefore always shows the latest committed standings with zero
   manual intervention.

The page also **auto-selects the stage of the day** when opened (the next
stage on rest days, the final stage once the race is over).

### Cancelled stages

A stage that is called off (bad weather, a security incident, …) never gets
result pages on the organiser's site, so the scraper alone can't represent
it — left alone, it would just look like "not raced yet" forever. Instead,
`fetch_results.py` has a hand-maintained `CANCELLED_STAGES` dict, keyed by
`(tour_id, stage_no)`, mapping to a reason code:

```python
CANCELLED_STAGES = {
    ("vuelta2026", 3): "weather",
}
```

Every run applies this unconditionally — it skips fetching that stage
entirely and writes `cancelled`/`cancelledReason` onto both its
`stageWinners` and `stageResults` entries — so the flag survives the next
scrape instead of being silently overwritten. The reason code must match a
key in the page's own `cancelledReasons` translation table (in `<tour>.html`'s
`STRINGS`), which renders the localized message and lets the cancelled stage
still be picked from the results dropdown.

### Teams & riders tab

Every race page has a third tab listing every team and rider, with each
rider's current or final general-classification position and gap to the
leader/winner. All four read `data/<tour>-riders.json`, written by
`scripts/fetch_riders.py` in one shared schema — but the organisers' sites
differ enough that the script has one handler per source family:

- **letour.fr / letourfemmes.fr / lavuelta.es** (`tdf2026`, `femmes2026`,
  `vuelta2026`) — ASO's Tour sites and Unipublic's Vuelta site share the same
  template, so one `"letour"` handler covers all three. It reads the start
  list at `/en/riders`, joined to the general classification and the
  per-stage withdrawal list **by bib number**; the displayed rider names
  differ between those pages, the bib does not. A rider who left the race
  therefore carries a DNS/DNF/OTL reason and the stage.
- **giroditalia.it** (`giro2026`) — teams from `/en/squadre/` and their
  rosters from each team page, joined to the final classifications **by
  athlete-page slug**. RCS never prints bib numbers, but every rider link
  carries one as `data-destination="Rider/<bib>"` (1–8 for the first team,
  11–18 for the second, … 221–228 — the Giro's own numbering), so the riders
  still get bibs and are listed in start-list order. Withdrawals are one
  table per stage page instead of a single list, so the script walks the
  stage pages to find the stage each rider left; without a published reason
  they are all reported as DNF. Times are restated from `83:22:51` into the
  same `83h 22' 51''` form the other tours use.

The script is deliberately **not** part of the workflow: a start list changes
only when riders drop out, so it is run by hand when the data needs a
refresh. Re-running it rewrites nothing unless the content actually changed,
so it never produces an empty commit:

```
pip install requests selectolax
python scripts/fetch_riders.py                              # every registered tour
python scripts/fetch_riders.py tdf2026 giro2026 vuelta2026   # specific tours
```

### Routes & the stage map

Each race page's expanded stage view draws the real route on a Leaflet map,
from a per-stage GPX track in `data/<tour>-routes.json`. `scripts/fetch_routes.py`
builds that file from one of two sources per race:

- **cyclingstage.com** GPX exports (`tdf2026`, `giro2026`, `femmes2026`) — a
  public, free-to-download third-party reconstruction of the route.
- **komoot** (`vuelta2026`) — the organiser's own official komoot account
  (`lavuelta`), which is the actual GPS-recorded course rather than a
  reconstruction, and is preferred wherever the organiser publishes one.

Each track is simplified with Ramer–Douglas–Peucker so the shipped file stays
small (the map is an overview locator, not turn-by-turn nav — ~50 m of
simplification is invisible at that zoom), and stored as `[lat, lon]` pairs
rounded to 5 decimals. A stage whose route hasn't been published yet is
simply omitted; the page falls back to a straight start→finish line for it.
Like `fetch_riders.py`, this script is run by hand, not part of the workflow:

```
python3 scripts/fetch_routes.py            # default: tdf2026
python3 scripts/fetch_routes.py vuelta2026
python3 scripts/fetch_routes.py all
```

### Weather

`tdf2026.html` and `vuelta2026.html` each show a "Race-day weather" block per
stage — actual recorded conditions (not a forecast), a daily high/low/feels
at the stage's start and finish location, sourced from Open-Meteo's free
historical archive (`archive-api.open-meteo.com`, no API key). A stage only
ever shows once its race day has fully passed, both in what gets fetched and
in what the page renders — a stage still being raced never shows a same-day,
not-yet-final reading. The Tour de France is over, so `tdf2026.html` always
shows all 21 stages; `vuelta2026.html` fills in day by day as the race is
run. `giro2026.html` and `femmes2026.html` don't have a weather block; their
tours aren't registered in `fetch_weather.py`'s `TOURS`.

`scripts/fetch_weather.py` is part of the same scheduled workflow as
`fetch_results.py` (see "How it works" above): every run, it checks each
registered tour's stage schedule against today's date (in the race's own
time zone), fetches any newly-finished stage's weather at its start/finish
coordinates (the first/last point of `data/<tour>-routes.json`, or a small
hardcoded `coords_fallback` for the handful of Tour stages that routes file
has no GPX points for), and writes `data/<tour>-weather.json`. A stage
already in that file is never re-fetched — a past day's weather doesn't
change — so most runs do nothing, and the workflow commits
`data/*-weather.json` alongside results only when something new was actually
fetched. Add another tour to the `TOURS` dict in `fetch_weather.py`, with its
stage schedule and time zone, to cover it too.

## Why letour.fr and not procyclingstats.com

The site originally scraped procyclingstats.com via the `procyclingstats`
Python package. That site sits behind Cloudflare bot protection, which
blocks plain scraper traffic — and blocks it *harder* from GitHub Actions'
datacenter IPs than from a home network, to the point where even
`cloudscraper` (a Cloudflare-bypass library) couldn't reliably get through.
letour.fr, the official Tour de France site, serves its rankings as plain
server-rendered HTML with no such protection, so `fetch_results.py` scrapes
it directly with `requests` + `selectolax` instead — and the same approach
covers lavuelta.es too, since Unipublic's Vuelta site is built on the
identical template.

Each classification is fetched and parsed independently, so a change to
letour.fr's or lavuelta.es's HTML that breaks one table (e.g. mountains)
doesn't take down the others — check the Actions log for warnings if a table
stops updating.

## License & disclaimer

The **source code** of this project (`index.html`, `scripts/`, and the
GitHub Actions workflow) is released under the [MIT License](LICENSE) — feel
free to use, modify, and share it.

The **results data**, however, is a different matter and the MIT license does
**not** extend to it:

- This is an unofficial, non-commercial fan project. It is **not affiliated
  with, endorsed by, or connected to** Amaury Sport Organisation (A.S.O.),
  RCS Sport, Unipublic, letour.fr, letourfemmes.fr, giroditalia.it,
  lavuelta.es, or the races themselves.
- Race results shown here are fetched from those organisers' own sites and
  remain the property of their respective owners. No ownership of, or rights
  to, that data are claimed or granted by this project.
- "Tour de France", "Giro d'Italia", "Tour de France Femmes", "Vuelta a
  España" and related names and logos are trademarks of their respective
  organisers and are used here only descriptively to identify the events.

If you reuse this code, you are responsible for sourcing your own data and
complying with the terms of whatever source you use.
