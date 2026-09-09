#!/usr/bin/env python3
"""Doplní do digestu anglickou verzi (pole `en`, `highlights_en`, počasí).

Web je anglicky a češtinu ukazuje po větách, takže ke každé české větě
musí existovat její překlad. Ručně přepisovat češtinu do digestu podruhé
je zbytečná práce i zdroj překlepů — proto češtinu rozdělí na věty tenhle
skript a agent dodá jen angličtinu.

Vstupní soubor s překladem (výchozí /tmp/en.json):

    {
      "highlights": ["Anglická věta.", "…"],
      "weather": { "summary": "…", "outlook": "…" },
      "items": [
        {
          "headline": "English headline",
          "sentences": ["First English sentence.", "Second one."],
          "glossary": [
            { "term": "curb", "definition": "to control or limit sth",
              "cs": "omezit" }
          ]
        }
      ]
    }

`items` musí mít stejný počet položek jako digest a jít ve stejném pořadí.
Vět v `sentences` musí být tolik, na kolik se rozpadne české `body`; když
sedět nebudou, skript vypíše český rozpad s čísly a nic nezapíše. Když
rozdělení nesedí schválně (dvě české věty patří do jedné anglické), dá se
u položky připsat vlastní `"cs": [...]` — úseky se pak berou odtud.

Použití:
    python3 scripts/add_english.py --digest digests/2026-09-08.json --show
    python3 scripts/add_english.py --digest digests/2026-09-08.json \\
        --translations /tmp/en.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Zkratky, po kterých tečka větu nekončí. Bez nich by se text trhal
# uprostřed jmen („podle Mgr. Nováka") a čísel („192 mil. Kč").
ABBREV = {
    "tzv", "tj", "tzn", "resp", "např", "atd", "apod", "mj", "cca", "č",
    "mil", "mld", "tis", "str", "roč", "sv", "st", "ul", "nám", "kr",
    "mgr", "ing", "bc", "mudr", "judr", "phdr", "rndr", "prof", "doc",
    "ph", "csc", "dis", "a", "s", "r", "o", "kč", "hod", "min", "max",
}

# Konec věty: interpunkce, případně uvozovka nebo závorka, mezera a začátek
# další věty. Rozdělení se pak ještě prosívá podle kontextu (viz split_cs).
BOUNDARY = re.compile(r'([.!?…]["“»)\]]?)\s+(?=[„"(\[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ0-9])')

WORD_BEFORE = re.compile(r'([\wÁ-Žá-ž]+)[.!?…]["“»)\]]?$')


def split_cs(body: str) -> list[str]:
    """Rozdělí český odstavec na věty.

    Heuristika, ne parser: co se rozdělí špatně, se v digestu přepíše
    ručním polem `cs`. Zpětné složení úseků dá vždy původní text —
    o tohle se opírá kontrola v build_site.py.
    """
    text = " ".join(body.split())
    parts: list[str] = []
    start = 0
    for match in BOUNDARY.finditer(text):
        end = match.end(1)
        head = text[start:end]
        before = WORD_BEFORE.search(head)
        token = before.group(1).lower() if before else ""
        # Řadová číslovka („8. září") a zkratka („tzv.") tečkou nekončí
        # větu; číslo na konci věty ano, když další věta začíná velkým
        # písmenem — to už ale rozhodl regulární výraz nahoře.
        if token in ABBREV:
            continue
        if token.isdigit() and text[match.end():match.end() + 1].islower():
            continue
        parts.append(head)
        start = match.end()
    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return parts or [text]


def show(digest: dict) -> None:
    for idx, item in enumerate(digest["items"], start=1):
        print(f'\n[{idx}] {item["rubric"]} · {item["headline"]}')
        for k, sentence in enumerate(split_cs(item["body"]), start=1):
            print(f"    {k}. {sentence}")


def merge(digest: dict, translation: dict) -> list[str]:
    """Vloží angličtinu do digestu. Vrací seznam problémů; při neprázdném
    seznamu se nic nezapisuje."""
    problems: list[str] = []
    items = digest["items"]
    given = translation.get("items") or []
    if len(given) != len(items):
        return [
            f"překlad má {len(given)} položek, digest {len(items)} — "
            f"musí si odpovídat jedna ku jedné a ve stejném pořadí"
        ]

    for idx, (item, en) in enumerate(zip(items, given), start=1):
        where = f"items[{idx}]"
        headline = (en.get("headline") or "").strip()
        sentences = en.get("sentences") or []
        if not headline:
            problems.append(f"{where}: chybí anglický headline")
        if not sentences:
            problems.append(f"{where}: chybí anglické sentences")
            continue
        czech = en.get("cs") or split_cs(item["body"])
        if len(czech) != len(sentences):
            problems.append(
                f"{where}: {len(sentences)} anglických vět proti "
                f"{len(czech)} českým — sluč nebo rozděl anglické věty, "
                f"nebo dodej vlastní pole 'cs'.\n"
                + "\n".join(f"      {k}. {s}"
                            for k, s in enumerate(czech, start=1))
            )
            continue
        if " ".join(" ".join(c.split()) for c in czech) != \
                " ".join(item["body"].split()):
            problems.append(
                f"{where}: pole 'cs' nedává dohromady původní body"
            )
            continue
        block = {
            "headline": headline,
            "sentences": [
                {"en": e.strip(), "cs": c} for e, c in zip(sentences, czech)
            ],
        }
        if en.get("glossary"):
            block["glossary"] = en["glossary"]
        item["en"] = block

    if problems:
        return problems

    if digest.get("highlights"):
        lines = translation.get("highlights") or []
        if len(lines) != len(digest["highlights"]):
            return [
                f"highlights: {len(lines)} anglických vět proti "
                f"{len(digest['highlights'])} českým"
            ]
        digest["highlights_en"] = [line.strip() for line in lines]

    weather = digest.get("weather")
    if weather:
        given_weather = translation.get("weather") or {}
        if not given_weather.get("summary"):
            return ["weather: chybí anglické summary"]
        weather["summary_en"] = given_weather["summary"].strip()
        if weather.get("outlook"):
            if not given_weather.get("outlook"):
                return ["weather: chybí anglický outlook"]
            weather["outlook_en"] = given_weather["outlook"].strip()
    return []


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--digest", required=True, help="digests/RRRR-MM-DD.json")
    ap.add_argument("--translations", default="/tmp/en.json",
                    help="soubor s anglickým textem (výchozí /tmp/en.json)")
    ap.add_argument("--show", action="store_true",
                    help="jen vypíše český rozpad na věty, nic nezapisuje")
    args = ap.parse_args()

    path = Path(args.digest)
    digest = json.loads(path.read_text(encoding="utf-8"))

    if args.show:
        show(digest)
        return 0

    translation = json.loads(Path(args.translations).read_text(encoding="utf-8"))
    problems = merge(digest, translation)
    if problems:
        print("CHYBA: angličtina se nedá spojit s češtinou:", file=sys.stderr)
        for problem in problems:
            print(f"  · {problem}", file=sys.stderr)
        return 1

    path.write_text(
        json.dumps(digest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"{path.name}: doplněna angličtina u {len(digest['items'])} položek",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
