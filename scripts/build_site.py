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
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DIGESTS = REPO_ROOT / "digests"
DOCS = REPO_ROOT / "docs"

SITE_TITLE = "Daily News"

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
# Akuzativ pro spojení „zprávy za …" (za středu, za sobotu, za neděli).
WEEKDAYS_ACC = [
    "pondělí", "úterý", "středu", "čtvrtek", "pátek", "sobotu", "neděli",
]
MONTHS = [
    "ledna", "února", "března", "dubna", "května", "června", "července",
    "srpna", "září", "října", "listopadu", "prosince",
]

TIME_RE = re.compile(r"^\d{2}:\d{2}$")


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
        for key in ("summary", "outlook", "place", "icon"):
            if key in weather and not isinstance(weather[key], str):
                fail(f"weather.{key} musí být řetězec")
        if "icon" in weather and weather["icon"] not in WEATHER_ICONS:
            fail(
                f"weather.icon '{weather['icon']}' neznám, povolené jsou "
                f"{', '.join(sorted(WEATHER_ICONS))}"
            )

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
        if item.get("day") not in (None, "covered", "issue"):
            fail(
                f"{where}: day '{item['day']}' neznám, povolené jsou "
                f"'covered' (den, za který je přehled) a 'issue' "
                f"(ráno dne vydání)"
            )
        if not isinstance(item["sources"], list):
            fail(f"{where}: sources musí být pole")
        for src in item["sources"]:
            if not src.get("name") or not src.get("url"):
                fail(f"{where}: zdroj musí mít name i url")
            if not src["url"].startswith("http"):
                fail(f"{where}: url '{src['url'][:60]}' nezačíná na http")


def load_digests() -> list[dict]:
    digests = []
    for path in sorted(DIGESTS.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise DigestError(f"{path.name}: nevalidní JSON — {exc}") from exc
        validate(data, path)
        digests.append(data)
    return digests


# ──────────────────────────────────  pomůcky  ───────────────────────────────


def esc(text: str) -> str:
    return html.escape(str(text), quote=True)


def long_date(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{WEEKDAYS[d.weekday()]} {d.day}. {MONTHS[d.month - 1]} {d.year}"


def long_date_acc(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{WEEKDAYS_ACC[d.weekday()]} {d.day}. {MONTHS[d.month - 1]} {d.year}"


def short_date(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.day}. {d.month}. {d.year}"


def day_month(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.day}. {d.month}."


def covered_date(data: dict) -> str:
    """Den, za který přehled je — ne den, kdy vznikl.

    Routina běží ráno a bere 24hodinové okno, takže vydání z 3. 8. shrnuje
    dění z 2. 8. plus ranní zprávy dne vydání. Web se proto datuje podle
    pokrytého dne; `covers` v digestu to může přepsat (třeba u večerního
    běhu, který shrnuje tentýž den).
    """
    if data.get("covers"):
        return data["covers"]
    return (date.fromisoformat(data["date"]) - timedelta(days=1)).isoformat()


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

.masthead .dateline {
  margin: 0.8rem 0 0;
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
  display: flex;
  align-items: center;
  gap: 1.05rem;
}

.weather .w-icon { flex: none; color: var(--accent); }
.weather .w-icon svg { width: 2.5rem; height: 2.5rem; display: block; }
.weather .w-text { min-width: 0; }

.weather .kicker {
  margin: 0 0 0.4rem;
  font-family: var(--sans);
  font-size: 0.7rem;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--ink-muted);
  font-weight: 700;
}

.weather p { margin: 0; font-size: 0.95rem; }

.weather .outlook {
  margin-top: 0.35rem;
  font-style: italic;
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

[data-read-id].read .stamp::after,
[data-read-id].read .kicker::after {
  content: "· přečteno ✓";
  margin-left: 0.5rem;
  font-weight: 400;
  color: var(--ink-muted);
}

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
}

@media print {
  .theme-toggle, .pager, .issues { display: none; }
  body { background: #fff; color: #000; }
}
"""

THEME_JS = """
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

/* Přečtené zprávy: klik na zprávu ji označí (a odznačí), klik na odkaz
   ji označí a nechá odkaz normálně otevřít. Stav žije v localStorage,
   záznamy starší 90 dnů se promazávají. */
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
        if (map[id]) el.classList.add('read');

        el.addEventListener('click', function (ev) {
          if (ev.target.closest('a')) {
            // Otevření zdroje počítáme jako přečtení, ale neodznačujeme.
            if (!map[id]) {
              map[id] = Date.now();
              el.classList.add('read');
              save(map);
            }
            return;
          }
          // Výběr textu (např. kvůli kopírování) přečtení nepřepíná.
          if (window.getSelection && String(window.getSelection())) return;
          if (el.classList.toggle('read')) map[id] = Date.now();
          else delete map[id];
          save(map);
        });
      }
    );
  });
})();
"""


# ──────────────────────────────────  šablony  ───────────────────────────────


def page(title: str, body: str, *, depth_prefix: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="cs">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="color-scheme" content="light dark">
<meta name="description" content="Denní přehled zpráv z důvěryhodných českých zdrojů.">
<link rel="stylesheet" href="{depth_prefix}assets/style.css">
<script>{THEME_JS}</script>
</head>
<body>
<button class="theme-toggle" type="button" aria-label="Přepnout tmavý režim"></button>
<div class="wrap">
{body}
</div>
</body>
</html>
"""


