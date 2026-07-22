#!/usr/bin/env python3
"""Fetch per-stage GPX route tracks for the 2026 Tour de France and write a
compact JSON the roadbook loads to draw the real route on the expanded
Leaflet map (tdf2026.html).

Source: cyclingstage.com GPX exports (public, free to download). Each track
is simplified with Ramer-Douglas-Peucker so the shipped file stays small —
the map is an overview locator, not a turn-by-turn nav, so ~50 m of
simplification is invisible at that zoom. Coordinates are stored as
[lat, lon] rounded to 5 decimals (~1 m).

Re-run after the route is finalised, or to pick up stages that were not yet
uploaded to the CDN (some 404 until the organiser publishes them):

    python3 scripts/fetch_routes.py

Missing stages are simply omitted from the JSON; the page falls back to a
straight start->finish line for those.
"""
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

STAGES = range(1, 22)
URL = "https://cdn.cyclingstage.com/images/tour-de-france/2026/stage-{n}-parcours.gpx"
REFERER = "https://www.cyclingstage.com/tour-de-france-2026-gpx/"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36")

OUT = Path(__file__).resolve().parent.parent / "data" / "tdf2026-routes.json"

# RDP tolerance in degrees (~0.0006 deg ≈ 60 m). Larger => fewer points.
EPSILON = 0.0006

TRKPT = re.compile(r'<trkpt[^>]*\blat="([-\d.]+)"[^>]*\blon="([-\d.]+)"')


def fetch(n):
    req = urllib.request.Request(URL.format(n=n),
                                 headers={"User-Agent": UA, "Referer": REFERER})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            if r.status != 200:
                return None
            return r.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001 - report and skip
        print(f"  stage {n}: fetch failed ({e})", file=sys.stderr)
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


def main():
    stages = {}
    for n in STAGES:
        gpx = fetch(n)
        if not gpx:
            print(f"stage {n:2d}: no data (skipped)")
            continue
        pts = parse(gpx)
        if len(pts) < 10:
            print(f"stage {n:2d}: too few points ({len(pts)}), skipped")
            continue
        simp = rdp(pts, EPSILON)
        stages[str(n)] = [[round(la, 5), round(lo, 5)] for la, lo in simp]
        print(f"stage {n:2d}: {len(pts):5d} -> {len(simp):4d} points")

    payload = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "cyclingstage.com GPX (simplified, RDP eps=%.4f deg)" % EPSILON,
        "stages": stages,
    }
    OUT.write_text(json.dumps(payload, separators=(",", ":")) + "\n")
    kb = OUT.stat().st_size / 1024
    print(f"\nwrote {OUT.relative_to(OUT.parent.parent)} "
          f"({len(stages)}/{len(list(STAGES))} stages, {kb:.1f} KB)")


if __name__ == "__main__":
    main()
