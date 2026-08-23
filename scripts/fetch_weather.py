#!/usr/bin/env python3
"""
Grand tour weather fetch — actual race-day weather, stage by stage.

Fetches the real recorded weather (not a forecast) at each stage's start and
finish location, for stages that have already been raced, and writes it to
data/<tour>-weather.json, which the tour's page reads automatically.

Only stages whose race day has fully passed (in the race's own time zone)
are fetched — Open-Meteo's historical archive rejects future dates outright,
but a same-day request for a stage still being raced would succeed with
data for an incomplete day, so "ended" is decided locally rather than left
to the API. Already-fetched stages are skipped on later runs (a past day's
weather does not change), so this script only ever does a little work per
run — the same "poll on a schedule, commit if changed" shape as
fetch_results.py.

Usage:
    python scripts/fetch_weather.py               # fetch every registered tour
    python scripts/fetch_weather.py vuelta2026     # fetch specific tour(s)
Dependencies:  pip install requests

Data source: Open-Meteo's free historical weather archive
(archive-api.open-meteo.com), no API key required. Daily aggregates
(high/low temperature, max wind, rainfall, mean humidity) at the stage's
start and finish coordinates, taken from the first/last point of
data/<tour>-routes.json.
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

# Each stage's date and start/finish town names, mirrored from the `stages`
# array in the tour's own HTML page (the schedule is fixed months ahead of
# the race, so this only needs updating if the route changes). "summit"
# marks a summit finish, so the page can show finish altitude for it.
# Coordinates are NOT duplicated here — they come from data/<tour>-routes.json
# (first/last point of each stage's polyline).
VUELTA_STAGES = [
    {"n": 1,  "date": "2026-08-22", "start": "Monaco",                  "finish": "Monaco"},
    {"n": 2,  "date": "2026-08-23", "start": "Monaco",                  "finish": "Manosque"},
    {"n": 3,  "date": "2026-08-24", "start": "Gruissan",                "finish": "Font-Romeu",            "summit": True},
    {"n": 4,  "date": "2026-08-25", "start": "Andorra la Vella",        "finish": "Andorra la Vella"},
    {"n": 5,  "date": "2026-08-26", "start": "Falset",                  "finish": "Roquetes"},
    {"n": 6,  "date": "2026-08-27", "start": "Alcossebre",              "finish": "Castellón"},
    {"n": 7,  "date": "2026-08-28", "start": "Vall d'Alba",             "finish": "Aramón Valdelinares",   "summit": True},
    {"n": 8,  "date": "2026-08-29", "start": "Puçol",                   "finish": "Xeraco"},
    {"n": 9,  "date": "2026-08-30", "start": "La Vila Joiosa",          "finish": "Alto de Aitana",        "summit": True},
    {"n": 10, "date": "2026-09-01", "start": "Alcaraz",                 "finish": "Elche de la Sierra"},
    {"n": 11, "date": "2026-09-02", "start": "Cartagena",               "finish": "Lorca"},
    {"n": 12, "date": "2026-09-03", "start": "Vera",                    "finish": "Calar Alto",            "summit": True},
    {"n": 13, "date": "2026-09-04", "start": "Almuñécar",               "finish": "Loja"},
    {"n": 14, "date": "2026-09-05", "start": "Jaén",                    "finish": "Sierra de la Pandera",  "summit": True},
    {"n": 15, "date": "2026-09-06", "start": "Palma del Río",           "finish": "Córdoba"},
    {"n": 16, "date": "2026-09-08", "start": "Cortegana",               "finish": "La Rábida"},
    {"n": 17, "date": "2026-09-09", "start": "Dos Hermanas",            "finish": "Sevilla"},
    {"n": 18, "date": "2026-09-10", "start": "El Puerto de Santa María","finish": "Jerez de la Frontera"},
    {"n": 19, "date": "2026-09-11", "start": "Vélez-Málaga",            "finish": "Peñas Blancas",         "summit": True},
    {"n": 20, "date": "2026-09-12", "start": "La Calahorra",            "finish": "Collada de Alguacil",   "summit": True},
    {"n": 21, "date": "2026-09-13", "start": "Granada",                 "finish": "Granada"},
]

# Mirrored from the `stages` array in tdf2026.html (rest days, n:'lepo', are
# left out — they carry no start/finish weather). "summit" marks the same
# mountain-top finishes the illustrative placeholder data used to give a
# finish altitude (Les Angles, Gavarnie-Gèdre, Le Lioran, Le Markstein,
# Plateau de Solaison, Orcières-Merlette, both Alpe d'Huez finishes).
TDF_STAGES = [
    {"n": 1,  "date": "2026-07-04", "start": "Barcelona",      "finish": "Barcelona"},
    {"n": 2,  "date": "2026-07-05", "start": "Tarragona",      "finish": "Barcelona"},
    {"n": 3,  "date": "2026-07-06", "start": "Granollers",     "finish": "Les Angles",           "summit": True},
    {"n": 4,  "date": "2026-07-07", "start": "Carcassonne",    "finish": "Foix"},
    {"n": 5,  "date": "2026-07-08", "start": "Lannemezan",     "finish": "Pau"},
    {"n": 6,  "date": "2026-07-09", "start": "Pau",            "finish": "Gavarnie-Gèdre",        "summit": True},
    {"n": 7,  "date": "2026-07-10", "start": "Hagetmau",       "finish": "Bordeaux"},
    {"n": 8,  "date": "2026-07-11", "start": "Périgueux",      "finish": "Bergerac"},
    {"n": 9,  "date": "2026-07-12", "start": "Malemort",       "finish": "Ussel"},
    {"n": 10, "date": "2026-07-14", "start": "Aurillac",       "finish": "Le Lioran",             "summit": True},
    {"n": 11, "date": "2026-07-15", "start": "Vichy",          "finish": "Nevers"},
    {"n": 12, "date": "2026-07-16", "start": "Magny-Cours",    "finish": "Chalon-sur-Saône"},
    {"n": 13, "date": "2026-07-17", "start": "Dole",           "finish": "Belfort"},
    {"n": 14, "date": "2026-07-18", "start": "Mulhouse",       "finish": "Le Markstein",          "summit": True},
    {"n": 15, "date": "2026-07-19", "start": "Champagnole",    "finish": "Plateau de Solaison",   "summit": True},
    {"n": 16, "date": "2026-07-21", "start": "Evian-les-Bains","finish": "Thonon-les-Bains"},
    {"n": 17, "date": "2026-07-22", "start": "Chambéry",       "finish": "Voiron"},
    {"n": 18, "date": "2026-07-23", "start": "Voiron",         "finish": "Orcières-Merlette",     "summit": True},
    {"n": 19, "date": "2026-07-24", "start": "Gap",            "finish": "Alpe d’Huez",           "summit": True},
    {"n": 20, "date": "2026-07-25", "start": "Bourg d’Oisans", "finish": "Alpe d’Huez",           "summit": True},
    {"n": 21, "date": "2026-07-26", "start": "Thoiry",         "finish": "Paris"},
]

# data/tdf2026-routes.json has no GPX-derived points for stages 3, 4 and 5
# (route data wasn't available for those when the file was built — see
# tdf2026.html's own STAGE_COORDS, which exists for exactly the same reason,
# as a straight-line fallback for its route map). Mirrored here, in
# [lon, lat] as in that table, and converted to [lat, lon] in point_for.
TDF_COORDS_FALLBACK = {
    3: [[2.29, 41.61], [2.07, 42.57]],
    4: [[2.35, 43.21], [1.61, 42.96]],
    5: [[0.38, 43.13], [-0.37, 43.30]],
}

TOURS = {
    "tdf2026": {
        "stages": TDF_STAGES,
        "routes": "tdf2026-routes.json",
        "out": "tdf2026-weather.json",
        "tz": "Europe/Paris",
        "coords_fallback": TDF_COORDS_FALLBACK,
    },
    "vuelta2026": {
        "stages": VUELTA_STAGES,
        "routes": "vuelta2026-routes.json",
        "out": "vuelta2026-weather.json",
        "tz": "Europe/Madrid",
    },
}

HEADERS = {"User-Agent": "grand-tours-weather-fetch/1.0 (+https://github.com/juusimaa/Tdf2026)"}

DAILY_FIELDS = (
    "weathercode,temperature_2m_max,temperature_2m_min,apparent_temperature_max,"
    "windspeed_10m_max,winddirection_10m_dominant,precipitation_sum,relative_humidity_2m_mean"
)

# WMO weather code -> condition slug. Slugs match the wxConds i18n table in
# each page's STRINGS object, which supplies the localized label.
WMO_COND = {
    0: "clear", 1: "sunny", 2: "partly", 3: "overcast",
    45: "mist", 48: "mist",
    51: "showers", 53: "showers", 55: "showers", 56: "showers", 57: "showers",
    61: "showers", 63: "rain", 65: "storm", 66: "rain", 67: "rain",
    71: "snow", 73: "snow", 75: "snow", 77: "snow",
    80: "showers", 81: "showers", 82: "storm",
    85: "snow", 86: "snow",
    95: "storm", 96: "storm", 99: "storm",
}

COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def compass_dir(deg):
    return COMPASS[round((deg % 360) / 45) % 8]


def load_routes(tour):
    path = DATA_DIR / TOURS[tour]["routes"]
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    return data.get("stages", {})


def fetch_daily(lat, lon, date, tz):
    resp = requests.get(
        ARCHIVE_URL,
        params={
            "latitude": lat,
            "longitude": lon,
            "start_date": date,
            "end_date": date,
            "daily": DAILY_FIELDS,
            "timezone": tz,
        },
        headers=HEADERS,
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    daily = data.get("daily") or {}
    if not daily.get("time"):
        return None
    code = daily["weathercode"][0]
    return {
        "temp": round(daily["temperature_2m_max"][0]),
        "low": round(daily["temperature_2m_min"][0]),
        "feels": round(daily["apparent_temperature_max"][0]),
        "cond": WMO_COND.get(code, "cloudy"),
        "wind": round(daily["windspeed_10m_max"][0]),
        "dir": compass_dir(daily["winddirection_10m_dominant"][0]),
        "precip": round(daily["precipitation_sum"][0], 1),
        "humidity": round(daily["relative_humidity_2m_mean"][0]),
        "alt": round(data.get("elevation")) if data.get("elevation") is not None else None,
    }


def point_for(place, routes, n, coords_fallback=None):
    """[lat, lon] for a stage's start (first route point) or finish (last)."""
    pts = routes.get(str(n))
    if pts:
        return pts[0] if place == "start" else pts[-1]
    if coords_fallback and n in coords_fallback:
        lon, lat = coords_fallback[n][0 if place == "start" else 1]
        return [lat, lon]
    return None


