#!/usr/bin/env python3
"""Stáhne RSS/Atom feedy ze sources.toml, znormalizuje je a seskupí duplicity.

Výstup je JSON připravený k tomu, aby ho přečetl agent a napsal z něj digest.
Cílem je udělat všechnu deterministickou práci tady, aby model řešil jen to,
co skutečně potřebuje úsudek: výběr, zkrácení a formulaci.

Používá pouze standardní knihovnu (Python 3.11+ kvůli tomllib), takže
v cloud session není potřeba žádný setup script ani pip install.

Použití:
    python3 scripts/fetch_feeds.py                     # -> stdout
    python3 scripts/fetch_feeds.py --out feed.json     # -> soubor
    python3 scripts/fetch_feeds.py --hours 48
"""

from __future__ import annotations

import argparse
import concurrent.futures
import html
import json
import re
import sys
import tomllib
import unicodedata
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parent.parent

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

ATOM = "{http://www.w3.org/2005/Atom}"

# Na kolik znaků se krátí slova při porovnávání titulků (viz tokenize).
STEM_LEN = 6

# Rubriky a části URL, podle kterých se položka pozná jako sportovní. Hlavní
# feedy portálů sport míchají mezi ostatní zprávy, takže sekci nelze brát jen
# z konfigurace feedu — jinak by se táž zpráva ze dvou zdrojů nespojila.
SPORT_CATEGORIES = {
    "sport", "fotbal", "hokej", "tenis", "basketbal", "volejbal", "atletika",
    "cyklistika", "motorsport", "golf", "biatlon", "lyzovani", "formule 1",
    "liga mistru", "ostatni sporty", "olympiada",
}
SPORT_URL_MARKERS = ("/sport/", "sport.", "/fotbal/", "/hokej/", "/tenis/")

# Slova, která nenesou význam při porovnávání titulků. Krátká slova (<4 znaky)
# se zahazují zvlášť, takže tady stačí delší balast.
STOPWORDS = {
    "podle", "kvuli", "protoze", "ktery", "ktera", "ktere", "kteri", "byla",
    "bylo", "byli", "byly", "jsou", "jeho", "jeji", "jejich", "jako", "tady",
    "ktereho", "prave", "znovu", "dalsi", "letos", "vcera", "dnes", "zitra",
    "rekl", "rekla", "uvedl", "uvedla", "tvrdi", "pise", "informoval",
    "informovala", "oznamil", "oznamila", "bude", "budou", "mel", "mela",
}


# ─────────────────────────────  načtení konfigurace  ─────────────────────────


def load_config(path: Path) -> dict:
    with path.open("rb") as fh:
        cfg = tomllib.load(fh)
    cfg.setdefault("settings", {})
    cfg["settings"].setdefault("window_hours", 24)
    cfg["settings"].setdefault("cluster_threshold", 0.42)
    cfg["settings"].setdefault("timeout", 20)
    if not cfg.get("feeds"):
        raise SystemExit(f"{path}: chybí sekce [[feeds]]")
    return cfg


# ────────────────────────────────  stahování  ───────────────────────────────


def fetch(url: str, timeout: int) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


# ─────────────────────────────────  parsování  ──────────────────────────────


def strip_html(raw: str) -> str:
    """Vyhodí tagy, rozbalí entity a znormalizuje mezery."""
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw, flags=re.S | re.I)
    text = re.sub(r"<br\s*/?>|</p>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def parse_date(value: str | None, naive_tz: timezone | ZoneInfo = timezone.utc
               ) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=naive_tz)
    return dt.astimezone(timezone.utc)


def entry_text(node: ET.Element, *tags: str) -> str:
    """Vrátí první neprázdný text z uvedených tagů (RSS i Atom varianta)."""
    for tag in tags:
        found = node.find(tag)
        if found is not None:
            if found.text and found.text.strip():
                return found.text.strip()
            # Atom <content type="html"> může mít text v potomcích
            inner = "".join(found.itertext()).strip()
            if inner:
                return inner
    return ""