def render_sources(sources: list[dict]) -> str:
    links = [
        f'<a href="{esc(s["url"])}" rel="noopener">{esc(s["name"])}</a>'
        for s in sources
    ]
    return '<span class="sep">·</span>'.join(links)


def cross_flag(item: dict) -> str:
    if not item.get("cross_source"):
        return ""
    n = len(item["sources"])
    return f"{n} zdroje" if n < 5 else f"{n} zdrojů"


READ_HINT = 'title="Kliknutím označíte zprávu jako přečtenou"'


def stamp(item: dict, issue_date: str) -> str:
    """Čas vydání; u zpráv z rána dne vydání i s datem, aby se nepletly.

    Většina položek je z pokrytého dne, kterým se datuje celé vydání —
    tam samotný čas nic nezamlžuje. Zprávy vydané po půlnoci ale patří
    až ke dni vydání, takže dostanou datum před čas.
    """
    if item.get("day") == "issue":
        return f'{day_month(issue_date)} {item["time"]}'
    return item["time"]


def render_item(item: dict, rid: str, issue_date: str) -> str:
    flag = cross_flag(item)
    flag_html = f' <span class="flag">· {esc(flag)}</span>' if flag else ""
    return f"""<article data-read-id="{rid}" {READ_HINT}>
<span class="stamp">{esc(stamp(item, issue_date))}{flag_html}</span>
<h3>{esc(item["headline"])}</h3>
<p>{esc(item["body"])}</p>
<p class="sources">{render_sources(item["sources"])}</p>
</article>"""


def render_opener(item: dict, rid: str, issue_date: str) -> str:
    flag = cross_flag(item)
    kicker = f'{esc(item["rubric"])} · {esc(stamp(item, issue_date))}'
    if flag:
        kicker += f" · {esc(flag)}"
    return f"""<section class="opener" data-read-id="{rid}" {READ_HINT}>
<p class="kicker">{kicker}</p>
<h2>{esc(item["headline"])}</h2>
<p>{esc(item["body"])}</p>
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


def render_weather(weather: dict, issue_date: str) -> str:
    place = weather.get("place") or "Hradec Králové"
    outlook = ""
    if weather.get("outlook"):
        outlook = f'\n<p class="outlook">{esc(weather["outlook"])}</p>'
    icon = ""
    if weather.get("icon") in WEATHER_ICONS:
        icon = (f'\n<div class="w-icon">{_W_SVG}'
                f'{WEATHER_ICONS[weather["icon"]]}</svg></div>')
    return f"""<section class="weather">{icon}
<div class="w-text">
<p class="kicker">Počasí na {esc(day_month(issue_date))} · {esc(place)}</p>
<p>{esc(weather["summary"])}</p>{outlook}
</div>
</section>"""


def render_digest(data: dict, prev: str | None, nxt: str | None,
                  recent: list[str], *, is_index: bool,
                  labels: dict[str, str]) -> str:
    items = data["items"]
    issue = data["date"]
    covered = covered_date(data)
    parts: list[str] = []

    # Otvírák: zpráva doložená nejvíce zdroji. Při shodě vyhrává první
    # v pořadí digestu, které řadí důležitost redakčně.
    opener = max(items, key=lambda i: len(i["sources"]))
    rest = [i for i in items if i is not opener]

    issues = ""
    if recent:
        links = '<span class="sep">·</span>'.join(
            f'<a href="{esc(d)}.html">{esc(labels[d])}</a>' for d in recent
        )
        issues = (f'\n<nav class="issues">Starší vydání: {links}'
                  f'<span class="sep">·</span>'
                  f'<a href="archiv.html">celý archiv</a></nav>')

    # Kolik zpráv už patří ke dni vydání — čtenář tak vidí, že přehled
    # nekončí pokrytým dnem, ale sahá až do rána, kdy vydání vzniklo.
    fresh = sum(1 for i in items if i.get("day") == "issue")
    fresh_note = (
        f" &nbsp;·&nbsp; z toho {fresh} z rána {esc(day_month(issue))}"
        if fresh else ""
    )

    home = "index.html"
    parts.append(f"""<header class="masthead">
