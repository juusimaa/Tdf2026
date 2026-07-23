#!/usr/bin/env python3
"""Fetch per-stage GPX route tracks for the 2026 grand tours and write a
compact JSON the roadbook loads to draw the real route on the expanded
Leaflet map (tdf2026.html / giro2026.html).

Source: cyclingstage.com GPX exports (public, free to download). Each track
is simplified with Ramer-Douglas-Peucker so the shipped file stays small —
the map is an overview locator, not a turn-by-turn nav, so ~50 m of
simplification is invisible at that zoom. Coordinates are stored as
[lat, lon] rounded to 5 decimals (~1 m).

Usage — one race, or all of them:

    python3 scripts/fetch_routes.py            # default: tdf2026
    python3 scripts/fetch_routes.py giro2026
    python3 scripts/fetch_routes.py all

Re-run after a route is finalised, or to pick up stages that were not yet
uploaded to the CDN (some 404 until the organiser publishes them). Missing
stages are simply omitted from the JSON; the page falls back to a straight
start->finish line for those.
"""
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Per-race GPX source. cyclingstage.com uses a slightly different filename per
# race (…-parcours.gpx for the Tour, …-route.gpx for the Giro).
RACES = {
    "tdf2026": {
        "url": "https://cdn.cyclingstage.com/images/tour-de-france/2026/stage-{n}-parcours.gpx",
        "referer": "https://www.cyclingstage.com/tour-de-france-2026-gpx/",
    },
    "giro2026": {
        "url": "https://cdn.cyclingstage.com/images/giro-italy/2026/stage-{n}-route.gpx",
        "referer": "https://www.cyclingstage.com/giro-2026-gpx/",
    },
    "vuelta2026": {
        "url": "https://cdn.cyclingstage.com/images/vuelta-spain/2026/stage-{n}-route.gpx",
        "referer": "https://www.cyclingstage.com/vuelta-2026-gpx/",
    },
}

STAGES = range(1, 22)
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# RDP tolerance in degrees (~0.0006 deg ≈ 60 m). Larger => fewer points.
EPSILON = 0.0006


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


def build_race(race):
    cfg = RACES[race]
    print(f"== {race} ==")
    stages = {}
    ends = {}
    for n in STAGES:
        gpx = fetch(cfg["url"].format(n=n), cfg["referer"])
        if not gpx:
            print(f"stage {n:2d}: no data (skipped)")
            continue
        pts = parse(gpx)
        if len(pts) < 10:
            print(f"stage {n:2d}: too few points ({len(pts)}), skipped")
            continue
        simp = rdp(pts, EPSILON)
        stages[str(n)] = [[round(la, 5), round(lo, 5)] for la, lo in simp]
        # Start/finish as [lon, lat] (the page's minimap convention), 3 dp.
        ends[str(n)] = [[round(pts[0][1], 3), round(pts[0][0], 3)],
                        [round(pts[-1][1], 3), round(pts[-1][0], 3)]]
        print(f"stage {n:2d}: {len(pts):5d} -> {len(simp):4d} points")

    payload = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "cyclingstage.com GPX (simplified, RDP eps=%.4f deg)" % EPSILON,
        "stages": stages,
    }
    out = DATA_DIR / f"{race}-routes.json"
    out.write_text(json.dumps(payload, separators=(",", ":")) + "\n")
    kb = out.stat().st_size / 1024
    print(f"wrote {out.relative_to(out.parent.parent)} "
          f"({len(stages)}/{len(list(STAGES))} stages, {kb:.1f} KB)")
    # Convenience dump: STAGE_COORDS literal for the page's collapsed minimap
    # (derived from the GPX endpoints so no town coords are hand-entered).
    literal = ", ".join(f"{n}:{v}" for n, v in ends.items()).replace(" ", "")
    print(f"STAGE_COORDS = {{{literal}}}\n")


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else "tdf2026"
    races = list(RACES) if arg == "all" else [arg]
    for race in races:
        if race not in RACES:
            sys.exit(f"unknown race '{race}'; choose from: {', '.join(RACES)}, all")
        build_race(race)


if __name__ == "__main__":
    main()
