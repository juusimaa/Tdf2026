#!/usr/bin/env python3
"""
Tour de France 2026 — tulosten automaattihaku.

Hakee letour.fr:n (virallinen kisasivusto) tulossivuilta viimeisimmän
ajetun etapin jälkeiset tilanteet kaikissa kategorioissa ja kirjoittaa ne
tiedostoon data/results.json, jonka index.html lukee automaattisesti.

Käyttö:  python scripts/fetch_results.py
Riippuvuudet:  pip install requests selectolax

Huom: käytimme aiemmin procyclingstats-pakettia, mutta procyclingstats.com
on Cloudflaren bottisuojauksen takana eikä GitHub Actionsin ajoympäristöstä
pääse sinne läpi edes cloudscraperilla. letour.fr ei ole samanlaisen
suojauksen takana ja tarjoaa tulostaulukot suoraan HTML:nä, joten
scrapataan sieltä.
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from selectolax.parser import HTMLParser

BASE = "https://www.letour.fr"
OUT = Path(__file__).resolve().parent.parent / "data" / "results.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# RESULTS-avain -> (letour-luokan koodi, arvon tyyppi, onko rivi joukkue eikä ajaja)
CLASS_CONFIG = {
    "gc":        {"code": "itg", "kind": "time",   "team_only": False},
    "points":    {"code": "ipg", "kind": "points", "team_only": False},
    "mountains": {"code": "img", "kind": "points", "team_only": False},
    "youth":     {"code": "ijg", "kind": "time",   "team_only": False},
    "teams":     {"code": "etg", "kind": "time",   "team_only": True},
}

session = requests.Session()
session.headers.update(HEADERS)


def fetch(url: str) -> str:
    resp = session.get(url, timeout=20)
    resp.raise_for_status()
    return resp.text


def ajax_stacks(html: str):
    """
    letour.fr upottaa sivun HTML:ään data-ajax-stack-attribuutteja, jotka
    sisältävät JSON-sanakirjan { luokkakoodi: ajax-url }. Sivulla on
    tyypillisesti kaksi: yksi yleisluokituksille (itg/ipg/img/ijg/etg) ja
    yksi etappiluokitukselle (esim. ete/ite).
    """
    stacks = []
    for m in re.finditer(r"data-ajax-stack\s*=\s*(\{.*?\})", html):
        raw = m.group(1).replace("&quot;", '"').replace("\\/", "/")
        try:
            stacks.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return stacks


def parse_table(html: str, team_only: bool, kind: str):
    """Muuntaa letour.fr:n rankingTables-HTML-fragmentin front-endin rivimuotoon."""
    tree = HTMLParser(html)
    rows = []
    for tr in tree.css("tbody tr.rankingTables__row"):
        tds = tr.css("td")
        if not tds:
            continue
        pos_text = tds[0].text(strip=True)
        pos = int(pos_text) if pos_text.isdigit() else None

        if team_only:
            rider = tds[1].text(strip=True)
            team, nat = "", ""
            val_idx = 2
        else:
            img = tr.css_first(".rankingTables__row__profile.runner img")
            rider = (img.attributes.get("alt") or "").strip() if img else tds[1].text(strip=True)
            team = tds[3].text(strip=True) if len(tds) > 3 else ""
            flag = tr.css_first("[data-class]")
            nat = (flag.attributes.get("data-class") or "").replace("flag--", "").upper() if flag else ""
            val_idx = 4

        if len(tds) <= val_idx:
            continue

        row = {"pos": pos, "rider": rider, "team": team, "nat": nat, "val": tds[val_idx].text(strip=True)}

        if kind == "time" and pos and pos > 1 and len(tds) > val_idx + 1:
            gap = tds[val_idx + 1].text(strip=True)
            if gap and gap != "-":
                row["gap"] = gap

        rows.append(row)
    return rows


def stage_winner(stage_no: int) -> str:
    """Hakee etapin voittajan (ajaja, tai joukkueaika-ajossa joukkue)."""
    html = fetch(f"{BASE}/en/rankings/stage-{stage_no}")
    stacks = ajax_stacks(html)
    if len(stacks) < 2:
        return ""
    stage_dict = stacks[1]
    if not stage_dict:
        return ""
    _, url = next(iter(stage_dict.items()))
    table_html = fetch(BASE + url)
    tree = HTMLParser(table_html)
    tr = tree.css_first("tbody tr.rankingTables__row")
    if tr is None:
        return ""
    img = tr.css_first(".rankingTables__row__profile.runner img")
    if img and img.attributes.get("alt"):
        return img.attributes["alt"].strip()
    tds = tr.css("td")
    return tds[1].text(strip=True) if len(tds) > 1 else ""


def main() -> int:
    try:
        main_html = fetch(f"{BASE}/en/rankings")
    except Exception as e:
        print(f"Tilanteen haku epäonnistui: {e}")
        return 0

    stacks = ajax_stacks(main_html)
    if not stacks or "itg" not in stacks[0]:
        print("Kisa ei ole vielä alkanut, tai tuloksia ei ole vielä julkaistu.")
        return 0

    general = stacks[0]
    stage_no = int(general["itg"].split("/")[4])
    print(f"Uusimmat tulokset: etappi {stage_no}")

    data = {
        "updated": datetime.now(ZoneInfo("Europe/Helsinki")).isoformat(),
        "updatedText": datetime.now(ZoneInfo("Europe/Helsinki")).strftime(
            "Päivitetty %d.%m.%Y klo %H.%M (Suomen aikaa)"
        ),
        "afterStage": stage_no,
        "stageWinners": [],
    }

    for key, cfg in CLASS_CONFIG.items():
        url = general.get(cfg["code"])
        rows = []
        if url:
            try:
                table_html = fetch(BASE + url)
                rows = parse_table(table_html, cfg["team_only"], cfg["kind"])
            except Exception as e:
                print(f"  varoitus: {key} haku epäonnistui: {e}")
        data[key] = {"rows": rows}

    # Aiemmin löydetyt etappivoittajat kelpaavat sellaisenaan; haetaan vain
    # ne joita ei vielä tiedetä, jotta jokaisella ajolla ei tehdä turhia
    # pyyntöjä kaikille jo ajetuille etapeille.
    previous_winners = {}
    if OUT.exists():
        try:
            prev = json.loads(OUT.read_text(encoding="utf-8"))
            for w in prev.get("stageWinners", []):
                if w.get("winner"):
                    previous_winners[w["n"]] = w["winner"]
        except Exception:
            pass

    for n in range(1, stage_no + 1):
        winner = previous_winners.get(n, "")
        if not winner:
            try:
                winner = stage_winner(n)
            except Exception as e:
                print(f"  etappi {n} voittaja: {e}")
                winner = ""
        data["stageWinners"].append({"n": n, "winner": winner})

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Kirjoitettu {OUT} (GC-rivejä: {len(data['gc']['rows'])})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
