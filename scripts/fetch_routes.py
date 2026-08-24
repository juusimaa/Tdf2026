#!/usr/bin/env python3
"""Fetch per-stage GPX route tracks for the 2026 grand tours and write a
compact JSON the roadbook loads to draw the real route on the expanded
Leaflet map (tdf2026.html / giro2026.html / vuelta2026.html).

Two sources are supported per race:
  - cyclingstage: cyclingstage.com GPX exports (public, free to download).
  - komoot: the organiser's official komoot account tour list + per-tour
    coordinates endpoint (public, no auth) — this is the actual GPS-recorded
    course rather than a third-party GPX reconstruction, so it's preferred
    where the organiser publishes one (e.g. La Vuelta's "lavuelta" account).

Each track is simplified with Ramer-Douglas-Peucker so the shipped file
stays small — the map is an overview locator, not a turn-by-turn nav, so
~50 m of simplification is invisible at that zoom. Coordinates are stored
as [lat, lon] rounded to 5 decimals (~1 m).

Usage — one race, or all of them:

    python3 scripts/fetch_routes.py            # default: tdf2026
    python3 scripts/fetch_routes.py giro2026
    python3 scripts/fetch_routes.py all

Re-run after a route is finalised, or to pick up stages that were not yet
uploaded/published. Missing stages are simply omitted from the JSON; the
page falls back to a straight start->finish line for those.
"""
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Per-race source. cyclingstage.com uses a slightly different filename per
# race (…-parcours.gpx for the Tour, …-route.gpx for the Giro).
RACES = {
    "tdf2026": {
        "source": "cyclingstage",
        "url": "https://cdn.cyclingstage.com/images/tour-de-france/2026/stage-{n}-parcours.gpx",
        "referer": "https://www.cyclingstage.com/tour-de-france-2026-gpx/",
    },
    "giro2026": {
        "source": "cyclingstage",
        "url": "https://cdn.cyclingstage.com/images/giro-italy/2026/stage-{n}-route.gpx",
        "referer": "https://www.cyclingstage.com/giro-2026-gpx/",
    },
    "vuelta2026": {
        "source": "komoot",
        "komoot_user": "lavuelta",
        "komoot_edition_tag": "La Vuelta 26",
    },
    "femmes2026": {
        "source": "cyclingstage",
        "url": "https://cdn.cyclingstage.com/images/tour-de-france-femmes/2026/stage-{n}-route.gpx",
        "referer": "https://www.cyclingstage.com/tour-de-france-femmes-2026-gpx/",
        "stages": 9,
    },
}

STAGES = range(1, 22)
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# RDP tolerance in degrees (~0.0006 deg ≈ 60 m). Larger => fewer points.
# A flat 60 m tolerance is fine for the 3-6k-point transitional stages, but it
# flattens the hairpins on short/tight tracks (a Monaco circuit prologue, an
# ITT loop) that only have a few hundred raw points to begin with -- and
# keeping those dense costs almost nothing in file size. So short tracks get
# a much finer tolerance instead.
EPSILON = 0.0006
FINE_EPSILON = 0.00008
FINE_POINT_THRESHOLD = 1000


def fetch(url, referer):
    req = urllib.request.Request(url,
                                 headers={"User-Agent": UA, "Referer": referer})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            if r.status != 200:
                return None
            return r.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001 - report and skip
        print(f"  fetch failed for {url} ({e})", file=sys.stderr)
        return None


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def komoot_stage_tours(user, edition_tag):
    """Map stage number -> tour id for the account's public "Stage N: ..."
    tours (komoot's public v007 API, no auth required). Official race
    accounts re-publish older editions under the same account, so tours are
    matched on both the stage number and an edition tag (e.g. "La Vuelta 26")
    to avoid picking up a same-numbered stage from a previous year."""
    tours = {}
    limit = 100
    offset = 0
    while True:
        url = (f"https://api.komoot.de/v007/users/{user}/tours/"
               f"?limit={limit}&offset={offset}&status=public")
        data = fetch_json(url)
        items = data.get("_embedded", {}).get("tours", [])
        for t in items:
            name = t.get("name", "")
            if edition_tag not in name:
                continue
            m = re.match(r"Stage (\d+):", name)
            if m:
                tours[int(m.group(1))] = t["id"]
        offset += limit
        if offset >= data.get("page", {}).get("totalElements", 0) or not items:
            break
    return tours


def komoot_coordinates(tour_id):
    url = f"https://api.komoot.de/v007/tours/{tour_id}/coordinates"
    data = fetch_json(url)
    return [(it["lat"], it["lng"]) for it in data.get("items", [])]


