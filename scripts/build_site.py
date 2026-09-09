#!/usr/bin/env python3
"""Vygeneruje statický web z digestů v digests/*.json do docs/.

Web se hostuje na GitHub Pages přímo z adresáře docs/ na hlavní branchi,
takže stačí commitnout výstup — žádná CI pipeline není potřeba.

Skript nejdřív každý digest zvaliduje. Když je nějaký rozbitý, skončí
chybou a nic nezapíše, aby se na web nedostal poloprázdný den.

Používá pouze standardní knihovnu.

Použití:
    python3 scripts/build_site.py
    python3 scripts/build_site.py --check    # jen validace, nic nezapisuje
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import subprocess
import sys
import urllib.parse
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parent.parent
DIGESTS = REPO_ROOT / "digests"
DOCS = REPO_ROOT / "docs"

SITE_TITLE = "Denní přehled"
SITE_DESCRIPTION = (
    "Přehled zpráv z českých zdrojů. Nové vydání každý den v 17:00, "
    "shrnuje uplynulých 24 hodin."
)

PRAGUE = ZoneInfo("Europe/Prague")

RUBRIC_ORDER = [
    "Domov",
    "Hradec Králové",
    "Svět",
    "Ekonomika",
    "Technologie",
    "Společnost a kultura",
    "Za pozornost",
    "Sport",
]

WEEKDAYS = [
    "pondělí", "úterý", "středa", "čtvrtek", "pátek", "sobota", "neděle",
]
MONTHS = [
    "ledna", "února", "března", "dubna", "května", "června", "července",
    "srpna", "září", "října", "listopadu", "prosince",
]

TIME_RE = re.compile(r"^\d{2}:\d{2}$")

# ─────────────────────────────  anglická mutace  ────────────────────────────
#
# Web je dvojjazyčný: výchozí je angličtina (čte se kvůli učení), čeština
# se dá zapnout přepínačem a u každé věty zvlášť. Anglický text nese digest
# v poli `en` u položek, chrome (nadpisy, data, patička) překládá skript.

SITE_TITLE_EN = "Daily Digest"
SITE_DESCRIPTION_EN = (
    "News from Czech sources, retold in English. A new issue every day "
    "at 17:00, covering the last 24 hours."
)

RUBRIC_EN = {
    "Domov": "Czechia",
    "Hradec Králové": "Hradec Králové",
    "Svět": "World",
    "Ekonomika": "Economy",
    "Technologie": "Technology",
    "Společnost a kultura": "Society & culture",
    "Za pozornost": "Worth reading",
    "Sport": "Sport",
}

WEEKDAYS_EN = [
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday",
    "Sunday",
]
MONTHS_EN = [
    "January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December",
]

# Cambridge přesměruje i tvary se skloňováním („curbed" → heslo „curb"),
# takže odkaz stavíme na vyhledávání a ne na konkrétní heslo.
CAMBRIDGE_SEARCH = (
    "https://dictionary.cambridge.org/search/direct/?datasetsearch=english&q="
)

# Slovíčko se v textu hledá jako celé slovo, ne jako podřetězec: „ban"
# se nesmí chytit uvnitř „banking".
_TERM_CACHE: dict[str, re.Pattern] = {}


def term_re(term: str) -> re.Pattern:
    pat = _TERM_CACHE.get(term)
    if pat is None:
        pat = re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", re.IGNORECASE)
        _TERM_CACHE[term] = pat
    return pat


def norm_ws(text: str) -> str:
    return " ".join(text.split())


def has_english(data: dict) -> bool:
    """Má vydání anglickou mutaci? Buď ji mají všechny položky, nebo žádná."""
    return bool(data["items"]) and all(i.get("en") for i in data["items"])


# ──────────────────────────────────  validace  ──────────────────────────────


class DigestError(Exception):
    pass


def validate(data: dict, path: Path) -> None:
    def fail(msg: str) -> None:
        raise DigestError(f"{path.name}: {msg}")

    for field in ("date", "items"):
        if field not in data:
            fail(f"chybí povinné pole '{field}'")

    if data["date"] != path.stem:
        fail(f"pole date ({data['date']}) neodpovídá názvu souboru")
    try:
        date.fromisoformat(data["date"])
    except ValueError:
        fail(f"date '{data['date']}' není platné RRRR-MM-DD")

    if "covers" in data:
        try:
            covers = date.fromisoformat(data["covers"])
        except (TypeError, ValueError):
            fail(f"covers '{data['covers']}' není platné RRRR-MM-DD")
        issued = date.fromisoformat(data["date"])
        if not timedelta(0) <= issued - covers <= timedelta(days=7):
            fail(
                f"covers ({data['covers']}) musí být den vydání "
                f"({data['date']}) nebo některý z předchozích sedmi dnů"
            )

    if not isinstance(data["items"], list) or not data["items"]:
        fail("items musí být neprázdné pole")

    weather = data.get("weather")
    if weather is not None:
        if not isinstance(weather, dict) or not weather.get("summary"):
            fail("weather musí být objekt s neprázdným polem 'summary'")
        for key in ("summary", "outlook", "place", "icon",
                    "summary_en", "outlook_en"):
            if key in weather and not isinstance(weather[key], str):
                fail(f"weather.{key} musí být řetězec")
        if "icon" in weather and weather["icon"] not in WEATHER_ICONS:
            fail(
                f"weather.icon '{weather['icon']}' neznám, povolené jsou "
                f"{', '.join(sorted(WEATHER_ICONS))}"
            )
        validate_weather_days(weather.get("days"), data["date"], fail)

    validate_highlights(data, fail)

    for idx, item in enumerate(data["items"], start=1):
        where = f"items[{idx}]"
        for field in ("rubric", "time", "headline", "body", "sources"):
            if not item.get(field):
                fail(f"{where}: chybí nebo je prázdné pole '{field}'")
        if item["rubric"] not in RUBRIC_ORDER:
            fail(
                f"{where}: neznámá rubrika '{item['rubric']}', "
                f"povolené jsou {', '.join(RUBRIC_ORDER)}"
            )
        if not TIME_RE.match(item["time"]):
            fail(f"{where}: time '{item['time']}' není ve formátu HH:MM")
        if item.get("day") not in (None, "covered", "prev"):
            fail(
                f"{where}: day '{item['day']}' neznám, povolené jsou "
                f"'covered' (pokrytý den, výchozí) a 'prev' "
                f"(večer předchozího dne)"
            )
        if not isinstance(item["sources"], list):
            fail(f"{where}: sources musí být pole")
        for src in item["sources"]:
            if not src.get("name") or not src.get("url"):
                fail(f"{where}: zdroj musí mít name i url")
            if not src["url"].startswith("http"):
                fail(f"{where}: url '{src['url'][:60]}' nezačíná na http")
        validate_item_english(item, where, fail)

    validate_english_coverage(data, fail)


def validate_highlights(data: dict, fail) -> None:
    """Shrnutí dne — `highlights` a jeho anglický protějšek."""
    for key in ("highlights", "highlights_en"):
        value = data.get(key)
        if value is None:
            continue
        if not isinstance(value, list):
            fail(f"{key} musí být pole vět")
        for idx, line in enumerate(value, start=1):
            if not isinstance(line, str) or not line.strip():
                fail(f"{key}[{idx}] musí být neprázdný řetězec")
    if data.get("highlights_en") is not None:
        cs = data.get("highlights") or []
        if len(data["highlights_en"]) != len(cs):
            fail(
                f"highlights_en má {len(data['highlights_en'])} vět, "
                f"highlights {len(cs)} — musí si odpovídat jedna ku jedné"
            )


def first_difference(a: str, b: str) -> str:
    """Místo, kde se dva texty rozejdou — pro čitelnou chybovou hlášku."""
    common = 0
    for common, (x, y) in enumerate(zip(a, b)):
        if x != y:
            break
    else:
        common = min(len(a), len(b))
    lo = max(0, common - 30)
    return f"…{a[lo:common + 40]}\n     proti …{b[lo:common + 40]}"


def validate_item_english(item: dict, where: str, fail) -> None:
    """Anglická mutace položky — pole `en`.

    Angličtina není volný převod: `en.sentences` rozděluje **český** text
    na úseky a ke každému dává překlad. Součet českých úseků se proto musí
    přesně rovnat poli `body`, jinak by web ukazoval dvě různé češtiny
    a po větách by se nedalo srovnávat.
    """
    en = item.get("en")
    if en is None:
        return
    if not isinstance(en, dict):
        fail(f"{where}: en musí být objekt")
    if not isinstance(en.get("headline"), str) or not en["headline"].strip():
        fail(f"{where}: en.headline chybí nebo je prázdný")

    pairs = en.get("sentences")
    if not isinstance(pairs, list) or not pairs:
        fail(f"{where}: en.sentences musí být neprázdné pole dvojic en/cs")
    for k, pair in enumerate(pairs, start=1):
        if not isinstance(pair, dict):
            fail(f"{where}: en.sentences[{k}] musí být objekt")
        for side in ("en", "cs"):
            if not isinstance(pair.get(side), str) or not pair[side].strip():
                fail(f"{where}: en.sentences[{k}].{side} chybí nebo je prázdný")

    joined = norm_ws(" ".join(p["cs"] for p in pairs))
    body = norm_ws(item["body"])
    if joined != body:
        fail(
            f"{where}: české úseky v en.sentences nedávají dohromady pole "
            f"body — rozcházejí se u {first_difference(joined, body)}"
        )

    haystack = " ".join([en["headline"]] + [p["en"] for p in pairs])
    glossary = en.get("glossary")
    if glossary is None:
        return
    if not isinstance(glossary, list):
        fail(f"{where}: en.glossary musí být pole")
    seen: set[str] = set()
    for k, entry in enumerate(glossary, start=1):
        spot = f"{where}: en.glossary[{k}]"
        if not isinstance(entry, dict):
            fail(f"{spot} musí být objekt")
        for field in ("term", "definition"):
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                fail(f"{spot}: chybí nebo je prázdné pole '{field}'")
        if "cs" in entry and not isinstance(entry["cs"], str):
            fail(f"{spot}: cs musí být řetězec")
        key = entry["term"].lower()
        if key in seen:
            fail(f"{spot}: slovíčko '{entry['term']}' je v položce dvakrát")
        seen.add(key)
        if not term_re(entry["term"]).search(haystack):
            fail(
                f"{spot}: slovíčko '{entry['term']}' se v anglickém textu "
                f"položky vůbec nevyskytuje — vysvětlovat se dá jen slovo, "
                f"které v textu opravdu je"
            )


def validate_english_coverage(data: dict, fail) -> None:
    """Buď anglicky celé vydání, nebo nic.

    Půlka přeložených položek by dala stránku, která se tváří anglicky
    a přitom v ní půlka zpráv zůstane česky — to je horší než čistě české
    vydání, které se prostě přepínačem nepřepíná.
    """
    with_en = [i for i in data["items"] if i.get("en")]
    if not with_en:
        for key in ("highlights_en",):
            if data.get(key):
                fail(f"{key} je vyplněné, ale žádná položka nemá pole 'en'")
        if (data.get("weather") or {}).get("summary_en"):
            fail("weather.summary_en je vyplněné, ale položky nemají 'en'")
        return
    if len(with_en) != len(data["items"]):
        missing = [
            str(idx) for idx, i in enumerate(data["items"], start=1)
            if not i.get("en")
        ]
        fail(
            f"anglicky je jen část vydání — pole 'en' chybí u items "
            f"{', '.join(missing)}. Přelož všechny položky, nebo žádnou."
        )
    if data.get("highlights") and not data.get("highlights_en"):
        fail("vydání je anglicky, ale chybí highlights_en")
    weather = data.get("weather")
    if weather:
        if not weather.get("summary_en"):
            fail("vydání je anglicky, ale chybí weather.summary_en")
        if weather.get("outlook") and not weather.get("outlook_en"):
            fail("vydání je anglicky, ale chybí weather.outlook_en")


def validate_weather_days(days, issue_iso: str, fail) -> None:
    """Předpověď na další dny — pole `weather.days`.

    Vydání vzniká v 17:00, takže čtenáře zajímá zítřek a dál. Proto musí
    každý den ležet **za** dnem vydání a být seřazený od nejbližšího.
    """
    if days is None:
        return
    if not isinstance(days, list) or not days:
        fail("weather.days musí být neprázdné pole, nebo úplně chybět")

    issued = date.fromisoformat(issue_iso)
    previous = issued
    for idx, day in enumerate(days, start=1):
        where = f"weather.days[{idx}]"
        if not isinstance(day, dict):
            fail(f"{where}: musí být objekt")
        try:
            when = date.fromisoformat(day.get("date", ""))
        except (TypeError, ValueError):
            fail(f"{where}: date '{day.get('date')}' není platné RRRR-MM-DD")
        if when <= issued:
            fail(
                f"{where}: date {day['date']} není po dni vydání "
                f"({issue_iso}) — do předpovědi patří jen zítřek a dál"
            )
        if when <= previous and idx > 1:
            fail(f"{where}: dny musí jít vzestupně od nejbližšího")
        previous = when
        if day.get("icon") not in WEATHER_ICONS:
            fail(
                f"{where}: icon '{day.get('icon')}' neznám, povolené jsou "
                f"{', '.join(sorted(WEATHER_ICONS))}"
            )
        if not isinstance(day.get("temp_max_c"), (int, float)):
            fail(f"{where}: temp_max_c musí být číslo")
        if "temp_min_c" in day and not isinstance(
            day["temp_min_c"], (int, float)
        ):
            fail(f"{where}: temp_min_c musí být číslo")


def load_digests() -> list[dict]:
    digests = []
    build_time = datetime.now(PRAGUE)
    committed = commit_times()
    changed = changed_files()
    for path in sorted(DIGESTS.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise DigestError(f"{path.name}: nevalidní JSON — {exc}") from exc
        validate(data, path)
        data["_updated"] = updated_at(path, build_time, committed, changed)
        digests.append(data)
    return digests


# ─────────────────────────────  čas aktualizace  ────────────────────────────


def _git(*args: str) -> str | None:
    """Výstup gitu, nebo None když git chybí nebo příkaz selže."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(REPO_ROOT), *args],
            capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout if proc.returncode == 0 else None


