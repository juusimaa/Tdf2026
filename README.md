# Grand tour — self-updating results page

A results site for the 2026 grand tours. The Tour de France page keeps itself
up to date automatically; results live in per-tour files
(`data/<tour>-results.json`) so the site covers all three grand tours (Tour de
France, Giro d'Italia, Vuelta a España) from one **tour-aware** codebase.

```
index.html                            # "Grand Tours" landing page (tour picker)
tdf2026.html                          # Tour de France — stages + auto-updating results
giro2026.html                         # Giro d'Italia — stages, profiles & final results (static)
vuelta2026.html                       # Vuelta a España — stages & profiles (preview, race not started)
data/tdf2026-results.json             # Tour de France results — auto-updated
data/tdf2026-riders.json              # Tour de France start list: teams, riders, final GC
data/giro2026-results.json            # Giro d'Italia final results — static
data/giro2026-riders.json             # Giro d'Italia start list: teams, riders, final GC
scripts/fetch_results.py              # results fetch script (scrapes letour.fr)
scripts/fetch_riders.py               # start-list fetch script (letour.fr + giroditalia.it)
.github/workflows/update-results.yml  # GitHub Actions build & publish workflow
```

`index.html` lets the visitor pick a race; each tour page has a back arrow to
the landing page. The Vuelta page is a route preview until that race starts.

### Live vs. static tours

- **Tour de France** (`tdf2026`) is a *live* tour: it is registered in the
  `TOURS` dict in `scripts/fetch_results.py`, and the scheduled workflow
  scrapes letour.fr and rewrites `data/tdf2026-results.json` as stages finish.
- **Giro d'Italia** (`giro2026`) is a *finished* race, so it is **static**:
  its final classifications and stage winners are stored once in
  `data/giro2026-results.json` (same schema as the Tour file) and never
  refetched. It is deliberately **not** in `fetch_results.py`'s `TOURS`
  registry, so the workflow leaves it untouched. (It *is* registered in
  `fetch_riders.py`, which is only ever run by hand — see below.)
  `giro2026.html` reads that JSON for the
  Results tab; its Stages tab (routes, distances, illustrative profiles) is
  built from a small hardcoded `stages` array in the page itself.

To add a live tour, register it in `TOURS` (with a source handler) and point a
page at its `data/<tour>-results.json`. To add a finished race, drop a static
`data/<tour>-results.json` in place and build a page that reads it — no script
or registry entry needed.

## How it works

1. GitHub Actions runs the workflow on every push to `main` and on demand from
   the Actions tab. While the Tour was being raced it also ran on a schedule
   (every 30 minutes, 14:00–20:00 UTC in July, plus a light morning run for
   late corrections); those `schedule:` entries were removed once the 2026
   race finished and are worth restoring for the next live race.
2. The workflow runs `fetch_results.py`, which scrapes the official
   **letour.fr** rankings pages for the latest completed stage: general
   classification, points, mountains, youth, and team classifications,
   plus the winner of every stage raced so far.
3. The script writes `data/tdf2026-results.json` (one file per registered
   tour). If the content changed, the workflow commits it back to the repo.
4. GitHub Pages serves the site, and each tour page fetches the JSON for its
   tour in the browser (`tdf2026.html` → `fetch('data/tdf2026-results.json')`).
   The page therefore always shows the latest committed standings with zero
   manual intervention.

The page also **auto-selects the stage of the day** when opened (the next
stage on rest days, the final stage once the race is over).

### Teams & riders tab

`tdf2026.html` and `giro2026.html` each have a third tab listing every team and
rider of that race, with each rider's final general-classification position and
gap to the winner. Both read `data/<tour>-riders.json`, written by
`scripts/fetch_riders.py` in one shared schema — but the two organisers'
sites publish very different things, so the script has one handler per source:

- **letour.fr** (`tdf2026`) — start list at `/en/riders`, joined to the general
  classification and the per-stage withdrawal list **by bib number**; the
  displayed rider names differ between those pages, the bib does not. A rider
  who left the race therefore carries a DNS/DNF/OTL reason and the stage.
- **giroditalia.it** (`giro2026`) — teams from `/en/squadre/` and their rosters
  from each team page, joined to the final classifications **by athlete-page
  slug**. RCS publishes no bib numbers and no withdrawal list, so riders have
  no bib and a non-finisher is only known as "did not finish". Times are
  restated from `83:22:51` into the same `83h 22' 51''` form the Tour data uses.

The script is deliberately **not** part of the workflow: a start list changes
only when riders drop out, so it is run by hand when the data needs a refresh.
Re-running it rewrites nothing unless the content actually changed, so it never
produces an empty commit:

```
pip install requests selectolax
python scripts/fetch_riders.py                     # every registered tour
python scripts/fetch_riders.py tdf2026 giro2026     # specific tours
```

## Why letour.fr and not procyclingstats.com

The site originally scraped procyclingstats.com via the `procyclingstats`
Python package. That site sits behind Cloudflare bot protection, which
blocks plain scraper traffic — and blocks it *harder* from GitHub Actions'
datacenter IPs than from a home network, to the point where even
`cloudscraper` (a Cloudflare-bypass library) couldn't reliably get through.
letour.fr, the official race site, serves its rankings as plain
server-rendered HTML with no such protection, so `fetch_results.py` scrapes
it directly with `requests` + `selectolax` instead.

Each classification is fetched and parsed independently, so a change to
letour.fr's HTML that breaks one table (e.g. mountains) doesn't take down
the others — check the Actions log for warnings if a table stops updating.

## License & disclaimer

The **source code** of this project (`index.html`, `scripts/`, and the
GitHub Actions workflow) is released under the [MIT License](LICENSE) — feel
free to use, modify, and share it.

The **results data**, however, is a different matter and the MIT license does
**not** extend to it:

- This is an unofficial, non-commercial fan project. It is **not affiliated
  with, endorsed by, or connected to** Amaury Sport Organisation (A.S.O.),
  letour.fr, or the Tour de France.
- Race results shown here are fetched from **letour.fr** and remain the
  property of their respective owners. No ownership of, or rights to, that
  data are claimed or granted by this project.
- "Tour de France" and related names and logos are trademarks of A.S.O. and
  are used here only descriptively to identify the event.

If you reuse this code, you are responsible for sourcing your own data and
complying with the terms of whatever source you use.
