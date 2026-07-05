#!/usr/bin/env python3
"""
Tour de France 2026 — tulosten automaattihaku.

Hakee procyclingstats.com-sivustolta viimeisimmän ajetun etapin jälkeiset
tilanteet kaikissa kategorioissa ja kirjoittaa ne tiedostoon
data/results.json, jonka index.html lukee automaattisesti.

Käyttö:  python scripts/fetch_results.py
Riippuvuus:  pip install procyclingstats

Huom: procyclingstats on epävirallinen scraper-paketti (PCS:llä ei ole
virallista APIa). Jos PCS muuttaa sivurakennettaan, päivitä paketti:
pip install procyclingstats --upgrade
"""

import json
import sys
from datetime import datetime, date
from pathlib import Path
from zoneinfo import ZoneInfo

from procyclingstats import Stage

RACE = "race/tour-de-france/2026"
OUT = Path(__file__).resolve().parent.parent / "data" / "results.json"

# Etappien päivämäärät (etappi -> pvm). Lepopäivät 13.7. ja 20.7.
STAGE_DATES = {
    1: date(2026, 7, 4),  2: date(2026, 7, 5),  3: date(2026, 7, 6),
    4: date(2026, 7, 7),  5: date(2026, 7, 8),  6: date(2026, 7, 9),
    7: date(2026, 7, 10), 8: date(2026, 7, 11), 9: date(2026, 7, 12),
    10: date(2026, 7, 14), 11: date(2026, 7, 15), 12: date(2026, 7, 16),
    13: date(2026, 7, 17), 14: date(2026, 7, 18), 15: date(2026, 7, 19),
    16: date(2026, 7, 21), 17: date(2026, 7, 22), 18: date(2026, 7, 23),
    19: date(2026, 7, 24), 20: date(2026, 7, 25), 21: date(2026, 7, 26),
}


def latest_possible_stage(today: date) -> int:
    """Suurin etappinumero, joka on päivämäärän puolesta voitu ajaa."""
    done = [n for n, d in STAGE_DATES.items() if d <= today]
    return max(done) if done else 0


def rows_from(table, value_field, is_time=False):
    """Muunna PCS-taulukko front-endin rivimuotoon."""
    rows = []
    for r in table:
        row = {
            "pos": r.get("rank"),
            "rider": r.get("rider_name") or r.get("team_name") or "",
            "team": r.get("team_name", "") if "rider_name" in r else "",
            "nat": (r.get("nationality") or "").upper(),
        }
        val = r.get(value_field)
        if val is None:
            val = ""
        if is_time:
            # Johtajalla kokonaisaika, muilla PCS näyttää eron — käytetään
            # arvoa sellaisenaan molemmissa kentissä.
            row["val"] = str(val)
            if row["pos"] and row["pos"] > 1:
                row["gap"] = str(val) if str(val).startswith("+") else "+" + str(val)
        else:
            row["val"] = f"{val} p."
        rows.append(row)
    return rows


def main() -> int:
    today = datetime.now(ZoneInfo("Europe/Helsinki")).date()
    candidate = latest_possible_stage(today)
    if candidate == 0:
        print("Kisa ei ole vielä alkanut — ei päivitettävää.")
        return 0

    # Etsi uusin etappi, jolta tulokset ovat jo saatavilla.
    stage = None
    stage_no = 0
    for n in range(candidate, 0, -1):
        try:
            s = Stage(f"{RACE}/stage-{n}")
            if s.results():
                stage, stage_no = s, n
                break
        except Exception as e:
            print(f"Etappi {n}: ei tuloksia vielä ({e})")
    if stage is None:
        print("Yhdeltäkään etapilta ei löytynyt tuloksia vielä.")
        return 0

    print(f"Uusimmat tulokset: etappi {stage_no}")

    def safe(fn, *a, **kw):
        try:
            return fn(*a, **kw) or []
        except Exception as e:
            print(f"  varoitus: {fn.__name__} epäonnistui: {e}")
            return []

    data = {
        "updated": datetime.now(ZoneInfo("Europe/Helsinki")).isoformat(),
        "updatedText": datetime.now(ZoneInfo("Europe/Helsinki")).strftime(
            "Päivitetty %d.%m.%Y klo %H.%M (Suomen aikaa)"
        ),
        "afterStage": stage_no,
        "gc": {"rows": rows_from(safe(stage.gc), "time", is_time=True)},
        "points": {"rows": rows_from(safe(stage.points), "points")},
        "mountains": {"rows": rows_from(safe(stage.kom), "points")},
        "youth": {"rows": rows_from(safe(stage.youth), "time", is_time=True)},
        "teams": {"rows": rows_from(safe(stage.teams), "time", is_time=True)},
        "stageWinners": [],
    }

    # Etappivoittajat kaikilta ajetuilta etapeilta.
    for n in range(1, stage_no + 1):
        try:
            s = stage if n == stage_no else Stage(f"{RACE}/stage-{n}")
            res = s.results()
            if res:
                data["stageWinners"].append(
                    {"n": n, "winner": res[0].get("rider_name", "")}
                )
        except Exception as e:
            print(f"  etappi {n} voittaja: {e}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Kirjoitettu {OUT} (GC-rivejä: {len(data['gc']['rows'])})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