def _iso(stamp: str) -> datetime | None:
    try:
        return datetime.fromisoformat(stamp).astimezone(PRAGUE)
    except ValueError:
        return None


def commit_times() -> dict[str, datetime] | None:
    """Čas posledního commitu ke každému digestu, jedním během gitu.

    `git log` vypisuje od nejnovějšího commitu, takže první výskyt cesty
    je ten, který nás zajímá. None znamená, že git není k dispozici.
    """
    out = _git("log", "--format=%x00%cI", "--name-only", "--", str(DIGESTS))
    if out is None:
        return None
    times: dict[str, datetime] = {}
    stamp: datetime | None = None
    for line in out.splitlines():
        if line.startswith("\0"):
            stamp = _iso(line[1:])
        elif line.strip() and stamp and line.strip() not in times:
            times[line.strip()] = stamp
    return times


def changed_files() -> set[str]:
    """Cesty digestů, které se od posledního commitu změnily nebo přibyly."""
    out = _git("status", "--porcelain", "--", str(DIGESTS)) or ""
    paths = set()
    for line in out.splitlines():
        # „XY cesta", u přejmenování „XY stará -> nová".
        path = line[3:].strip().split(" -> ")[-1].strip('"')
        if path:
            paths.add(path)
    return paths


def updated_at(path: Path, build_time: datetime,
               committed: dict[str, datetime] | None,
               changed: set[str]) -> datetime | None:
    """Kdy vydání naposledy vzniklo.

    Rozepsaný nebo ještě necommitnutý digest je ten, který se právě staví
    — u něj platí čas buildu. U ostatních bereme čas posledního commitu
    souboru, takže přegenerování webu starým vydáním datum neposune.
    Bez gitu se čas nedá zjistit a stránka ho neuvádí.
    """
    if committed is None:
        return None
    rel = path.relative_to(REPO_ROOT).as_posix()
    if rel in changed:
        return build_time
    return committed.get(rel)


# ──────────────────────────────────  pomůcky  ───────────────────────────────


def esc(text: str) -> str:
    return html.escape(str(text), quote=True)


