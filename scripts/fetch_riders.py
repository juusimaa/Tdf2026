#!/usr/bin/env python3
"""
Grand tour start list — teams and riders with their final placing.

Scrapes each race's own site for the full start list (23 teams x 8 riders) and
joins every rider to the general classification, so each rider carries either a
final GC position + gap to the winner, or the fact that they did not finish.
The result is written to data/<tour>-riders.json, which the "Teams & riders"
tab of the tour page reads. Both handlers emit the same schema.

Two sources, because the organisers' sites are unrelated:
  * "letour"  — letour.fr (Tour de France). Has bib numbers and a per-stage
                withdrawal list, so non-finishers get a DNS/DNF/OTL reason and
                the stage they left.
  * "giro"    — giroditalia.it (Giro d'Italia, RCS). Publishes neither bib
                numbers nor a withdrawal list, so riders carry no bib and a
                non-finisher is only known as "not classified".

Unlike fetch_results.py this is not run on a schedule: the start list only
changes when riders are added or drop out, and the joined GC data is final once
the race is over. Run it by hand (or from the Actions tab) when the data needs
a refresh.

Usage:
    python scripts/fetch_riders.py                    # every registered tour
    python scripts/fetch_riders.py tdf2026 giro2026    # specific tour(s)
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

# Registry mirroring fetch_results.TOURS, but with one entry per organiser
# site. The Vuelta needs its own source handler before it can be listed here.
TOURS = {
    "tdf2026": {
        "source": "letour",
        "base": "https://www.letour.fr",
        "out": "tdf2026-riders.json",
    },
    "giro2026": {
        "source": "giro",
        "base": "https://www.giroditalia.it",
        "out": "giro2026-riders.json",
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
            riders.append(rider)
        teams.append({
            "name": team["name"],
            "code": team["code"],
            "url": base + team["url"] if team["url"].startswith("/") else team["url"],
            "gcPos": entry.get("pos"),
            "gcVal": entry.get("val", ""),
            "gcGap": entry.get("gap", ""),
            "riders": riders,
        })

    return write_riders(out, teams, after_stage)


def normalize_team(name: str) -> str:
    """Team names are compared across pages — collapse case and whitespace."""
    return re.sub(r"\s+", " ", name).strip().upper()


def write_riders(out: Path, teams: list, after_stage) -> int:
    """
    Sorts the teams into final team-classification order, wraps them with the
    race totals and writes data/<tour>-riders.json. Shared by every source so
    the pages only ever see one schema.
    """
    # A team missing from the team classification (or a race with no results
    # yet) keeps its start-list position.
    order = {id(t): i for i, t in enumerate(teams)}
    teams.sort(key=lambda t: (t["gcPos"] is None, t["gcPos"] or 0, order[id(t)]))

    rider_count = sum(len(t["riders"]) for t in teams)
    finishers = sum(1 for t in teams for r in t["riders"] if r["gcPos"])
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


# ---------------------------------------------------------------- giroditalia
# RCS builds its rankings page (/en/classifiche) out of divs, not tables: one
# wrapper per classification carrying the RCS code in its class name, holding
# .line-table rows. CLGEN is the general classification and CLSQAGEN the
# "Super Team" team classification.
#
# The site publishes no bib numbers and no withdrawal list, so riders are
# joined to the GC by their athlete-page slug (/en/atleti/<slug>/, identical on
# the team pages and in the rankings) and a rider missing from the GC is simply
# not classified — no reason or stage is available.
GIRO_GC_CODE = "CLGEN"
GIRO_TEAM_CODE = "CLSQAGEN"


def url_slug(url: str) -> str:
    """'https://…/en/atleti/vingegaard-jonas/' -> 'vingegaard-jonas'."""
    return (url or "").rstrip("/").rsplit("/", 1)[-1].lower()


def rcs_time(value: str) -> str:
    """RCS writes times as 83:22:51 — restated in the site's H h M' S'' form."""
    parts = [p for p in value.strip().split(":") if p.isdigit()]
    if len(parts) != 3:
        return value.strip()
    h, m, s = parts
    return f"{int(h)}h {int(m):02d}' {int(s):02d}''"


def rcs_gap(value: str) -> str:
    """
    Gaps come as MM:SS or H:MM:SS, and as 0:00 for the leader (who has none).
    Returned in the same "+ 00h 05' 22''" form the Tour data uses.
    """
    parts = [p for p in value.strip().split(":") if p.isdigit()]
    if not parts or not any(int(p) for p in parts):
        return ""
    if len(parts) == 2:
        parts = ["0"] + parts
    if len(parts) != 3:
        return value.strip()
    h, m, s = (int(p) for p in parts)
    return f"+ {h:02d}h {m:02d}' {s:02d}''"


def giro_ranking_rows(tree, code: str):
    """Rows of one /en/classifiche classification, in published order."""
    wrapper = tree.css_first(f"div.js-tab-classifica-{code}")
    return wrapper.css(".line-table") if wrapper else []


def parse_giro_roster(html: str):
    """
    Parses one team page's rider list. Names are split across two lines
    ("Jonas<br>Vingegaard"), which is exactly the given name / surname split the
    site's usual "Jonas VINGEGAARD" form needs.
    """
    riders = []
    for item in HTMLParser(html).css(".riders-list .rider-item"):
        info = item.css_first(".info .h5")
        if info is None:
            continue
        parts = [
            re.sub(r"<[^>]+>", "", p).strip()
            for p in re.split(r"<br\s*/?>", info.html or "")
        ]
        parts = [p for p in parts if p]
        if not parts:
            continue
        given, surname = " ".join(parts[:-1]), parts[-1]
        nat = item.css_first(".label-4")
        link = item.css_first("a")
        riders.append({
            "name": f"{given} {surname.upper()}".strip(),
            "nat": nat.text(strip=True).upper() if nat else "",
            "slug": url_slug(link.attributes.get("href") if link else ""),
        })
    return riders


def fetch_giro(base: str, out: Path) -> int:
    """Scrape giroditalia.it's teams, rosters and final GC into `out`."""
    try:
        teams_html = fetch(f"{base}/en/squadre/")
    except Exception as e:
        print(f"Failed to fetch the team list: {e}")
        return 0

    cards = HTMLParser(teams_html).css("a.single-squadra")
    if not cards:
        print("The team list has not been published yet.")
        return 0

    gc, team_gc, after_stage = {}, {}, None
    try:
        tree = HTMLParser(fetch(f"{base}/en/classifiche/"))
        for row in giro_ranking_rows(tree, GIRO_GC_CODE):
            pos = row.css_first(".position")
            link = row.css_first(".atleta-info a")
            time_el, gap_el = row.css_first(".tempo"), row.css_first(".distacco")
            if pos is None or link is None or not pos.text(strip=True).isdigit():
                continue
            gc[url_slug(link.attributes.get("href"))] = {
                "pos": int(pos.text(strip=True)),
                "val": rcs_time(time_el.text(strip=True)) if time_el else "",
                "gap": rcs_gap(gap_el.text(strip=True)) if gap_el else "",
            }
        # The team table has no rank column — the rows are already in order.
        for i, row in enumerate(giro_ranking_rows(tree, GIRO_TEAM_CODE), start=1):
            link = row.css_first(".team a")
            time_el, gap_el = row.css_first(".tempo"), row.css_first(".distacco")
            if link is None:
                continue
            team_gc[url_slug(link.attributes.get("href"))] = {
                "pos": i,
                "val": rcs_time(time_el.text(strip=True)) if time_el else "",
                "gap": rcs_gap(gap_el.text(strip=True)) if gap_el else "",
            }
        # The rankings page links every raced stage as /classifiche/di-tappa/N.
        stages = [int(n) for n in re.findall(r"/classifiche/di-tappa/(\d+)", tree.html or "")]
        after_stage = max(stages) if stages else None
    except Exception as e:
        print(f"  warning: fetching the classifications failed: {e}")

    teams = []
    for card in cards:
        url = card.attributes.get("href") or ""
        name_el, nat_el = card.css_first(".h5"), card.css_first(".label-4")
        name = name_el.text(strip=True) if name_el else ""
        try:
            roster = parse_giro_roster(fetch(url))
        except Exception as e:
            print(f"  warning: fetching the roster of {name} failed: {e}")
            roster = []

        riders = []
        for r in roster:
            placing = gc.get(r["slug"])
            riders.append({
                "bib": None,  # RCS does not publish bib numbers
                "name": r["name"],
                "nat": r["nat"],
                "gcPos": placing["pos"] if placing else None,
                "gcVal": placing["val"] if placing else "",
                "gcGap": placing["gap"] if placing else "",
                "status": "" if placing else "DNF",
                "statusStage": None,  # no withdrawal list on giroditalia.it
            })

        entry = team_gc.get(url_slug(url), {})
        teams.append({
            "name": name,
            "code": "",
            "nat": nat_el.text(strip=True).upper() if nat_el else "",
            "url": url,
            "gcPos": entry.get("pos"),
            "gcVal": entry.get("val", ""),
            "gcGap": entry.get("gap", ""),
            "riders": riders,
        })

    return write_riders(out, teams, after_stage)


SOURCES = {
    "letour": fetch_letour,
    "giro": fetch_giro,
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
