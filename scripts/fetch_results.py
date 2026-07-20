#!/usr/bin/env python3
"""
Grand tour results fetch — self-updating standings.

Fetches the standings in all categories after the most recently raced
stage and writes them to data/<tour>-results.json, which index.html reads
automatically.

This scaffolding is tour-aware so the site can cover all three grand tours.
Each tour is registered in TOURS with its own source and output file. Today
only the Tour de France (tdf2026) is configured; the Giro d'Italia and Vuelta
a España will be added there with their own source handler (letour.fr only
covers the Tour de France).

Usage:
    python scripts/fetch_results.py               # fetch every registered tour
    python scripts/fetch_results.py tdf2026        # fetch specific tour(s)
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

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Registry of grand tours the site covers. Each entry names the scraper
# ("source") to use, the site base URL, and the output file under data/.
# Add giro2026 / vuelta2026 here once their source handler exists.
TOURS = {
    "tdf2026": {
        "source": "letour",
        "base": "https://www.letour.fr",
        "out": "tdf2026-results.json",
    },
}

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

# Per-stage statistics beyond the finishing order (stageResults[n] key ->
# letour per-stage class code). The finishing order itself ("rows", ite/ete)
# and the combativity award ("combative", ice) are handled separately.
# "sectioned" tables hold one sub-table per scoring point (each intermediate
# sprint / the finish for ipe, each categorized climb for ime), and are stored
# as [{label, rows}] instead of a flat row list.
STAGE_CLASS_CONFIG = {
    "points":    {"code": "ipe", "kind": "points", "team_only": False, "sectioned": True},
    "mountains": {"code": "ime", "kind": "points", "team_only": False, "sectioned": True},
    "youth":     {"code": "ije", "kind": "time",   "team_only": False, "sectioned": False},
    "teams":     {"code": "ete", "kind": "time",   "team_only": True,  "sectioned": False},
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


def parse_sections(html: str, team_only: bool, kind: str):
    """
    Splits a rankingTables fragment into its captioned sub-tables (one per
    intermediate sprint / finish, or one per climb) and parses each.
    Returns [{label, rows}, ...]; a fragment without captions becomes a
    single unlabeled section.
    """
    parts = re.split(r'<div class="rankingTables__caption">(.*?)</div>', html, flags=re.S)
    if len(parts) < 3:
        rows = parse_table(html, team_only=team_only, kind=kind)
        return [{"label": "", "rows": rows}] if rows else []
    sections = []
    for i in range(1, len(parts) - 1, 2):
        label = re.sub(r"<[^>]+>", "", parts[i]).strip()
        rows = parse_table(parts[i + 1], team_only=team_only, kind=kind)
        if rows:
            sections.append({"label": label, "rows": rows})
    return sections


# letour.fr reason text (lowercased) -> normalized code the front-end translates
WITHDRAWAL_CODES = {
    "dns": "DNS",
    "withdrawal": "DNF",
    "outside the time limit": "OTL",
}


def fetch_withdrawals(base: str):
    """
    Fetches the per-stage withdrawal lists — one page (/en/withdrawal) covers
    every stage, split into id="stage-N" sections. Returns
    {stage_no: [{bib, rider, team, reason}]}, with reason normalized to
    DNS (did not start), DNF (abandoned during the stage) or OTL (outside the
    time limit); an unrecognized reason keeps the source text.
    """
    html = fetch(f"{base}/en/withdrawal")
    parts = re.split(r'id="stage-(\d+)"', html)
    out = {}
    for i in range(1, len(parts) - 1, 2):
        rows = []
        for tr in HTMLParser(parts[i + 1]).css("tbody tr"):
            cells = [td.text(strip=True) for td in tr.css("td")]
            if len(cells) < 4 or not cells[0].isdigit():
                continue  # header row or a "No withdrawal" placeholder
            reason = WITHDRAWAL_CODES.get(cells[3].lower(), cells[3])
            rows.append({"bib": int(cells[0]), "rider": cells[1], "team": cells[2], "reason": reason})
        out[int(parts[i])] = rows
    return out


def parse_combative(html: str):
    """
    Parses the combativity award table (ice). Unlike the other rankings it has
    no value column — just rank / rider / bib / team — and holds a single row:
    the stage's most combative rider. Returns {rider, team, nat} or None.
    """
    tree = HTMLParser(html)
    tr = tree.css_first("tbody tr.rankingTables__row")
    if tr is None:
        return None
    tds = tr.css("td")
    if len(tds) < 2:
        return None
    img = tr.css_first(".rankingTables__row__profile.runner img")
    rider = (img.attributes.get("alt") or "").strip() if img else tds[1].text(strip=True)
    if not rider:
        return None
    team_td = tr.css_first("td.team")
    team = team_td.text(strip=True) if team_td else ""
    flag = tr.css_first("[data-class]")
    nat = (flag.attributes.get("data-class") or "").replace("flag--", "").upper() if flag else ""
    return {"rider": rider, "team": team, "nat": nat}


def fetch_stage_data(base: str, stage_no: int):
    """
    Fetches everything letour.fr publishes for a single stage: the finishing
    order ("rows") plus the per-stage classifications (points and mountain
    points won on the stage, the young riders' and teams' stage results) and
    the combativity award. Same ajax-stack mechanics as the general
    classifications, but stacks[1] holds the stage-specific URLs.
    """
    html = fetch(f"{base}/en/rankings/stage-{stage_no}")
    stacks = ajax_stacks(html)
    if len(stacks) < 2 or not stacks[1]:
        return {}
    stage_dict = stacks[1]

    def table(code, team_only, kind, sectioned=False):
        url = stage_dict.get(code)
        if not url:
            return []
        try:
            html = fetch(base + url)
        except Exception:
            return []
        if sectioned:
            return parse_sections(html, team_only=team_only, kind=kind)
        return parse_table(html, team_only=team_only, kind=kind)

    # 'ite' = individual stage result (normal stage). If it is empty — as in
    # a team time trial (TTT) — use 'ete' = the teams' stage result. Any other
    # codes are tried last as a fallback.
    attempts = [("ite", False), ("ete", True)]
    attempts += [(c, False) for c in stage_dict if c not in ("ite", "ete")]
    rows = []
    for code, team_only in attempts:
        rows = table(code, team_only, "time")
        if rows:
            break
    if not rows:
        return {}

    data = {"rows": rows}
    for key, cfg in STAGE_CLASS_CONFIG.items():
        data[key] = table(cfg["code"], cfg["team_only"], cfg["kind"], cfg["sectioned"])

    combative = None
    if stage_dict.get("ice"):
        try:
            combative = parse_combative(fetch(base + stage_dict["ice"]))
        except Exception:
            combative = None
    data["combative"] = combative
    return data


# A cached stage entry is reused only if it already has every per-stage
# statistic in the current format — entries written before those were scraped
# (or in the pre-section flat format) get refetched once.
STAGE_KEYS = ("rows", "points", "mountains", "youth", "teams", "combative")


def stage_entry_complete(entry) -> bool:
    if not entry.get("rows") or any(k not in entry for k in STAGE_KEYS):
        return False
    for key, cfg in STAGE_CLASS_CONFIG.items():
        if cfg["sectioned"] and any(
            not isinstance(s, dict) or "rows" not in s for s in entry[key]
        ):
            return False
    return True


def fetch_letour(base: str, out: Path) -> int:
    """Scrape one letour.fr-hosted tour into `out`. Returns 0 always."""
    try:
        main_html = fetch(f"{base}/en/rankings")
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
    if out.exists():
        try:
            prev = json.loads(out.read_text(encoding="utf-8"))
        except Exception:
            pass

    data = {"afterStage": stage_no, "stageWinners": []}

    for key, cfg in CLASS_CONFIG.items():
        url = general.get(cfg["code"])
        rows = []
        if url:
            try:
                table_html = fetch(base + url)
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
    # already-raced stages on every run. The latest stage is always refetched,
    # because its slower tables (combativity, points) can trail the finish
    # times by a while — once the next stage exists, the entry is frozen.
    previous_winners = {
        w["n"]: w["winner"] for w in prev.get("stageWinners", []) if w.get("winner")
    }
    prev_stage_results = prev.get("stageResults", {}) or {}
    data["stageResults"] = {}

    for n in range(1, stage_no + 1):
        key = str(n)
        winner = previous_winners.get(n, "")
        entry = prev_stage_results.get(key) or {}
        if n == stage_no or not stage_entry_complete(entry):
            try:
                entry = fetch_stage_data(base, n) or entry
            except Exception as e:
                print(f"  stage {n} results: {e}")
        if entry.get("rows"):
            data["stageResults"][key] = entry
            if not winner:
                winner = entry["rows"][0].get("rider", "")
        data["stageWinners"].append({"n": n, "winner": winner})

    # Withdrawals come from one page covering every stage, so they are cheap
    # to refresh on every run (unlike the cached per-stage tables — and a DNS
    # for stage N appears there before stage N has results). Only raced stages
    # get the key: the page shows future stages as "No withdrawal" too, which
    # must not be stored as fact. If the fetch fails, entries reused from the
    # previous run keep their stored withdrawals.
    try:
        withdrawals = fetch_withdrawals(base)
        for key, entry in data["stageResults"].items():
            entry["withdrawals"] = withdrawals.get(int(key), [])
    except Exception as e:
        print(f"  warning: fetching withdrawals failed: {e}")

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

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Wrote {out} (GC rows: {len(data['gc']['rows'])})")
    return 0


# Map a tour's "source" to the scraper that handles it. New sources (e.g. for
# the Giro or Vuelta) get their own function and an entry here.
SOURCES = {
    "letour": fetch_letour,
}


def fetch_tour(tour_id: str, cfg: dict) -> int:
    handler = SOURCES.get(cfg["source"])
    if handler is None:
        print(f"[{tour_id}] no handler for source '{cfg['source']}' — skipping.")
        return 0
    print(f"=== {tour_id} ===")
    return handler(cfg["base"], DATA_DIR / cfg["out"])


def main() -> int:
    requested = sys.argv[1:] or list(TOURS)
    unknown = [t for t in requested if t not in TOURS]
    if unknown:
        print(f"Unknown tour(s): {', '.join(unknown)}. Known: {', '.join(TOURS)}")
        return 1
    for tour_id in requested:
        fetch_tour(tour_id, TOURS[tour_id])
    return 0


if __name__ == "__main__":
    sys.exit(main())