def long_date(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{WEEKDAYS[d.weekday()]} {d.day}. {MONTHS[d.month - 1]} {d.year}"


def short_date(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.day}. {d.month}. {d.year}"


def day_month(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.day}. {d.month}."


def updated_note(when: datetime | None, english: bool = False) -> str:
    """Doplněk hlavičkového řádku s časem poslední aktualizace stránky."""
    if when is None:
        return ""
    stamp = esc(when.isoformat(timespec="minutes"))
    czech = (f"{when.day}. {when.month}. {when.year} "
             f"v {when.hour}:{when.minute:02d}")
    note_cs = (f"aktualizováno <time datetime=\"{stamp}\">"
               f"{esc(czech)}</time>")
    english_text = (f"{when.day} {MONTHS_EN[when.month - 1][:3]} {when.year} "
                    f"at {when.hour}:{when.minute:02d}")
    note_en = (f"updated <time datetime=\"{stamp}\">"
               f"{esc(english_text)}</time>")
    return " &nbsp;·&nbsp; " + bi(note_cs, note_en if english else None)


def covered_date(data: dict) -> str:
    """Den, za který přehled je.

    Routina běží v 17:00 a bere 24hodinové okno, takže drtivá většina
    zpráv je z téhož dne — pokrytý den je proto standardně den vydání.
    Pole `covers` to může přepsat u ručního běhu v jinou dobu (třeba
    dopoledne, kdy je většina okna ještě ze včerejška).
    """
    return data.get("covers") or data["date"]


def previous_date(iso: str) -> str:
    return (date.fromisoformat(iso) - timedelta(days=1)).isoformat()


def plural_items(n: int) -> str:
    if n == 1:
        return "1 zpráva"
    if 2 <= n <= 4:
        return f"{n} zprávy"
    return f"{n} zpráv"


def read_id(date_iso: str, item: dict) -> str:
    """Stabilní ID položky pro sledování přečtených zpráv v localStorage."""
    raw = f'{date_iso}|{item["headline"]}|{item["sources"][0]["url"]}'
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def long_date_en(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{WEEKDAYS_EN[d.weekday()]} {d.day} {MONTHS_EN[d.month - 1]} {d.year}"


def short_date_en(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.day} {MONTHS_EN[d.month - 1][:3]} {d.year}"


def day_month_en(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.day} {MONTHS_EN[d.month - 1][:3]}"


def plural_items_en(n: int) -> str:
    return "1 story" if n == 1 else f"{n} stories"


def reading_minutes(data: dict) -> int:
    """Odhad doby čtení; u anglického vydání z anglického textu."""
    if has_english(data):
        words = sum(
            len(i["en"]["headline"].split())
            + sum(len(p["en"].split()) for p in i["en"]["sentences"])
            for i in data["items"]
        )
    else:
        words = sum(
            len(i["headline"].split()) + len(i["body"].split())
            for i in data["items"]
        )
    return max(1, round(words / 160))


# ───────────────────────────  dvojjazyčná sazba  ────────────────────────────
#
# Obě jazykové verze jsou v HTML naráz a přepínač jen mění, která se
# ukazuje — stránka je statická, takže překlad nemá odkud dojet. Chrome
# (nadpisy, data, patička) nese třídy `lang-cs`/`lang-en`, věty zpráv
# `t-cs`/`t-en` uvnitř obalu `.s`, který se dá rozkliknout po jedné větě.


def bi(cs: str, en: str | None, *, tag: str = "span") -> str:
    """Dvojjazyčný kus chrome. Bez angličtiny zůstane jen čeština."""
    if en is None:
        return cs
    return (f'<{tag} class="lang-cs">{cs}</{tag}>'
            f'<{tag} class="lang-en">{en}</{tag}>')


def cambridge_url(term: str) -> str:
    return CAMBRIDGE_SEARCH + urllib.parse.quote(term)


def gloss_span(surface: str, entry: dict) -> str:
    """Slovíčko s vysvětlivkou. Definici i překlad nese v data atributech,
    bublinu z nich skládá až JavaScript."""
    czech = entry.get("cs") or ""
    hint = entry["definition"] + (f" · {czech}" if czech else "")
    return (
        f'<span class="gl" role="button" tabindex="0" '
        f'data-term="{esc(entry["term"])}" '
        f'data-def="{esc(entry["definition"])}" '
        f'data-cs="{esc(czech)}" '
        f'data-url="{esc(cambridge_url(entry["term"]))}" '
        f'aria-label="{esc(surface)} — {esc(hint)}">{esc(surface)}</span>'
    )


def mark_glossary(raw: str, glossary: list[dict], used: set[str]) -> str:
    """Text s vyznačenými slovíčky, jinak zvenčí stejný jako esc().

    Značí se **první** výskyt v položce, aby text nebyl posetý tečkovaným
    podtržením. Escapuje se po kouscích, protože escapování mění délku
    řetězce a posunulo by nalezené pozice.
    """
    if not glossary:
        return esc(raw)
    spans: list[tuple[int, int, dict]] = []
    for entry in glossary:
        key = entry["term"].lower()
        if key in used:
            continue
        match = term_re(entry["term"]).search(raw)
        if not match:
            continue
        if any(match.start() < e and s < match.end() for s, e, _ in spans):
            continue
        spans.append((match.start(), match.end(), entry))
        used.add(key)
    if not spans:
        return esc(raw)
    spans.sort()
    out: list[str] = []
    pos = 0
    for start, end, entry in spans:
        out.append(esc(raw[pos:start]))
        out.append(gloss_span(raw[start:end], entry))
        pos = end
    out.append(esc(raw[pos:]))
    return "".join(out)


def sentence_span(cs: str, en_html: str) -> str:
    """Jedna věta v obou jazycích. Kliknutím se ukáže i ta druhá."""
    return (f'<span class="s" tabindex="0" role="button">'
            f'<span class="t-en">{en_html}</span>'
            f'<span class="t-cs">{esc(cs)}</span></span>')


def item_headline(item: dict, used: set[str]) -> str:
    en = item.get("en")
    if not en:
        return esc(item["headline"])
    marked = mark_glossary(en["headline"], en.get("glossary") or [], used)
    return sentence_span(item["headline"], marked)


def item_body(item: dict, used: set[str]) -> str:
    """Tělo zprávy: anglicky po větách, k tomu celý český odstavec."""
    en = item.get("en")
    if not en:
        return f'<p class="body">{esc(item["body"])}</p>'
    glossary = en.get("glossary") or []
    sentences = " ".join(
        sentence_span(pair["cs"], mark_glossary(pair["en"], glossary, used))
        for pair in en["sentences"]
    )
    return (f'<p class="body en">{sentences}</p>\n'
            f'<p class="body cs-full">{esc(item["body"])}</p>')


def collect_vocabulary(items: list[dict]) -> list[dict]:
    """Slovíčka celého vydání v pořadí, v jakém se ve zprávách objeví."""
    seen: set[str] = set()
    words: list[dict] = []
    for item in items:
        for entry in (item.get("en") or {}).get("glossary") or []:
            key = entry["term"].lower()
            if key in seen:
                continue
            seen.add(key)
            words.append(entry)
    return words


# ────────────────────────────────────  CSS  ─────────────────────────────────

CSS = """
/* Novinová sazba, varianta „Vydání": hlavní zpráva dne jako otvírák pod
   hlavičkou, klidný serif pro text, sans pro metadata a navigaci. Světlé
   téma je barva novinového papíru, tmavé je ztlumená varianta pro čtení
   večer. Přepínač zapisuje data-theme na <html>, jinak rozhoduje systém. */

:root {
  --paper: #f7f3ea;
  --paper-raised: #fdfaf3;
  --ink: #221f19;
  --ink-muted: #736a58;
  --rule: #ddd4c2;
  --rule-strong: #221f19;
  --accent: #93321f;
  --serif: "Iowan Old Style", "Palatino Linotype", Palatino, Georgia,
           "Times New Roman", "Times", serif;
  --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
          "Helvetica Neue", Arial, sans-serif;
}

@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --paper: #181712;
    --paper-raised: #201e18;
    --ink: #e8e2d4;
    --ink-muted: #9c9484;
    --rule: #37342b;
    --rule-strong: #7a7260;
    --accent: #d98d75;
  }
}

:root[data-theme="dark"] {
  --paper: #181712;
  --paper-raised: #201e18;
  --ink: #e8e2d4;
  --ink-muted: #9c9484;
  --rule: #37342b;
  --rule-strong: #7a7260;
  --accent: #d98d75;
}

* { box-sizing: border-box; }

html { -webkit-text-size-adjust: 100%; }

body {
  margin: 0;
  padding: 0 1.4rem 4.5rem;
  background: var(--paper);
  color: var(--ink);
  font-family: var(--serif);
  font-size: clamp(1rem, 0.97rem + 0.15vw, 1.075rem);
  line-height: 1.62;
  text-rendering: optimizeLegibility;
  -webkit-font-smoothing: antialiased;
}

.wrap { max-width: 44rem; margin: 0 auto; }

/* ── hlavička ─────────────────────────────────────────────────────────── */

.masthead { padding-top: 2.6rem; text-align: center; }

.masthead h1 {
  margin: 0;
  font-size: clamp(2.1rem, 1.4rem + 3.2vw, 3.1rem);
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  line-height: 1.05;
}

.masthead h1 a { color: inherit; text-decoration: none; }

/* Pokrytý den — jediný podtitulek hlavičky. */
.masthead .dateline {
  margin: 0.7rem 0 0;
  font-family: var(--sans);
  font-size: 0.78rem;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--ink-muted);
}

.rule-double {
  margin: 1.05rem 0 0;
  border: 0;
  border-top: 3px solid var(--rule-strong);
  border-bottom: 1px solid var(--rule-strong);
  height: 4px;
}

.meta {
  margin: 0.7rem 0 0;
  font-family: var(--sans);
  font-size: 0.76rem;
  letter-spacing: 0.04em;
  color: var(--ink-muted);
  text-align: center;
}

.issues {
  margin: 0.45rem 0 0;
  font-family: var(--sans);
  font-size: 0.76rem;
  letter-spacing: 0.04em;
  color: var(--ink-muted);
  text-align: center;
}

.issues a { color: var(--ink-muted); text-decoration: none;
  border-bottom: 1px dotted currentColor; padding-bottom: 1px; }
.issues a:hover, .issues a:focus { color: var(--accent); }
.issues .sep { padding: 0 0.35rem; opacity: 0.6; }

/* ── počasí ───────────────────────────────────────────────────────────── */

.weather {
  margin: 1.9rem 0 0;
  padding: 0.95rem 1.15rem;
  background: var(--paper-raised);
  border: 1px solid var(--rule);
}

.weather .kicker {
  margin: 0 0 0.4rem;
  font-family: var(--sans);
  font-size: 0.7rem;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--ink-muted);
  font-weight: 700;
}

/* Servisní box, ne článek — celý stojí na bezpatkovém písmu jako kicker
   a proužek pod ním. */
.weather p {
  margin: 0;
  font-family: var(--sans);
  font-size: 0.9rem;
  line-height: 1.5;
}

/* Výhled odděluje jen zalomení řádku, sazbu má shodnou se shrnutím. */
.weather .outlook { margin-top: 0.3rem; }

/* Proužek dalších dnů: ikona, den a denní/noční teplota vedle sebe.
   Na úzkém displeji se vodorovně odroluje místo zalomení. */
.weather .w-days {
  display: flex;
  gap: 0.4rem;
  margin: 0.95rem 0 0;
  padding: 0.85rem 0 0;
  border-top: 1px solid var(--rule);
  list-style: none;
  overflow-x: auto;
}

.weather .w-days li {
  flex: 1 1 0;
  min-width: 4.1rem;
  text-align: center;
  font-family: var(--sans);
}

.weather .w-days .w-when {
  display: block;
  font-size: 0.71rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--ink-muted);
}

.weather .w-days .w-mark {
  display: block;
  margin: 0.3rem 0 0.25rem;
  color: var(--accent);
}

.weather .w-days .w-mark svg {
  width: 1.75rem;
  height: 1.75rem;
  display: inline-block;
}

.weather .w-days .w-temp {
  display: block;
  font-size: 0.83rem;
  font-variant-numeric: tabular-nums;
  font-weight: 700;
}

.weather .w-days .w-temp .low {
  font-weight: 400;
  color: var(--ink-muted);
}

/* ── otvírák ──────────────────────────────────────────────────────────── */

.opener {
  margin: 2.2rem 0 0;
  padding-bottom: 1.9rem;
  border-bottom: 1px solid var(--rule);
}

.opener .kicker {
  margin: 0;
  font-family: var(--sans);
  font-size: 0.72rem;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--accent);
  font-weight: 700;
}

.opener h2 {
  margin: 0.5rem 0 0.7rem;
  font-size: clamp(1.5rem, 1.2rem + 1.6vw, 2rem);
  line-height: 1.22;
  font-weight: 700;
  letter-spacing: -0.005em;
}

.opener p { margin: 0; font-size: 1.06rem; }

.opener .sources { margin-top: 0.7rem; font-size: 0.75rem; }
.opener .sources a { border-bottom-color: transparent; }
.opener .sources a:hover, .opener .sources a:focus {
  border-bottom-color: currentColor;
}

/* ── rubriky a položky ────────────────────────────────────────────────── */

.rubric { margin: 2.8rem 0 0; }

.rubric > h2 {
  margin: 0 0 0.2rem;
  padding-bottom: 0.45rem;
  border-bottom: 2px solid var(--rule-strong);
  font-family: var(--sans);
  font-size: 0.8rem;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  font-weight: 700;
}

article {
  padding: 1.35rem 0;
  border-bottom: 1px solid var(--rule);
}

article:last-child { border-bottom: 0; }

.stamp {
  display: block;
  margin-bottom: 0.35rem;
  font-family: var(--sans);
  font-size: 0.72rem;
  letter-spacing: 0.1em;
  color: var(--ink-muted);
  font-variant-numeric: tabular-nums;
}

.stamp .flag { color: var(--accent); font-weight: 600; }

article h3 {
  margin: 0 0 0.45rem;
  font-size: 1.22rem;
  line-height: 1.32;
  font-weight: 700;
}

article p { margin: 0; }

.sources {
  margin-top: 0.6rem;
  font-family: var(--sans);
  font-size: 0.78rem;
  color: var(--ink-muted);
}

.sources a {
  color: var(--ink-muted);
  text-decoration: none;
  border-bottom: 1px dotted currentColor;
  padding-bottom: 1px;
}

.sources a:hover, .sources a:focus { color: var(--accent); }

.sources .sep { padding: 0 0.35rem; opacity: 0.6; }

/* ── přečtené zprávy ──────────────────────────────────────────────────── */

[data-read-id] { cursor: pointer; }

[data-read-id].read h2,
[data-read-id].read h3,
[data-read-id].read p { opacity: 0.42; }

/* Značka „přečteno" je element, ne ::after — v hlavičce zprávy stojí
   před tlačítky, která jsou odsunutá doprava. */
.read-mark { display: none; font-weight: 400; color: var(--ink-muted); }
[data-read-id].read .read-mark { display: inline; }

/* ── navigace a patička ───────────────────────────────────────────────── */

.pager {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem 1.5rem;
  justify-content: space-between;
  margin-top: 3rem;
  padding-top: 1.1rem;
  border-top: 1px solid var(--rule);
  font-family: var(--sans);
  font-size: 0.84rem;
}

.pager a { color: var(--accent); text-decoration: none; }
.pager a:hover { text-decoration: underline; }

footer {
  margin-top: 2.5rem;
  padding-top: 1.1rem;
  border-top: 3px double var(--rule-strong);
  font-family: var(--sans);
  font-size: 0.76rem;
  color: var(--ink-muted);
}

footer p { margin: 0.35rem 0; }
footer .used { line-height: 1.5; }
footer .warn { font-style: italic; }
footer a { color: var(--accent); }

/* ── přepínač témat ───────────────────────────────────────────────────── */

.theme-toggle {
  position: fixed;
  top: 0.85rem;
  right: 0.85rem;
  z-index: 10;
  width: 2.3rem;
  height: 2.3rem;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  background: var(--paper-raised);
  color: var(--ink-muted);
  border: 1px solid var(--rule);
  border-radius: 50%;
  cursor: pointer;
}

.theme-toggle svg { width: 1.05rem; height: 1.05rem; display: block; }

.theme-toggle:hover { color: var(--ink); border-color: var(--rule-strong); }

/* ── archiv ───────────────────────────────────────────────────────────── */

.archive { margin: 2.4rem 0 0; list-style: none; padding: 0; }

.archive li {
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem 0.75rem;
  align-items: baseline;
  padding: 0.75rem 0;
  border-bottom: 1px solid var(--rule);
}

.archive a { color: var(--ink); text-decoration: none; font-weight: 700; }
.archive a:hover { color: var(--accent); }
.archive .count {
  font-family: var(--sans);
  font-size: 0.78rem;
  color: var(--ink-muted);
}

/* ── mobil ────────────────────────────────────────────────────────────── */

@media (max-width: 34rem) {
  body { padding: 0 1rem 3rem; line-height: 1.58; }
  .masthead { padding-top: 3.25rem; }
  .masthead h1 { letter-spacing: 0.03em; }
  .opener h2 { font-size: 1.45rem; }
  .rubric { margin-top: 2.3rem; }
  article h3 { font-size: 1.14rem; }
  .pager { flex-direction: column; }
  .lang-switch { top: 0.7rem; right: 3.2rem; }
  .lang-switch button { padding: 0.2rem 0.4rem; font-size: 0.64rem; }
  .theme-toggle { top: 0.7rem; width: 2.1rem; height: 2.1rem; }
  .vocab li { grid-template-columns: 1fr; gap: 0.1rem; }
}

/* ── dvě jazykové verze ───────────────────────────────────────────────────
   Obě jsou v HTML naráz, přepínač jen mění, co je vidět. Výchozí je
   angličtina, takže bez atributu data-lang platí anglická sazba.
   Režimy: „en" (anglicky), „both" (věta pod větou), „cs" (česky).       */

:root:not([data-lang="cs"]) .lang-cs { display: none; }
:root[data-lang="cs"] .lang-en { display: none; }

/* Věta zprávy: v angličtině se dá rozkliknout a ukázat český protějšek. */
.s { cursor: pointer; }
.s > .t-cs { display: none; }

:root[data-lang="cs"] .s > .t-en { display: none; }
:root[data-lang="cs"] .s > .t-cs { display: inline; }

.s:hover > .t-en, .s:focus-visible > .t-en,
:root[data-lang="cs"] .s:hover > .t-cs,
:root[data-lang="cs"] .s:focus-visible > .t-cs {
  background: color-mix(in srgb, var(--accent) 7%, transparent);
  border-radius: 2px;
}

/* V souběžném čtení je věta oddělená sama o sobě, zvýraznění by rušilo. */
:root[data-lang="both"] .s:hover > .t-en,
:root[data-lang="en"] .bi .s:hover > .t-en { background: none; }

.s:focus { outline: none; }
.s:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

/* Jedna rozkliknutá věta: překlad hned za ní, kurzívou a ztlumeně. */
:root[data-lang="en"] .s.open > .t-cs {
  display: inline;
  color: var(--ink-muted);
  font-style: italic;
}

:root[data-lang="en"] .s.open > .t-cs::before {
  content: "↳\\00a0";
  font-style: normal;
  opacity: 0.65;
  margin-left: 0.3em;
}

/* Souběžné čtení: každá věta na svém řádku, překlad pod ní. Platí pro
   celý web v režimu „both" a pro jednotlivou zprávu přepnutou tlačítkem. */
:root[data-lang="both"] .s,
:root[data-lang="en"] .bi .s {
  display: block;
  margin: 0 0 0.55rem;
}

:root[data-lang="both"] .s > .t-cs,
:root[data-lang="en"] .bi .s > .t-cs {
  display: block;
  color: var(--ink-muted);
  font-style: italic;
  font-size: 0.94em;
  padding-left: 0.7rem;
  border-left: 2px solid var(--rule);
}

:root[data-lang="both"] .s.open > .t-cs::before,
:root[data-lang="en"] .bi .s.open > .t-cs::before { content: none; }

/* Celý český odstavec je jen pro čistě českou verzi — v obou anglických
   režimech češtinu nesou už samotné věty. */
.body.cs-full { display: none; }
:root[data-lang="cs"] .body.cs-full { display: block; }
:root[data-lang="cs"] .body.en { display: none; }

/* ── vysvětlivky slovíček ─────────────────────────────────────────────── */

.gl {
  border-bottom: 1px dotted var(--accent);
  cursor: help;
  text-decoration: none;
}

.gl:hover, .gl[aria-expanded="true"] {
  background: color-mix(in srgb, var(--accent) 15%, transparent);
}

.gl:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

.gloss-pop {
  position: absolute;
  z-index: 40;
  max-width: min(22rem, calc(100vw - 2rem));
  padding: 0.7rem 0.85rem;
  background: var(--paper-raised);
  border: 1px solid var(--rule-strong);
  box-shadow: 0 6px 24px rgba(0, 0, 0, 0.18);
  font-family: var(--sans);
  font-size: 0.83rem;
  line-height: 1.45;
}

.gloss-pop p { margin: 0; }

.gloss-pop .term {
  font-weight: 700;
  letter-spacing: 0.02em;
}

.gloss-pop .def { margin: 0.25rem 0 0; }

.gloss-pop .cz {
  margin: 0.3rem 0 0;
  color: var(--ink-muted);
  font-style: italic;
}

.gloss-pop .more {
  display: inline-block;
  margin-top: 0.45rem;
  color: var(--accent);
  text-decoration: none;
  border-bottom: 1px solid currentColor;
  font-size: 0.78rem;
}

/* ── ovládání jazyka ──────────────────────────────────────────────────── */

.lang-switch {
  position: fixed;
  top: 0.85rem;
  right: 3.6rem;
  z-index: 10;
  display: flex;
  padding: 2px;
  background: var(--paper-raised);
  border: 1px solid var(--rule);
  border-radius: 999px;
  font-family: var(--sans);
}

.lang-switch button {
  padding: 0.24rem 0.55rem;
  border: 0;
  border-radius: 999px;
  background: none;
  color: var(--ink-muted);
  font: inherit;
  font-size: 0.7rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  cursor: pointer;
}

.lang-switch button:hover { color: var(--ink); }

.lang-switch button[aria-pressed="true"] {
  background: var(--rule-strong);
  color: var(--paper);
}

/* Nápověda pod hlavičkou — bez ní se o klikacích větách nikdo nedozví. */
.hint {
  margin: 0.5rem 0 0;
  font-family: var(--sans);
  font-size: 0.74rem;
  line-height: 1.5;
  color: var(--ink-muted);
  text-align: center;
}

.hint b { font-weight: 600; color: var(--ink); }

/* ── tlačítka u zprávy ────────────────────────────────────────────────── */

.stamp { display: flex; align-items: baseline; gap: 0.5rem; }
.stamp .grow { flex: 1 1 auto; }

.tool {
  padding: 0.1rem 0.4rem;
  border: 1px solid var(--rule);
  border-radius: 3px;
  background: none;
  color: var(--ink-muted);
  font-family: var(--sans);
  font-size: 0.66rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  line-height: 1.5;
  cursor: pointer;
}

.tool:hover { color: var(--accent); border-color: var(--accent); }
.tool[aria-pressed="true"] { color: var(--paper); background: var(--rule-strong);
  border-color: var(--rule-strong); }

:root[data-lang="both"] .tool.tool-cs,
:root[data-lang="cs"] .tool.tool-cs { display: none; }

/* ── shrnutí dne ──────────────────────────────────────────────────────── */

.lead {
  margin: 2rem 0 0;
  padding: 1rem 1.15rem 1.05rem;
  border-top: 3px solid var(--rule-strong);
  border-bottom: 1px solid var(--rule);
  background: var(--paper-raised);
}

.lead .kicker {
  margin: 0 0 0.5rem;
  font-family: var(--sans);
  font-size: 0.7rem;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--accent);
  font-weight: 700;
}

.lead ul { margin: 0; padding-left: 1.05rem; }
.lead li { margin: 0 0 0.4rem; }
.lead li:last-child { margin-bottom: 0; }

/* ── slovníček vydání ─────────────────────────────────────────────────── */

.vocab { margin: 2.8rem 0 0; }

.vocab > h2 {
  margin: 0 0 0.2rem;
  padding-bottom: 0.45rem;
  border-bottom: 2px solid var(--rule-strong);
  font-family: var(--sans);
  font-size: 0.8rem;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  font-weight: 700;
}

.vocab ul { margin: 0; padding: 0; list-style: none; }

.vocab li {
  display: grid;
  grid-template-columns: minmax(6rem, 9rem) 1fr auto;
  gap: 0.2rem 0.9rem;
  align-items: baseline;
  padding: 0.6rem 0;
  border-bottom: 1px solid var(--rule);
  font-family: var(--sans);
  font-size: 0.86rem;
  line-height: 1.5;
}

.vocab li:last-child { border-bottom: 0; }
.vocab .term { font-weight: 700; font-size: 0.95rem; }
.vocab .cz { color: var(--ink-muted); font-style: italic; }
.vocab .more {
  color: var(--accent);
  text-decoration: none;
  font-size: 0.76rem;
  white-space: nowrap;
}
.vocab .more:hover { text-decoration: underline; }

@media print {
  .theme-toggle, .pager, .issues, .lang-switch, .tool, .hint { display: none; }
  body { background: #fff; color: #000; }
  .s > .t-cs, .body.cs-full { display: none; }
}
"""

THEME_JS = """
/* Jazyk stránky. Výchozí je angličtina, protože web se čte kvůli učení;
   „both" staví větu pod větu, „cs" ukazuje původní české znění. Volba se
   pamatuje, ale na starší česká vydání se neaplikuje — ta angličtinu
   nemají a přepínač na nich není. */
(function () {
  var root = document.documentElement;
  var MODES = { en: 1, both: 1, cs: 1 };
  var HTML_LANG = { en: 'en', both: 'en', cs: 'cs' };

  function apply(mode) {
    root.setAttribute('data-lang', mode);
    root.setAttribute('lang', HTML_LANG[mode]);
  }

  var stored = null;
  try { stored = localStorage.getItem('lang'); } catch (e) {}
  if (root.getAttribute('data-has-en') === '1' && MODES[stored]) apply(stored);

  document.addEventListener('DOMContentLoaded', function () {
    var box = document.querySelector('.lang-switch');
    if (!box) return;
    var btns = box.querySelectorAll('button[data-mode]');
    function sync() {
      var now = root.getAttribute('data-lang') || 'en';
      Array.prototype.forEach.call(btns, function (b) {
        b.setAttribute('aria-pressed',
          b.getAttribute('data-mode') === now ? 'true' : 'false');
      });
    }
    sync();
    Array.prototype.forEach.call(btns, function (b) {
      b.addEventListener('click', function () {
        apply(b.getAttribute('data-mode'));
        try { localStorage.setItem('lang', b.getAttribute('data-mode')); }
        catch (e) {}
        sync();
      });
    });
  });
})();

(function () {
  var root = document.documentElement;
  var stored = null;
  try { stored = localStorage.getItem('theme'); } catch (e) {}
  if (stored === 'dark' || stored === 'light') root.setAttribute('data-theme', stored);

  var SVG_ATTRS = 'xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" ' +
    'fill="none" stroke="currentColor" stroke-width="2" ' +
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"';
  var SUN = '<svg ' + SVG_ATTRS + '><circle cx="12" cy="12" r="4"/>' +
    '<path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41' +
    'M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>';
  var MOON = '<svg ' + SVG_ATTRS + '>' +
    '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';

  document.addEventListener('DOMContentLoaded', function () {
    var btn = document.querySelector('.theme-toggle');
    if (!btn) return;
    function isDark() {
      return root.getAttribute('data-theme') === 'dark' ||
        (!root.getAttribute('data-theme') &&
         window.matchMedia('(prefers-color-scheme: dark)').matches);
    }
    function label() {
      var dark = isDark();
      btn.innerHTML = dark ? SUN : MOON;
      var text = dark ? 'Přepnout na světlý režim' : 'Přepnout na tmavý režim';
      btn.setAttribute('aria-label', text);
      btn.setAttribute('title', text);
      btn.setAttribute('aria-pressed', dark ? 'true' : 'false');
    }
    label();
    btn.addEventListener('click', function () {
      var next = isDark() ? 'light' : 'dark';
      root.setAttribute('data-theme', next);
      try { localStorage.setItem('theme', next); } catch (e) {}
      label();
    });
  });
})();

/* Přečtené zprávy: klik na zprávu ji označí (a odznačí), stejně tak
   tlačítko v hlavičce zprávy; klik na odkaz ji označí a nechá odkaz
   normálně otevřít. Klikání na věty a slovíčka se do označování neplete.
   Stav žije v localStorage, záznamy starší 90 dnů se promazávají. */
(function () {
  var KEY = 'readItems';
  var MAX_AGE_MS = 90 * 24 * 60 * 60 * 1000;

  function load() {
    try { return JSON.parse(localStorage.getItem(KEY)) || {}; }
    catch (e) { return {}; }
  }
  function save(map) {
    try { localStorage.setItem(KEY, JSON.stringify(map)); } catch (e) {}
  }

  document.addEventListener('DOMContentLoaded', function () {
    var map = load();
    var now = Date.now();
    var changed = false;
    for (var k in map) {
      if (now - map[k] > MAX_AGE_MS) { delete map[k]; changed = true; }
    }
    if (changed) save(map);

    Array.prototype.forEach.call(
      document.querySelectorAll('[data-read-id]'),
      function (el) {
        var id = el.getAttribute('data-read-id');
        var btn = el.querySelector('.tool-read');
        if (map[id]) el.classList.add('read');

        function sync() {
          if (btn) {
            btn.setAttribute('aria-pressed',
              el.classList.contains('read') ? 'true' : 'false');
          }
        }
        function mark() {
          if (!map[id]) { map[id] = Date.now(); el.classList.add('read'); save(map); }
          sync();
        }
        function toggle() {
          if (el.classList.toggle('read')) map[id] = Date.now();
          else delete map[id];
          save(map);
          sync();
        }
        sync();

        if (btn) {
          btn.addEventListener('click', function (ev) {
            ev.stopPropagation();
            toggle();
          });
        }

        el.addEventListener('click', function (ev) {
          // Věty, slovíčka a tlačítka mají vlastní význam kliknutí.
          if (ev.target.closest('.s, .gl, .tool')) return;
          if (ev.target.closest('a')) {
            // Otevření zdroje počítáme jako přečtení, ale neodznačujeme.
            mark();
            return;
          }
          // Výběr textu (např. kvůli kopírování) přečtení nepřepíná.
          if (window.getSelection && String(window.getSelection())) return;
          toggle();
        });
      }
    );
  });
})();

/* Srovnání s češtinou: klik na větu ukáže její překlad, tlačítko „CS"
   v hlavičce zprávy přepne na souběžné čtení celé zprávy. */
(function () {
  function selecting() {
    return !!(window.getSelection && String(window.getSelection()));
  }

  document.addEventListener('DOMContentLoaded', function () {
    Array.prototype.forEach.call(
      document.querySelectorAll('.s'),
      function (s) {
        s.addEventListener('click', function (ev) {
          ev.stopPropagation();
          if (selecting()) return;
          s.classList.toggle('open');
        });
        s.addEventListener('keydown', function (ev) {
          if (ev.key !== 'Enter' && ev.key !== ' ') return;
          ev.preventDefault();
          ev.stopPropagation();
          s.classList.toggle('open');
        });
      }
    );

    Array.prototype.forEach.call(
      document.querySelectorAll('.tool-cs'),
      function (btn) {
        var box = btn.closest('[data-read-id]');
        btn.addEventListener('click', function (ev) {
          ev.stopPropagation();
          if (!box) return;
          var on = box.classList.toggle('bi');
          btn.setAttribute('aria-pressed', on ? 'true' : 'false');
        });
      }
    );
  });
})();

/* Vysvětlivky slovíček. Bublina se skládá až tady, aby v HTML nebyla
   u každého slova schovaná kopie definice. */
(function () {
  var pop = null;
  var owner = null;

  function close() {
    if (pop) { pop.parentNode.removeChild(pop); pop = null; }
    if (owner) { owner.setAttribute('aria-expanded', 'false'); owner = null; }
  }

  function line(cls, text) {
    var el = document.createElement('p');
    el.className = cls;
    el.textContent = text;
    return el;
  }

  function place(el) {
    var box = el.getBoundingClientRect();
    pop.style.left = '0px';
    pop.style.top = (box.bottom + window.scrollY + 6) + 'px';
    var width = pop.offsetWidth;
    var limit = document.documentElement.clientWidth - 10;
    var left = box.left + window.scrollX;
    if (left + width > limit) left = Math.max(10, limit - width);
    pop.style.left = left + 'px';
  }

  function open(el) {
    var again = owner === el;
    close();
    if (again) return;
    pop = document.createElement('div');
    pop.className = 'gloss-pop';
    pop.setAttribute('role', 'dialog');
    pop.appendChild(line('term', el.getAttribute('data-term')));
    pop.appendChild(line('def', el.getAttribute('data-def')));
    if (el.getAttribute('data-cs')) {
      pop.appendChild(line('cz', el.getAttribute('data-cs')));
    }
    var more = document.createElement('a');
    more.className = 'more';
    more.href = el.getAttribute('data-url');
    more.target = '_blank';
    more.rel = 'noopener noreferrer';
    more.textContent = 'Cambridge Dictionary \u2197';
    pop.appendChild(more);
    document.body.appendChild(pop);
    owner = el;
    el.setAttribute('aria-expanded', 'true');
    place(el);
  }

  document.addEventListener('DOMContentLoaded', function () {
    Array.prototype.forEach.call(
      document.querySelectorAll('.gl'),
      function (el) {
        el.setAttribute('aria-expanded', 'false');
        el.addEventListener('click', function (ev) {
          ev.stopPropagation();
          open(el);
        });
        el.addEventListener('keydown', function (ev) {
          if (ev.key !== 'Enter' && ev.key !== ' ') return;
          ev.preventDefault();
          ev.stopPropagation();
          open(el);
        });
      }
    );

    document.addEventListener('click', function (ev) {
      if (!pop || ev.target.closest('.gloss-pop')) return;
      close();
    });
    document.addEventListener('keydown', function (ev) {
      if (ev.key === 'Escape') close();
    });
    window.addEventListener('resize', close);
  });
})();
"""


# ──────────────────────────────────  šablony  ───────────────────────────────


LANG_SWITCH = """<div class="lang-switch" role="group" aria-label="Language">
<button type="button" data-mode="en" title="English only">EN</button>
<button type="button" data-mode="both" title="English with Czech under \
each sentence">EN+CS</button>
<button type="button" data-mode="cs" title="Jen česky">CS</button>
</div>"""


def page(title: str, body: str, *, depth_prefix: str = "",
         has_en: bool = False) -> str:
    """Kostra stránky.

    Výchozí jazyk je angličtina, ale jen tam, kde ji vydání má. Starší
    česká vydání se otevřou česky a přepínač na nich není — přepínat by
    bylo na co jen naoko.
    """
    lang = "en" if has_en else "cs"
    switch = f"\n{LANG_SWITCH}" if has_en else ""
    description = SITE_DESCRIPTION_EN if has_en else SITE_DESCRIPTION
    return f"""<!DOCTYPE html>
<html lang="{lang}" data-lang="{lang}" data-has-en="{'1' if has_en else '0'}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="color-scheme" content="light dark">
<meta name="description" content="{esc(description)}">
<link rel="stylesheet" href="{depth_prefix}assets/style.css">
<script>{THEME_JS}</script>
</head>
<body>
<button class="theme-toggle" type="button" aria-label="Přepnout tmavý režim"></button>\
{switch}
<div class="wrap">
{body}
</div>
</body>
</html>
"""


def render_sources(sources: list[dict]) -> str:
    # Odkazy vedou na cizí weby, takže otvírají nový panel — čtenář tím
    # neztratí rozečtené vydání.
    links = [
        f'<a href="{esc(s["url"])}" target="_blank" '
        f'rel="noopener noreferrer">{esc(s["name"])}</a>'
        for s in sources
    ]
    return '<span class="sep">·</span>'.join(links)


def cross_flag(item: dict) -> str:
    if not item.get("cross_source"):
        return ""
    n = len(item["sources"])
    czech = f"{n} zdroje" if n < 5 else f"{n} zdrojů"
    return bi(esc(czech), esc(f"{n} sources"))


def stamp_text(item: dict, prev_date: str) -> str:
    """Čas vydání; u zpráv z večera předchozího dne i s datem.

    Vydání vzniká v 17:00 a bere 24 hodin zpět, takže většina položek je
    z pokrytého dne, kterým se datuje celý web — tam samotný čas nic
    nezamlžuje. Zbytek okna je večer předchozího dne; ty dostanou datum
    před čas, aby se nepletly s dneškem.
    """
    if item.get("day") != "prev":
        return esc(item["time"])
    return bi(esc(f'{day_month(prev_date)} {item["time"]}'),
              esc(f'{day_month_en(prev_date)} {item["time"]}'))


READ_MARK = ('<span class="read-mark">· '
             + bi("přečteno ✓", "read ✓") + "</span>")


def item_tools(has_en: bool) -> str:
    """Tlačítka v hlavičce zprávy: souběžná čeština a značka „přečteno"."""
    tools = []
    if has_en:
        tools.append(
            '<button class="tool tool-cs" type="button" aria-pressed="false" '
            'title="Show the Czech original sentence by sentence">CS</button>'
        )
    tools.append(
        '<button class="tool tool-read" type="button" aria-pressed="false" '
        + f'title="{esc("Mark as read / Označit jako přečtené")}">✓</button>'
    )
    return "".join(tools)


def render_item(item: dict, rid: str, prev_date: str) -> str:
    used: set[str] = set()
    flag = cross_flag(item)
    flag_html = f'<span class="flag">· {flag}</span>' if flag else ""
    return f"""<article data-read-id="{rid}">
<span class="stamp">{stamp_text(item, prev_date)}{flag_html}\
{READ_MARK}<span class="grow"></span>{item_tools(bool(item.get("en")))}</span>
<h3>{item_headline(item, used)}</h3>
{item_body(item, used)}
<p class="sources">{render_sources(item["sources"])}</p>
</article>"""


def render_opener(item: dict, rid: str, prev_date: str) -> str:
    used: set[str] = set()
    flag = cross_flag(item)
    rubric = bi(esc(item["rubric"]), esc(RUBRIC_EN[item["rubric"]])
                if item.get("en") else None)
    kicker = f'{rubric} · {stamp_text(item, prev_date)}'
    if flag:
        kicker += f" · {flag}"
    return f"""<section class="opener" data-read-id="{rid}">
<p class="kicker stamp">{kicker}{READ_MARK}<span class="grow"></span>\
{item_tools(bool(item.get("en")))}</p>
<h2>{item_headline(item, used)}</h2>
{item_body(item, used)}
<p class="sources">{render_sources(item["sources"])}</p>
</section>"""


# Čárové ikony počasí (Lucide, licence ISC), stroke dědí currentColor.
_W_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
          'fill="none" stroke="currentColor" stroke-width="1.7" '
          'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">')

WEATHER_ICONS = {
    "clear": (
        '<circle cx="12" cy="12" r="4"/>'
        '<path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41'
        'M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/>'
    ),
    "partly": (
        '<path d="M12 2v2"/><path d="m4.93 4.93 1.41 1.41"/>'
        '<path d="M20 12h2"/><path d="m19.07 4.93-1.41 1.41"/>'
        '<path d="M15.947 12.65a4 4 0 0 0-5.925-4.128"/>'
        '<path d="M13 22H7a5 5 0 1 1 4.9-6H13a3 3 0 0 1 0 6Z"/>'
    ),
    "cloudy": '<path d="M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z"/>',
    "fog": (
        '<path d="M4 14.899A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 2.5 8.242"/>'
        '<path d="M16 17H7"/><path d="M17 21H9"/>'
    ),
    "rain": (
        '<path d="M4 14.899A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 2.5 8.242"/>'
        '<path d="M16 14v6"/><path d="M8 14v6"/><path d="M12 16v6"/>'
    ),
    "snow": (
        '<path d="M4 14.899A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 2.5 8.242"/>'
        '<path d="M8 15h.01"/><path d="M8 19h.01"/><path d="M12 17h.01"/>'
        '<path d="M12 21h.01"/><path d="M16 15h.01"/><path d="M16 19h.01"/>'
    ),
    "storm": (
        '<path d="M6 16.326A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 .5 8.973"/>'
        '<path d="m13 12-3 5h4l-3 5"/>'
    ),
}


def weather_icon_svg(name: str) -> str:
    return f'{_W_SVG}{WEATHER_ICONS[name]}</svg>'


def relative_day(target_iso: str, issue_iso: str) -> str:
    """Jak se o dni mluví vzhledem ke dni vydání."""
    offset = (date.fromisoformat(target_iso)
              - date.fromisoformat(issue_iso)).days
    if offset in (0, 1, 2):
        return ("dnes", "zítra", "pozítří")[offset]
    return WEEKDAYS[date.fromisoformat(target_iso).weekday()]


def relative_day_en(target_iso: str, issue_iso: str) -> str:
    """Totéž anglicky. Dál než na zítřek se den jmenuje zkratkou, aby se
    proužek předpovědi vešel i na mobil."""
    offset = (date.fromisoformat(target_iso)
              - date.fromisoformat(issue_iso)).days
    if offset in (0, 1):
        return ("today", "tomorrow")[offset]
    return WEEKDAYS_EN[date.fromisoformat(target_iso).weekday()][:3]


def temp(value) -> str:
    return f"{round(value)}°"


def render_weather_days(days: list[dict], issue_date: str,
                        english: bool) -> str:
    """Proužek předpovědi pod textem počasí.

    Nese celé pole `days`, tedy zítřek i dny po něm — je to jediné místo,
    kde se ikony počasí ukazují. Starší digesty žádné `days` nemají, u nich
    se proužek vůbec nevykreslí.
    """
    if not days:
        return ""
    cells = []
    for day in days:
        low = ""
        if day.get("temp_min_c") is not None:
            low = f' <span class="low">{esc(temp(day["temp_min_c"]))}</span>'
        when = bi(
            esc(relative_day(day["date"], issue_date)),
            esc(relative_day_en(day["date"], issue_date)) if english else None,
        )
        cells.append(
            f'<li><span class="w-when">{when}</span>'
            f'<span class="w-mark">{weather_icon_svg(day["icon"])}</span>'
            f'<span class="w-temp">{esc(temp(day["temp_max_c"]))}{low}'
            f'</span></li>'
        )
    return f'\n<ul class="w-days">\n{chr(10).join(cells)}\n</ul>'


def render_weather(weather: dict, issue_date: str, english: bool) -> str:
    """Počasí v digestu je předpověď na zítřek a další dny.

    Vydání vychází v 17:00, kdy je dnešní počasí čtenáři dávno známé —
    užitečná je až předpověď dopředu. Text shrne zítřek, proužek pod ním
    ukáže zítřek i zbývající dny v ikonách.
    """
    place = weather.get("place") or "Hradec Králové"
    days = weather.get("days") or []

    # Výhled stojí na vlastním řádku, ale sází se stejně jako shrnutí nad
    # ním — odlišuje ho jen zalomení, ne písmo.
    outlook = ""
    if weather.get("outlook"):
        text = bi(esc(weather["outlook"]),
                  esc(weather["outlook_en"]) if english else None)
        outlook = f'\n<p class="outlook">{text}</p>'

    if days:
        # Konkrétní den nese proužek, kicker tedy jen uvozuje rubriku.
        kicker = bi(f'Počasí · {esc(place)}',
                    f'Weather · {esc(place)}' if english else None)
    else:
        # Digesty z doby, kdy vydání vycházelo ráno, nesou předpověď na
        # den vydání a proužek nemají. Popisujeme je tak, jak byly
        # napsané — přeznačit je na „zítra" by tvrdilo něco, co v datech
        # není.
        kicker = bi(
            f'Počasí na {esc(day_month(issue_date))} · {esc(place)}',
            f'Weather for {esc(day_month_en(issue_date))} · {esc(place)}'
            if english else None,
        )
    summary = bi(esc(weather["summary"]),
                 esc(weather["summary_en"]) if english else None)
    return f"""<section class="weather">
<p class="kicker">{kicker}</p>
<p>{summary}</p>{outlook}\
{render_weather_days(days, issue_date, english)}
</section>"""


def render_lead(data: dict) -> str:
    """Shrnutí dne nad otvírákem — dvě až čtyři věty o tom podstatném."""
    lines = data.get("highlights") or []
    if not lines:
        return ""
    english = data.get("highlights_en") or []
    rows = []
    for idx, line in enumerate(lines):
        if english:
            rows.append(f"<li>{sentence_span(line, esc(english[idx]))}</li>")
        else:
            rows.append(f"<li>{esc(line)}</li>")
    kicker = bi("Ve zkratce", "In brief" if english else None)
    return (f'<section class="lead">\n<p class="kicker">{kicker}</p>\n'
            f'<ul>\n{chr(10).join(rows)}\n</ul>\n</section>')


def render_vocabulary(items: list[dict]) -> str:
    """Slovníček vydání: všechna vysvětlená slovíčka pohromadě na konci."""
    words = collect_vocabulary(items)
    if not words:
        return ""
    rows = []
    for entry in words:
        czech = ""
        if entry.get("cs"):
            czech = f' <span class="cz">· {esc(entry["cs"])}</span>'
        rows.append(
            f'<li><span class="term">{esc(entry["term"])}</span>'
            f'<span class="def">{esc(entry["definition"])}{czech}</span>'
            f'<a class="more" href="{esc(cambridge_url(entry["term"]))}" '
            f'target="_blank" rel="noopener noreferrer">Cambridge ↗</a></li>'
        )
    heading = bi("Slovníček", "Vocabulary")
    return (f'<section class="vocab">\n<h2>{heading}</h2>\n'
            f'<ul>\n{chr(10).join(rows)}\n</ul>\n</section>')


HINT_CS = ("Čteš anglickou verzi českých zpráv. <b>Klikni na větu</b> "
           "a ukáže se česky, <b>tečkovaně podtržená slova</b> mají "
           "vysvětlivku.")
HINT_EN = ("Czech news retold in English (B2–C1). <b>Click any sentence</b> "
           "for the Czech version, <b>tap the dotted words</b> for "
           "a definition.")


def render_digest(data: dict, prev: str | None, nxt: str | None,
                  recent: list[str], *, is_index: bool,
                  labels: dict[str, tuple[str, str]]) -> str:
    items = data["items"]
    issue = data["date"]
    covered = covered_date(data)
    english = has_english(data)
    # Zbytek 24hodinového okna sahá do večera dne před pokrytým dnem.
    before = previous_date(covered)
    parts: list[str] = []

    def label(iso: str) -> str:
        cs, en = labels[iso]
        return bi(esc(cs), esc(en) if english else None)

    # Otvírák: zpráva doložená nejvíce zdroji. Při shodě vyhrává první
    # v pořadí digestu, které řadí důležitost redakčně.
    opener = max(items, key=lambda i: len(i["sources"]))
    rest = [i for i in items if i is not opener]

    issues = ""
    if recent:
        links = '<span class="sep">·</span>'.join(
            f'<a href="{esc(d)}.html">{label(d)}</a>' for d in recent
        )
        archive = bi("celý archiv", "full archive" if english else None)
        older = bi("Starší vydání:", "Earlier issues:" if english else None)
        issues = (f'\n<nav class="issues">{older} {links}'
                  f'<span class="sep">·</span>'
                  f'<a href="archiv.html">{archive}</a></nav>')

    minutes = reading_minutes(data)
    meta = bi(
        f"{esc(plural_items(len(items)))} &nbsp;·&nbsp; ≈ {minutes} min čtení",
        f"{esc(plural_items_en(len(items)))} &nbsp;·&nbsp; ≈ {minutes} min read"
        if english else None,
    )
    hint = f'\n<p class="hint">{bi(HINT_CS, HINT_EN)}</p>' if english else ""

    home = "index.html"
    title = bi(esc(SITE_TITLE), esc(SITE_TITLE_EN) if english else None)
    dateline = bi(esc(long_date(covered)),
                  esc(long_date_en(covered)) if english else None)
    parts.append(f"""<header class="masthead">
<h1><a href="{home}">{title}</a></h1>
<p class="dateline">{dateline}</p>
<hr class="rule-double">
<p class="meta">{meta}{updated_note(data.get("_updated"), english)}</p>\
{issues}{hint}
</header>""")

    if data.get("weather"):
        parts.append(render_weather(data["weather"], issue, english))

    parts.append(render_lead(data))
    parts.append(render_opener(opener, read_id(issue, opener), before))

    for rubric in RUBRIC_ORDER:
        group = [i for i in rest if i["rubric"] == rubric]
        if not group:
            continue
        body = "\n".join(
            render_item(i, read_id(issue, i), before) for i in group
        )
        heading = bi(esc(rubric),
                     esc(RUBRIC_EN[rubric]) if english else None)
        parts.append(
            f'<section class="rubric">\n<h2>{heading}</h2>\n{body}\n</section>'
        )

    parts.append(render_vocabulary(items))

    pager = ['<nav class="pager">']
    pager.append(
        f'<a href="{prev}.html">← {label(prev)}</a>' if prev
        else "<span></span>"
    )
    archive_word = bi("Archiv", "Archive" if english else None)
    pager.append(f'<a href="archiv.html">{archive_word}</a>')
    pager.append(
        f'<a href="{nxt}.html">{label(nxt)} →</a>' if nxt
        else "<span></span>"
    )
    pager.append("</nav>")
    parts.append("\n".join(pager))

    foot = ['<footer>']
    if data.get("sources_used"):
        used = esc(" · ".join(data["sources_used"]))
        foot.append(
            f'<p class="used">'
            + bi(f"Zdroje vydání: {used}",
                 f"Sources of this issue: {used}" if english else None)
            + "</p>"
        )
    if data.get("failed_feeds"):
        failed = esc(", ".join(data["failed_feeds"]))
        foot.append(
            f'<p class="warn">'
            + bi(f"Nepodařilo se načíst: {failed}.",
                 f"Could not be fetched: {failed}." if english else None)
            + "</p>"
        )
    hours = esc(data.get("window_hours", 24))
    foot.append(
        "<p>"
        + bi(
            "Vydání vzniká automaticky každý den v 17:00 a shrnuje "
            f"uplynulých {hours} hodin z RSS uvedených zdrojů. Každá zpráva "
            "odkazuje na původní článek. Počasí je předpověď na následující "
            "dny."
            + (" Anglická verze je překlad českého původního znění."
               if english else ""),
            "A new issue is put together automatically every day at 17:00 "
            f"and covers the last {hours} hours of the RSS feeds listed "
            "above. Every story links to the original article, which is in "
            "Czech. The English text is a translation of the Czech original."
            if english else None,
        )
        + "</p>"
    )
    if not is_index:
        latest = bi("Nejnovější vydání",
                    "Latest issue" if english else None)
        foot.append(f'<p><a href="index.html">{latest}</a></p>')
    foot.append("</footer>")
    parts.append("\n".join(foot))

    return "\n\n".join(part for part in parts if part)


def render_archive(digests: list[dict]) -> str:
    rows = []
    for data in reversed(digests):
        # Vydání se v archivu jmenuje podle dne, za který je. Datum vydání
        # se připisuje jen tehdy, když se od pokrytého dne liší — u běhu
        # v 17:00 jsou obvykle totožné.
        issued = ""
        if data["date"] != covered_date(data):
            issued = bi(f'vydáno {esc(day_month(data["date"]))} · ',
                        f'issued {esc(day_month_en(data["date"]))} · ')
        covered = covered_date(data)
        # Vydání z doby před anglickou verzí se označují, aby čtenáře
        # nepřekvapilo, že se na nich přepínač jazyka nenabízí.
        note = "" if has_english(data) else bi(" · jen česky", " · Czech only")
        count = bi(esc(plural_items(len(data["items"]))),
                   esc(plural_items_en(len(data["items"]))))
        rows.append(
            f'<li><a href="{esc(data["date"])}.html">'
            f'{bi(esc(long_date(covered)), esc(long_date_en(covered)))}</a>'
            f'<span class="count">{issued}{count}{note}</span></li>'
        )
    title = bi(esc(SITE_TITLE), esc(SITE_TITLE_EN))
    return f"""<header class="masthead">
<h1><a href="index.html">{title}</a></h1>
<p class="dateline">{bi("Archiv", "Archive")}</p>
<hr class="rule-double">
<p class="meta">{bi(f"{len(digests)} vydání", f"{len(digests)} issues")}\
{updated_note(digests[-1].get("_updated"), True)}</p>
</header>

<ul class="archive">
{chr(10).join(rows)}
</ul>

<nav class="pager">
<a href="index.html">← {bi("Nejnovější vydání", "Latest issue")}</a>
<span></span>
<span></span>
</nav>"""


# ────────────────────────────────────  main  ────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--check", action="store_true",
        help="jen zvaliduje digesty, nic nezapisuje",
    )
    args = ap.parse_args()

    try:
        digests = load_digests()
    except DigestError as exc:
        print(f"CHYBA: {exc}", file=sys.stderr)
        return 1

    if not digests:
        print("V digests/ nejsou žádné .json digesty.", file=sys.stderr)
        return 1

    total = sum(len(d["items"]) for d in digests)
    print(f"validní: {len(digests)} digestů, {total} položek", file=sys.stderr)

    if args.check:
        return 0

    DOCS.mkdir(exist_ok=True)
    (DOCS / "assets").mkdir(exist_ok=True)
    (DOCS / "assets" / "style.css").write_text(CSS.lstrip(), encoding="utf-8")
    # Bez .nojekyll by GitHub Pages pustil obsah přes Jekyll a mohl zahodit
    # soubory a adresáře začínající podtržítkem.
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")

    dates = [d["date"] for d in digests]
    # Odkazy na jiná vydání se popisují pokrytým dnem, ne dnem vydání.
    labels = {
        d["date"]: (short_date(covered_date(d)), short_date_en(covered_date(d)))
        for d in digests
    }

    def recent_before(idx: int) -> list[str]:
        """Až tři vydání předcházející tomu na pozici idx, nejnovější první."""
        return list(reversed(dates[max(0, idx - 3):idx]))

    def page_title(data: dict) -> str:
        covered = covered_date(data)
        if has_english(data):
            return f"{SITE_TITLE_EN} · {long_date_en(covered)}"
        return f"{SITE_TITLE} · {long_date(covered)}"

    for idx, data in enumerate(digests):
        prev = dates[idx - 1] if idx > 0 else None
        nxt = dates[idx + 1] if idx + 1 < len(dates) else None
        body = render_digest(data, prev, nxt, recent_before(idx),
                             is_index=False, labels=labels)
        (DOCS / f"{data['date']}.html").write_text(
            page(page_title(data), body, has_en=has_english(data)),
            encoding="utf-8",
        )

    latest = digests[-1]
    prev = dates[-2] if len(dates) > 1 else None
    (DOCS / "index.html").write_text(
        page(
            page_title(latest),
            render_digest(latest, prev, None, recent_before(len(dates) - 1),
                          is_index=True, labels=labels),
            has_en=has_english(latest),
        ),
        encoding="utf-8",
    )
    # Archiv je jen rozcestník, žádné zprávy nenese — dvojjazyčný je vždy.
    (DOCS / "archiv.html").write_text(
        page(f"{SITE_TITLE_EN} · archive", render_archive(digests),
             has_en=True),
        encoding="utf-8",
    )

    translated = sum(1 for d in digests if has_english(d))
    print(
        f"docs/: index.html, archiv.html, {len(digests)} denních stránek "
        f"({translated} s anglickou verzí)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