def entry_link(node: ET.Element) -> str:
    link = entry_text(node, "link", f"{ATOM}id")
    if link:
        return link
    for cand in node.findall(f"{ATOM}link"):
        if cand.get("rel", "alternate") == "alternate" and cand.get("href"):
            return cand.get("href", "")
    return ""


def detect_section(feed_section: str, link: str, categories: list[str]) -> str:
    """Sportovní zprávu pozná i v obecném feedu, podle rubriky nebo URL.

    Přeřazuje jen z obecného zpravodajství ("news"). Tematické sekce
    (tech, hradec) si své položky drží — sport FC Hradec Králové patří
    do hradecké rubriky, ne mezi celostátní sport.
    """
    if feed_section != "news":
        return feed_section
    if any(fold(c) in SPORT_CATEGORIES for c in categories):
        return "sport"
    if any(marker in link.lower() for marker in SPORT_URL_MARKERS):
        return "sport"
    return feed_section


def parse_feed(raw: bytes, feed: dict) -> list[dict]:
    root = ET.fromstring(raw)
    nodes = root.findall(".//item") or root.findall(f".//{ATOM}entry")
    naive_tz: timezone | ZoneInfo = timezone.utc
    if feed.get("assume_tz"):
        naive_tz = ZoneInfo(feed["assume_tz"])
    items: list[dict] = []

    for node in nodes:
        title = strip_html(entry_text(node, "title", f"{ATOM}title"))
        link = entry_link(node)
        if not title or not link:
            continue

        summary = strip_html(
            entry_text(
                node,
                "description",
                "{http://purl.org/rss/1.0/modules/content/}encoded",
                f"{ATOM}summary",
                f"{ATOM}content",
            )
        )
        published = parse_date(
            entry_text(node, "pubDate", f"{ATOM}updated", f"{ATOM}published")
            or None,
            naive_tz,
        )
        categories = [
            strip_html(c.text)
            for c in node.findall("category")
            if c.text and c.text.strip()
        ]
        # Seznam Zprávy dává rubriky do <sections>, ne do <category>.
        for sec in node.findall("sections"):
            for value in sec.itertext():
                value = value.strip()
                if value:
                    categories.append(value)

        items.append(
            {
                "source": feed["source"],
                "source_name": feed["name"],
                "section": detect_section(
                    feed.get("section", "news"), link, categories
                ),
                "kind": feed.get("kind", "breaking"),
                "weight": float(feed.get("weight", 1.0)),
                "title": title,
                "link": link,
                "published": published.isoformat() if published else None,
                "summary": summary,
                "categories": sorted(set(categories)),
            }
        )
    return items


# ─────────────────────────────────  clustering  ─────────────────────────────


def fold(text: str) -> str:
    """Malá písmena bez diakritiky."""
    folded = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in folded if not unicodedata.combining(ch))


def tokenize(title: str) -> set[str]:
    """Rozloží titulek na porovnatelné tokeny.

    Slova se krátí na prvních STEM_LEN znaků. Je to primitivní stemming, ale
    v češtině bez něj neprojdou ani zřejmé shody: "Newcastlu"/"Newcastle",
    "nejdražšího"/"nejdražším", "Horníčka"/"Horníček". Delší slova nesou
    dost informace i po zkrácení, takže riziko falešné shody je malé.
    """
    words = re.findall(r"[a-z0-9]+", fold(title))
    return {
        w[:STEM_LEN] for w in words if len(w) > 3 and w not in STOPWORDS
    }