<h1><a href="{home}">{esc(SITE_TITLE)}</a></h1>
<p class="dateline">Zprávy za {esc(long_date_acc(covered))}</p>
<hr class="rule-double">
<p class="meta">{esc(plural_items(len(items)))}{fresh_note} &nbsp;·&nbsp; okno {esc(data.get("window_hours", 24))} h &nbsp;·&nbsp; vydání {esc(short_date(issue))} &nbsp;·&nbsp; {esc(" · ".join(data.get("sources_used") or []))}</p>{issues}
</header>""")

    if data.get("weather"):
        parts.append(render_weather(data["weather"], issue))

    parts.append(render_opener(opener, read_id(issue, opener), issue))

    for rubric in RUBRIC_ORDER:
        group = [i for i in rest if i["rubric"] == rubric]
        if not group:
            continue
        body = "\n".join(
            render_item(i, read_id(issue, i), issue) for i in group
        )
        parts.append(
            f'<section class="rubric">\n<h2>{esc(rubric)}</h2>\n{body}\n</section>'
        )

    pager = ['<nav class="pager">']
    pager.append(
        f'<a href="{prev}.html">← {esc(labels[prev])}</a>' if prev
        else "<span></span>"
    )
    pager.append('<a href="archiv.html">Archiv</a>')
    pager.append(
        f'<a href="{nxt}.html">{esc(labels[nxt])} →</a>' if nxt
        else "<span></span>"
    )
    pager.append("</nav>")
    parts.append("\n".join(pager))

    foot = ['<footer>']
    if data.get("failed_feeds"):
        foot.append(
            f'<p class="warn">Nepodařilo se načíst: '
            f'{esc(", ".join(data["failed_feeds"]))}.</p>'
        )
    foot.append(
        "<p>Sestaveno automaticky z RSS uvedených zdrojů. "
        "Každá zpráva odkazuje na původní článek.</p>"
    )
    if not is_index:
        foot.append('<p><a href="index.html">Nejnovější vydání</a></p>')
    foot.append("</footer>")
    parts.append("\n".join(foot))

    return "\n\n".join(parts)


def render_archive(digests: list[dict]) -> str:
    rows = []
    for data in reversed(digests):
        # Vydání se v archivu jmenuje podle dne, za který je — soubor se
        # pořád jmenuje podle dne vydání, proto je datum vydání v popisku.
        rows.append(
            f'<li><a href="{esc(data["date"])}.html">'
            f'{esc(long_date(covered_date(data)))}</a>'
            f'<span class="count">vydání {esc(day_month(data["date"]))} · '
            f'{esc(plural_items(len(data["items"])))}</span></li>'
        )
    return f"""<header class="masthead">
<h1><a href="index.html">{esc(SITE_TITLE)}</a></h1>
<p class="dateline">Archiv</p>
<hr class="rule-double">
<p class="meta">{len(digests)} vydání</p>
</header>

<ul class="archive">
{chr(10).join(rows)}
</ul>

<nav class="pager">
<a href="index.html">← Nejnovější vydání</a>
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
    labels = {d["date"]: short_date(covered_date(d)) for d in digests}

    def recent_before(idx: int) -> list[str]:
        """Až tři vydání předcházející tomu na pozici idx, nejnovější první."""
        return list(reversed(dates[max(0, idx - 3):idx]))

    for idx, data in enumerate(digests):
        prev = dates[idx - 1] if idx > 0 else None
        nxt = dates[idx + 1] if idx + 1 < len(dates) else None
        body = render_digest(data, prev, nxt, recent_before(idx),
                             is_index=False, labels=labels)
        (DOCS / f"{data['date']}.html").write_text(
            page(f"{SITE_TITLE} · {long_date(covered_date(data))}", body),
            encoding="utf-8",
        )

    latest = digests[-1]
    prev = dates[-2] if len(dates) > 1 else None
    (DOCS / "index.html").write_text(
        page(
            f"{SITE_TITLE} · {long_date(covered_date(latest))}",
            render_digest(latest, prev, None, recent_before(len(dates) - 1),
                          is_index=True, labels=labels),
        ),
        encoding="utf-8",
    )
    (DOCS / "archiv.html").write_text(
        page(f"{SITE_TITLE} · archiv", render_archive(digests)),
        encoding="utf-8",
    )

    print(
        f"docs/: index.html, archiv.html, {len(digests)} denních stránek",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
