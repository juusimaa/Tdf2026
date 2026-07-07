# Grand tour — self-updating results page

A static results page for the 2026 Tour de France that keeps itself up to
date, with no manual work required once it's deployed. The data and scripts
are **tour-aware**: results live in per-tour files (`data/<tour>-results.json`)
so the site can be extended to cover all three grand tours (Tour de France,
Giro d'Italia, Vuelta a España). Today only `tdf2026` is configured.

```
index.html                            # the page (stages + results tabs)
data/tdf2026-results.json             # auto-updated results data (per tour)
scripts/fetch_results.py              # fetch script (scrapes letour.fr)
.github/workflows/update-results.yml  # scheduled GitHub Actions workflow
```

To add another tour later, register it in the `TOURS` dict in
`scripts/fetch_results.py` (with a source handler) and point a page at its
`data/<tour>-results.json`.

## How it works

1. GitHub Actions runs the workflow on a schedule (every 30 minutes,
   14:00–20:00 UTC in July — stages typically finish in that window — plus
   a light morning run to catch late corrections).
2. The workflow runs `fetch_results.py`, which scrapes the official
   **letour.fr** rankings pages for the latest completed stage: general
   classification, points, mountains, youth, and team classifications,
   plus the winner of every stage raced so far.
3. The script writes `data/tdf2026-results.json` (one file per registered
   tour). If the content changed, the workflow commits it back to the repo.
4. GitHub Pages serves the site, and `index.html` fetches the JSON for its
   tour in the browser (`fetch('data/tdf2026-results.json')`). The page
   therefore always shows the latest committed standings with zero manual
   intervention.

The page also **auto-selects the stage of the day** when opened (the next
stage on rest days, the final stage once the race is over).

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