def similarity(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if not inter:
        return 0.0
    # Overlap koeficient místo Jaccardu: titulky mají různou délku a krátký
    # titulek plně obsažený v delším je stejná zpráva.
    return inter / min(len(a), len(b))


def cluster(items: list[dict], threshold: float) -> list[dict]:
    """Seskupí položky, které popisují tutéž zprávu na různých portálech."""
    tokens = [tokenize(it["title"]) for it in items]
    parent = list(range(len(items)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[max(ri, rj)] = min(ri, rj)

    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            # Stejný zdroj = nespojovat, jinak by se slily dvě různé zprávy
            # z jednoho portálu i navazující update téhož tématu.
            if items[i]["source"] == items[j]["source"]:
                continue
            if items[i]["section"] != items[j]["section"]:
                continue
            if similarity(tokens[i], tokens[j]) >= threshold:
                union(i, j)

    groups: dict[int, list[int]] = {}
    for idx in range(len(items)):
        groups.setdefault(find(idx), []).append(idx)

    clusters = []
    for gid, idxs in groups.items():
        members = [items[i] for i in idxs]
        members.sort(key=lambda m: (m["published"] or "", m["source_name"]))
        sources = sorted({m["source"] for m in members})
        newest = max((m["published"] or "" for m in members), default="")
        # Skóre je jen pomůcka pro řazení vstupu, ne finální redakční rozhodnutí.
        score = round(
            len(sources) * 1.5 + max(m["weight"] for m in members), 3
        )
        clusters.append(
            {
                "id": f"c{gid:03d}",
                "section": members[0]["section"],
                "source_count": len(sources),
                "sources": sources,
                "score": score,
                "newest_published": newest or None,
                "items": members,
            }
        )

    clusters.sort(
        key=lambda c: (-c["source_count"], -c["score"], c["newest_published"] or ""),
        reverse=False,
    )
    return clusters


# ────────────────────────────────────  main  ────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, default=REPO_ROOT / "sources.toml")
    ap.add_argument("--out", type=Path, help="kam zapsat JSON (default stdout)")
    ap.add_argument("--hours", type=int, help="přepíše window_hours ze configu")
    args = ap.parse_args()

    cfg = load_config(args.config)
    settings = cfg["settings"]
    window = args.hours or settings["window_hours"]
    timeout = int(settings["timeout"])
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window)

    raw_items: list[dict] = []
    feed_status: list[dict] = []

    def work(feed: dict) -> tuple[dict, list[dict] | None, str | None]:
        try:
            return feed, parse_feed(fetch(feed["url"], timeout), feed), None
        except (urllib.error.URLError, ET.ParseError, OSError) as exc:
            return feed, None, f"{type(exc).__name__}: {exc}"

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for feed, items, error in pool.map(work, cfg["feeds"]):
            if error is not None:
                feed_status.append(
                    {"url": feed["url"], "name": feed["name"], "ok": False,
                     "error": error, "items_in_window": 0}
                )
                print(f"CHYBA  {feed['name']}: {error}", file=sys.stderr)
                continue

            fresh = [
                it for it in items
                if it["published"] and parse_date(it["published"]) >= cutoff
            ]
            raw_items.extend(fresh)
            feed_status.append(
                {"url": feed["url"], "name": feed["name"], "ok": True,
                 "error": None, "items_total": len(items),
                 "items_in_window": len(fresh)}
            )
            print(
                f"ok     {feed['name']}: {len(fresh)}/{len(items)} v okně",
                file=sys.stderr,
            )

    # Deduplikace identických URL (main feed a rychlé zprávy se překrývají).
    seen: set[str] = set()
    items: list[dict] = []
    for it in sorted(raw_items, key=lambda x: x["published"], reverse=True):
        key = it["link"].split("?")[0]
        if key in seen:
            continue
        seen.add(key)
        items.append(it)

    clusters = cluster(items, float(settings["cluster_threshold"]))

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_hours": window,
        "cutoff": cutoff.isoformat(),
        "feeds": feed_status,
        "failed_feeds": [f["name"] for f in feed_status if not f["ok"]],
    }

    section_counts: dict[str, int] = {}
    for c in clusters:
        section_counts[c["section"]] = section_counts.get(c["section"], 0) + 1

    payload["counts"] = {
        "items": len(items),
        "clusters": len(clusters),
        "sections": section_counts,
        "multi_source_clusters": sum(
            1 for c in clusters if c["source_count"] > 1
        ),
    }
    payload["clusters"] = clusters

    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
        print(f"\nzapsáno: {args.out}", file=sys.stderr)
    else:
        print(text)

    c = payload["counts"]
    per_section = ", ".join(
        f"{name} {count}" for name, count in sorted(c["sections"].items())
    )
    print(
        f"\nsouhrn: {c['items']} položek -> {c['clusters']} témat "
        f"({per_section}; {c['multi_source_clusters']} na více portálech)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