def parse(gpx):
    # GPX uses lat/lon order; sometimes lon appears before lat, so try both.
    pts = []
    for m in re.finditer(r"<trkpt\b[^>]*>", gpx):
        tag = m.group(0)
        lat = re.search(r'\blat="([-\d.]+)"', tag)
        lon = re.search(r'\blon="([-\d.]+)"', tag)
        if lat and lon:
            pts.append((float(lat.group(1)), float(lon.group(1))))
    return pts


def _perp(p, a, b):
    """Perpendicular distance of p from segment a-b (in degree space)."""
    (py, px), (ay, ax), (by, bx) = p, a, b
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t * dx, ay + t * dy
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5


def rdp(points, eps):
    """Iterative Ramer-Douglas-Peucker (avoids recursion limits on big tracks)."""
    if len(points) < 3:
        return points[:]
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        lo, hi = stack.pop()
        dmax, idx = 0.0, -1
        a, b = points[lo], points[hi]
        for i in range(lo + 1, hi):
            d = _perp(points[i], a, b)
            if d > dmax:
                dmax, idx = d, i
        if dmax > eps and idx != -1:
            keep[idx] = True
            stack.append((lo, idx))
            stack.append((idx, hi))
    return [p for p, k in zip(points, keep) if k]


def _write_payload(race, stages, ends, total, source_text):
    payload = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": source_text,
        "stages": stages,
    }
    out = DATA_DIR / f"{race}-routes.json"
    out.write_text(json.dumps(payload, separators=(",", ":")) + "\n")
    kb = out.stat().st_size / 1024
    print(f"wrote {out.relative_to(out.parent.parent)} "
          f"({len(stages)}/{total} stages, {kb:.1f} KB)")
    # Convenience dump: STAGE_COORDS literal for the page's collapsed minimap
    # (derived from the track endpoints so no town coords are hand-entered).
    literal = ", ".join(f"{n}:{v}" for n, v in ends.items()).replace(" ", "")
    print(f"STAGE_COORDS = {{{literal}}}\n")


def _add_stage(stages, ends, n, pts):
    eps = FINE_EPSILON if len(pts) < FINE_POINT_THRESHOLD else EPSILON
    simp = rdp(pts, eps)
    stages[str(n)] = [[round(la, 5), round(lo, 5)] for la, lo in simp]
    # Start/finish as [lon, lat] (the page's minimap convention), 3 dp.
    ends[str(n)] = [[round(pts[0][1], 3), round(pts[0][0], 3)],
                    [round(pts[-1][1], 3), round(pts[-1][0], 3)]]
    print(f"stage {n:2d}: {len(pts):5d} -> {len(simp):4d} points")


def build_race_cyclingstage(race, cfg):
    print(f"== {race} (cyclingstage.com) ==")
    stages, ends = {}, {}
    stage_range = range(1, cfg.get("stages", 21) + 1)
    for n in stage_range:
        gpx = fetch(cfg["url"].format(n=n), cfg["referer"])
        if not gpx:
            print(f"stage {n:2d}: no data (skipped)")
            continue
        pts = parse(gpx)
        if len(pts) < 10:
            print(f"stage {n:2d}: too few points ({len(pts)}), skipped")
            continue
        _add_stage(stages, ends, n, pts)
    source_text = "cyclingstage.com GPX (simplified, RDP eps=%.4f deg)" % EPSILON
    _write_payload(race, stages, ends, len(list(stage_range)), source_text)


def build_race_komoot(race, cfg):
    user = cfg["komoot_user"]
    print(f"== {race} (komoot.com/user/{user}) ==")
    stages, ends = {}, {}
    tour_map = komoot_stage_tours(user, cfg["komoot_edition_tag"])
    for n in sorted(tour_map):
        try:
            pts = komoot_coordinates(tour_map[n])
        except Exception as e:  # noqa: BLE001 - report and skip
            print(f"stage {n:2d}: fetch failed ({e})", file=sys.stderr)
            continue
        if len(pts) < 10:
            print(f"stage {n:2d}: too few points ({len(pts)}), skipped")
            continue
        _add_stage(stages, ends, n, pts)
    source_text = (f"komoot.com/user/{user} (official route, simplified, "
                    f"RDP eps=%.4f deg)" % EPSILON)
    _write_payload(race, stages, ends, len(tour_map), source_text)


def build_race(race):
    cfg = RACES[race]
    if cfg.get("source") == "komoot":
        build_race_komoot(race, cfg)
    else:
        build_race_cyclingstage(race, cfg)


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else "tdf2026"
    races = list(RACES) if arg == "all" else [arg]
    for race in races:
        if race not in RACES:
            sys.exit(f"unknown race '{race}'; choose from: {', '.join(RACES)}, all")
        build_race(race)


if __name__ == "__main__":
    main()