def fetch_tour(tour):
    cfg = TOURS[tour]
    out_path = DATA_DIR / cfg["out"]
    existing = {}
    if out_path.exists():
        try:
            existing = json.loads(out_path.read_text()).get("stages", {})
        except (json.JSONDecodeError, OSError):
            existing = {}

    routes = load_routes(tour)
    today = datetime.now(ZoneInfo(cfg["tz"])).date().isoformat()

    stages_out = dict(existing)
    changed = False
    for st in cfg["stages"]:
        key = str(st["n"])
        if st["date"] >= today:
            continue  # race day hasn't fully passed yet
        if key in existing:
            continue  # already fetched; a past day's weather won't change

        entry = {}
        for place, town in (("start", st["start"]), ("finish", st["finish"])):
            pt = point_for(place, routes, st["n"], cfg.get("coords_fallback"))
            if not pt:
                print(f"  stage {st['n']} {place}: no route point, skipping")
                continue
            try:
                vals = fetch_daily(pt[0], pt[1], st["date"], cfg["tz"])
            except requests.RequestException as e:
                print(f"  stage {st['n']} {place}: fetch failed ({e})")
                continue
            if not vals:
                print(f"  stage {st['n']} {place}: no data returned")
                continue
            vals["town"] = town
            if not st.get("summit") or place != "finish":
                vals.pop("alt", None)
            entry[place] = vals
            time.sleep(0.2)  # be polite to the free API

        if "start" in entry and "finish" in entry:
            stages_out[key] = entry
            changed = True
            print(f"  stage {st['n']} ({st['date']}): fetched")

    if not changed:
        print(f"{tour}: nothing new to fetch.")
        return

    out_path.write_text(json.dumps({
        "note": ("Actual weather recorded at the stage's start and finish "
                 "location on race day, from Open-Meteo's historical archive. "
                 "Only stages that have already been raced are included."),
        "source": "archive-api.open-meteo.com",
        "units": {"temp": "°C", "wind": "km/h", "rain": "mm", "humidity": "%"},
        "updated": datetime.now(ZoneInfo("Europe/Helsinki")).isoformat(timespec="seconds"),
        "stages": stages_out,
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{tour}: wrote {out_path.relative_to(DATA_DIR.parent)}")


def main():
    tours = sys.argv[1:] or list(TOURS)
    for tour in tours:
        if tour not in TOURS:
            print(f"Unknown tour: {tour} (registered: {', '.join(TOURS)})", file=sys.stderr)
            continue
        print(f"Fetching weather for {tour}...")
        fetch_tour(tour)


if __name__ == "__main__":
    main()
