#!/usr/bin/env python3
"""
Tour de France 2026 — automatic results fetch.

Fetches the standings in all categories after the most recently raced
stage from letour.fr (the official race site) and writes them to
data/results.json, which index.html reads automatically.

Usage:  python scripts/fetch_results.py
Dependencies:  pip install requests selectolax

Note: we previously used the procyclingstats package, but procyclingstats.com
is behind Cloudflare bot protection and cannot be reached from the GitHub
Actions runner even with cloudscraper. letour.fr is not behind the same
protection and serves the result tables directly as HTML, so we scrape it.
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

# RESULTS key -> (letour class code, value type, whether the row is a team not a rider)
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
    letour.fr embeds data-ajax-stack attributes in the page HTML, each
    containing a JSON dict { class_code: ajax_url }. A page typically has
    two: one for the general classifications (itg/ipg/img/ijg/etg) and one
    for the stage classification (e.g. ete/ite).
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
    """Converts a letour.fr rankingTables HTML fragment into front-end row form."""
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


def stage_table_rows(stage_no: int):
    """
    Fetches a stage's own result table (finishing order with times).
    Same ajax-stack mechanics as the general classifications, but stacks[1]
    holds the stage-specific classification (ete/ite) URL.
    """
    html = fetch(f"{BASE}/en/rankings/stage-{stage_no}")
    stacks = ajax_stacks(html)
    if len(stacks) < 2 or not stacks[1]:
        return []
    stage_dict = stacks[1]

    # 'ite' = individual stage result (normal stage). If it is empty — as in
    # a team time trial (TTT) — use 'ete' = the teams' stage result. Any other
    # codes are tried last as a fallback.
    attempts = []
    if "ite" in stage_dict:
        attempts.append(("ite", False))
    if "ete" in stage_dict:
        attempts.append(("ete", True))
    for code in stage_dict:
        if code not in ("ite", "ete"):
            attempts.append((code, False))

    for code, team_only in attempts:
        url = stage_dict.get(code)
        if not url:
            continue
        try:
            table_html = fetch(BASE + url)
        except Exception:
            continue
        rows = parse_table(table_html, team_only=team_only, kind="time")
        if rows:
            return rows
    return []


def stage_winner(stage_no: int) -> str:
    """Fetches the stage winner (rider, or team in a team time trial)."""
    rows = stage_table_rows(stage_no)
    return rows[0]["rider"] if rows else ""


def main() -> int:
    try:
        main_html = fetch(f"{BASE}/en/rankings")
    except Exception as e:
        print(f"Failed to fetch standings: {e}")
        return 0

    stacks = ajax_stacks(main_html)
    if not stacks or "itg" not in stacks[0]:
        print("The race has not started yet, or no results have been published yet.")
        return 0

    general = stacks[0]
    stage_no = int(general["itg"].split("/")[4])
    print(f"Latest results: stage {stage_no}")

    prev = {}
    if OUT.exists():
        try:
            prev = json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:
            pass

    data = {"afterStage": stage_no, "stageWinners": []}

    for key, cfg in CLASS_CONFIG.items():
        url = general.get(cfg["code"])
        rows = []
        if url:
            try:
                table_html = fetch(BASE + url)
                rows = parse_table(table_html, cfg["team_only"], cfg["kind"])
            except Exception as e:
                print(f"  warning: fetching {key} failed: {e}")
        data[key] = {"rows": rows}

    # letour.fr flips the "latest stage" pointer on /en/rankings already when
    # a stage starts, before that stage's result tables are published — so
    # stage_no would increase while the tables are still empty. If the GC
    # table (always the first to be finalized) has no rows, that stage's
    # results are not out yet: keep the previous known-good data untouched
    # and try again on the next run.
    if not data["gc"]["rows"]:
        print(f"Results for stage {stage_no} are not published yet — not updating.")
        return 0

    # Previously fetched stage results and winners are reused as-is; only the
    # unknown ones are fetched, so we don't make pointless requests for all
    # already-raced stages on every run.
    previous_winners = {
        w["n"]: w["winner"] for w in prev.get("stageWinners", []) if w.get("winner")
    }
    prev_stage_results = prev.get("stageResults", {}) or {}
    data["stageResults"] = {}

    for n in range(1, stage_no + 1):
        key = str(n)
        winner = previous_winners.get(n, "")
        rows = (prev_stage_results.get(key) or {}).get("rows") or []
        if not rows:
            try:
                rows = stage_table_rows(n)
            except Exception as e:
                print(f"  stage {n} results: {e}")
                rows = []
        if rows:
            data["stageResults"][key] = {"rows": rows}
            if not winner:
                winner = rows[0].get("rider", "")
        data["stageWinners"].append({"n": n, "winner": winner})

    # "updated"/"updatedText" are refreshed only when some other field
    # actually changed — otherwise the workflow's "commit if changed" check
    # would commit on every run just because of the timestamp.
    prev_content = {k: v for k, v in prev.items() if k not in ("updated", "updatedText")}
    if prev_content == data and prev.get("updated"):
        data["updated"] = prev["updated"]
        data["updatedText"] = prev["updatedText"]
    else:
        data["updated"] = datetime.now(ZoneInfo("Europe/Helsinki")).isoformat()
        data["updatedText"] = datetime.now(ZoneInfo("Europe/Helsinki")).strftime(
            "Päivitetty %d.%m.%Y klo %H.%M (Suomen aikaa)"
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Wrote {OUT} (GC rows: {len(data['gc']['rows'])})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
