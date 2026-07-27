#!/usr/bin/env python3
"""
Grand tour start list — teams and riders with their final placing.

Scrapes letour.fr's start list (/en/riders: 23 teams x 8 riders) and joins
every rider to the general classification and to the withdrawal list, so each
rider carries either a final GC position + gap to the winner, or the reason and
stage they left the race. The result is written to data/<tour>-riders.json,
which the "Teams & riders" tab of the tour page reads.

Unlike fetch_results.py this is not run on a schedule: the start list only
changes when riders are added or drop out, and the joined GC data is final once
the race is over. Run it by hand (or from the Actions tab) when the data needs
a refresh.

Usage:
    python scripts/fetch_riders.py               # every registered tour
    python scripts/fetch_riders.py tdf2026        # specific tour(s)
Dependencies:  pip install requests selectolax
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from selectolax.parser import HTMLParser

# Shares the HTTP session, the ajax-stack mechanics and the withdrawal parser
# with the results scraper — both read the same site.
from fetch_results import DATA_DIR, ajax_stacks, fetch, fetch_withdrawals

# Registry mirroring fetch_results.TOURS. letour.fr only covers the Tour de
# France; the Giro and Vuelta need their own source handler before they can be
# listed here.
TOURS = {
    "tdf2026": {
        "source": "letour",
        "base": "https://www.letour.fr",
        "out": "tdf2026-riders.json",
    },
}


def parse_startlist(html: str):
    """
    Parses /en/riders. The whole start list lives in one .list--competitors
    container where team headings (h3.list__heading) and rider lists
    (.list__box) are siblings, so the children are walked in document order and
    every rider box is attached to the heading above it.

    Returns [{name, code, url, riders: [{bib, listName, nat}]}] in start-list
    (i.e. bib) order.
    """
    tree = HTMLParser(html)
    container = tree.css_first("section.competitors .list--competitors")
    if container is None:
        return []

    teams, current = [], None
    for node in container.iter():
        if node.tag == "h3":
            link = node.css_first("a")
            href = (link.attributes.get("href") or "") if link else ""
            code = ""
            m = re.match(r"/[a-z]{2}/team/([^/]+)/", href)
            if m:
                code = m.group(1).upper()
            current = {
                "name": (link or node).text(strip=True),
                "code": code,
                "url": href,
                "riders": [],
            }
            teams.append(current)
        elif current is not None:
            for li in node.css("li.list__box__item"):
                bib_el = li.css_first(".bib")
                link = li.css_first("a.runner__link")
                flag = li.css_first("[data-class]")
                bib = bib_el.text(strip=True) if bib_el else ""
                if not bib.isdigit() or link is None:
                    continue
                nat = (flag.attributes.get("data-class") or "") if flag else ""
                current["riders"].append({
                    "bib": int(bib),
                    "listName": link.text(strip=True),
                    "nat": nat.replace("flag--", "").upper(),
                })

    return [t for t in teams if t["riders"]]


def parse_gc_by_bib(html: str):
    """
    Parses the general-classification fragment into {bib: {pos, val, gap}}.
    The GC table's columns are rank / rider / rider no. / team / time / gap, and
    the bib is what lets a GC row be matched to a start-list rider reliably —
    the displayed rider names differ between letour.fr's own pages.

    The rider name (an "alt" attribute on the jersey image) is kept as a
    surname hint for display_name(); it is sometimes abbreviated
    ("P. SEIXAS"), but its uppercase part is always the full surname.
    """
    out = {}
    for tr in HTMLParser(html).css("tbody tr.rankingTables__row"):
        tds = tr.css("td")
        if len(tds) < 5:
            continue
        pos_text = tds[0].text(strip=True)
        bib_text = tds[2].text(strip=True)
        if not pos_text.isdigit() or not bib_text.isdigit():
            continue
        img = tr.css_first(".rankingTables__row__profile.runner img")
        gap = tds[5].text(strip=True) if len(tds) > 5 else ""
        out[int(bib_text)] = {
            "pos": int(pos_text),
            "val": tds[4].text(strip=True),
            "gap": gap if gap and gap != "-" else "",
            "name": (img.attributes.get("alt") or "").strip() if img else "",
        }
    return out


def titlecase(word: str) -> str:
    """'JEAN-BAPTISTE' -> 'Jean-Baptiste', 'O’BRIEN' -> 'O’Brien'."""
    return re.sub(r"[^\W\d_]+", lambda m: m.group(0).capitalize(), word.lower())


def display_name(list_name: str, hint: str) -> str:
    """
    letour.fr writes rider names three different ways: the start list is all
    caps ("TADEJ POGACAR"), the rankings use "Tadej POGACAR" (sometimes
    abbreviated to "P. SEIXAS") and the withdrawal list uses "BERTHET Clément".
    The one part that is always full and always uppercase is the surname, so it
    is taken from the ranking/withdrawal `hint`, and the given names come from
    the start list with the surname tokens stripped off the end.

    Produces the "Tadej POGACAR" form the rest of the page uses. Without a
    usable hint the first token is treated as the given name.
    """
    tokens = list_name.split()
    if not tokens:
        return titlecase(hint) if hint else ""

    surname = [w for w in hint.split() if w.isupper() and len(w) > 1]
    if surname:
        cut = len(tokens)
        while cut > 1 and tokens[cut - 1] in surname:
            cut -= 1
        given = tokens[:cut]
    else:
        given, surname = tokens[:1], tokens[1:]

    return " ".join([titlecase(w) for w in given] + surname).strip()


def fetch_letour(base: str, out: Path) -> int:
    """Scrape one letour.fr-hosted tour's start list into `out`. Returns 0."""
    try:
        startlist = parse_startlist(fetch(f"{base}/en/riders"))
    except Exception as e:
        print(f"Failed to fetch the start list: {e}")
        return 0
    if not startlist:
        print("The start list has not been published yet.")
        return 0

    # General classification (individual + teams) after the latest stage; both
    # come from the same ajax stack the results scraper uses.
    gc, team_gc, after_stage = {}, {}, None
    try:
        stacks = ajax_stacks(fetch(f"{base}/en/rankings"))
        general = stacks[0] if stacks else {}
        if general.get("itg"):
            after_stage = int(general["itg"].split("/")[4])
            gc = parse_gc_by_bib(fetch(base + general["itg"]))
        if general.get("etg"):
            for tr in HTMLParser(fetch(base + general["etg"])).css("tbody tr.rankingTables__row"):
                tds = tr.css("td")
                if len(tds) < 3 or not tds[0].text(strip=True).isdigit():
                    continue
                gap = tds[3].text(strip=True) if len(tds) > 3 else ""
                team_gc[normalize_team(tds[1].text(strip=True))] = {
                    "pos": int(tds[0].text(strip=True)),
                    "val": tds[2].text(strip=True),
                    "gap": gap if gap and gap != "-" else "",
                }
    except Exception as e:
        print(f"  warning: fetching the classifications failed: {e}")

    # Withdrawals: one page covers every stage, keyed here by bib so a rider
    # missing from the GC can be shown with the stage and reason they left.
    left = {}
    try:
        for stage_no, rows in fetch_withdrawals(base).items():
            for row in rows:
                left[row["bib"]] = {"stage": stage_no, "reason": row["reason"], "name": row["rider"]}
    except Exception as e:
        print(f"  warning: fetching withdrawals failed: {e}")

    teams = []
    finishers = 0
    for team in startlist:
        entry = team_gc.get(normalize_team(team["name"]), {})
        riders = []
        for r in team["riders"]:
            placing = gc.get(r["bib"])
            gone = left.get(r["bib"])
            hint = (placing or {}).get("name") or (gone or {}).get("name", "")
            rider = {
                "bib": r["bib"],
                "name": display_name(r["listName"], hint),
                "nat": r["nat"],
                "gcPos": placing["pos"] if placing else None,
                "gcVal": placing["val"] if placing else "",
                "gcGap": placing["gap"] if placing else "",
                "status": gone["reason"] if gone else ("" if placing else "DNF"),
                "statusStage": gone["stage"] if gone else None,
            }
            if placing:
                finishers += 1
            riders.append(rider)
        teams.append({
            "name": team["name"],
            "code": team["code"],
            "url": team["url"],
            "gcPos": entry.get("pos"),
            "gcVal": entry.get("val", ""),
            "gcGap": entry.get("gap", ""),
            "riders": riders,
        })

    # Teams in final team-classification order; any team missing from that
    # table (or a race with no results yet) keeps its start-list position.
    order = {t["name"]: i for i, t in enumerate(teams)}
    teams.sort(key=lambda t: (t["gcPos"] is None, t["gcPos"] or 0, order[t["name"]]))

    rider_count = sum(len(t["riders"]) for t in teams)
    data = {
        "afterStage": after_stage,
        "teamCount": len(teams),
        "riderCount": rider_count,
        "finishers": finishers,
        "teams": teams,
    }

    # Same rule as the results scraper: only stamp a new timestamp when the
    # content actually changed, so re-running does not create empty commits.
    prev = {}
    if out.exists():
        try:
            prev = json.loads(out.read_text(encoding="utf-8"))
        except Exception:
            pass
    prev_content = {k: v for k, v in prev.items() if k not in ("updated", "updatedText")}
    if prev_content == data and prev.get("updated"):
        data["updated"] = prev["updated"]
        data["updatedText"] = prev["updatedText"]
    else:
        now = datetime.now(ZoneInfo("Europe/Helsinki"))
        data["updated"] = now.isoformat()
        data["updatedText"] = now.strftime("Päivitetty %d.%m.%Y klo %H.%M (Suomen aikaa)")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Wrote {out} ({len(teams)} teams, {rider_count} riders, {finishers} classified)")
    return 0


def normalize_team(name: str) -> str:
    """Team names are compared across pages — collapse case and whitespace."""
    return re.sub(r"\s+", " ", name).strip().upper()


SOURCES = {
    "letour": fetch_letour,
}


def main() -> int:
    requested = sys.argv[1:] or list(TOURS)
    unknown = [t for t in requested if t not in TOURS]
    if unknown:
        print(f"Unknown tour(s): {', '.join(unknown)}. Known: {', '.join(TOURS)}")
        return 1
    for tour_id in requested:
        cfg = TOURS[tour_id]
        handler = SOURCES.get(cfg["source"])
        if handler is None:
            print(f"[{tour_id}] no handler for source '{cfg['source']}' — skipping.")
            continue
        print(f"=== {tour_id} ===")
        handler(cfg["base"], DATA_DIR / cfg["out"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
