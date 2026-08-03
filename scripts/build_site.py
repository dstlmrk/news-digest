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
import html
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DIGESTS = REPO_ROOT / "digests"
DOCS = REPO_ROOT / "docs"

SITE_TITLE = "Rychlé zprávy"

RUBRIC_ORDER = [
    "Domov",
    "Svět",
    "Ekonomika",
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

    if not isinstance(data["items"], list) or not data["items"]:
        fail("items musí být neprázdné pole")

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


def short_date(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.day}. {d.month}. {d.year}"


def plural_items(n: int) -> str:
    if n == 1:
        return "1 zpráva"
    if 2 <= n <= 4:
        return f"{n} zprávy"
    return f"{n} zpráv"


# ────────────────────────────────────  CSS  ─────────────────────────────────

CSS = """
/* Novinová sazba. Světlé téma je barva novinového papíru, tmavé je
   ztlumená varianta pro čtení večer. Přepínač zapisuje data-theme na
   <html>, jinak se řídí nastavením systému. */

:root {
  --paper: #f4efe3;
  --paper-raised: #faf6ec;
  --ink: #201d17;
  --ink-muted: #6d6555;
  --rule: #d2c8b3;
  --rule-strong: #201d17;
  --accent: #8c2f1d;
  --serif: Georgia, "Iowan Old Style", "Palatino Linotype", Palatino,
           "Times New Roman", "Times", serif;
}

@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --paper: #171612;
    --paper-raised: #1f1d18;
    --ink: #e7e1d4;
    --ink-muted: #9b9384;
    --rule: #35322a;
    --rule-strong: #6d6555;
    --accent: #d98a72;
  }
}

:root[data-theme="dark"] {
  --paper: #171612;
  --paper-raised: #1f1d18;
  --ink: #e7e1d4;
  --ink-muted: #9b9384;
  --rule: #35322a;
  --rule-strong: #6d6555;
  --accent: #d98a72;
}

* { box-sizing: border-box; }

html { -webkit-text-size-adjust: 100%; }

body {
  margin: 0;
  padding: 0 1.25rem 4rem;
  background: var(--paper);
  color: var(--ink);
  font-family: var(--serif);
  font-size: clamp(1rem, 0.97rem + 0.15vw, 1.075rem);
  line-height: 1.62;
  text-rendering: optimizeLegibility;
  -webkit-font-smoothing: antialiased;
}

.wrap { max-width: 40rem; margin: 0 auto; }

/* ── hlavička ─────────────────────────────────────────────────────────── */

.masthead { padding-top: 2.5rem; text-align: center; }

.masthead h1 {
  margin: 0;
  font-size: clamp(2rem, 1.3rem + 3.2vw, 3.1rem);
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  line-height: 1.05;
}

.masthead h1 a { color: inherit; text-decoration: none; }

.masthead .dateline {
  margin: 0.85rem 0 0;
  font-size: 0.8rem;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--ink-muted);
}

.rule-double {
  margin: 1.1rem 0 0;
  border: 0;
  border-top: 3px solid var(--rule-strong);
  border-bottom: 1px solid var(--rule-strong);
  height: 4px;
}

.meta {
  margin: 0.7rem 0 0;
  font-size: 0.78rem;
  letter-spacing: 0.04em;
  color: var(--ink-muted);
  text-align: center;
}

/* ── nejdůležitější ───────────────────────────────────────────────────── */

.highlights {
  margin: 2.2rem 0 0;
  padding: 1.15rem 1.35rem;
  background: var(--paper-raised);
  border: 1px solid var(--rule);
}

.highlights h2 {
  margin: 0 0 0.6rem;
  font-size: 0.72rem;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--ink-muted);
  font-weight: 700;
}

.highlights ul { margin: 0; padding-left: 1.1rem; }
.highlights li { margin: 0.32rem 0; font-style: italic; }

/* ── rubriky a položky ────────────────────────────────────────────────── */

.rubric { margin: 2.9rem 0 0; }

.rubric > h2 {
  margin: 0 0 0.2rem;
  padding-bottom: 0.4rem;
  border-bottom: 2px solid var(--rule-strong);
  font-size: 0.78rem;
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
  margin-bottom: 0.3rem;
  font-size: 0.72rem;
  letter-spacing: 0.12em;
  color: var(--ink-muted);
  font-variant-numeric: tabular-nums;
}

.stamp .flag { color: var(--accent); }

article h3 {
  margin: 0 0 0.45rem;
  font-size: 1.16em;
  line-height: 1.32;
  font-weight: 700;
}

article p { margin: 0; }

.sources {
  margin-top: 0.6rem;
  font-size: 0.82rem;
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

/* ── navigace a patička ───────────────────────────────────────────────── */

.pager {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem 1.5rem;
  justify-content: space-between;
  margin-top: 3rem;
  padding-top: 1.1rem;
  border-top: 1px solid var(--rule);
  font-size: 0.85rem;
}

.pager a { color: var(--accent); text-decoration: none; }
.pager a:hover { text-decoration: underline; }

footer {
  margin-top: 2.5rem;
  padding-top: 1.1rem;
  border-top: 3px double var(--rule-strong);
  font-size: 0.78rem;
  color: var(--ink-muted);
}

footer p { margin: 0.35rem 0; }
footer .warn { font-style: italic; }

/* ── přepínač témat ───────────────────────────────────────────────────── */

.theme-toggle {
  position: fixed;
  top: 0.85rem;
  right: 0.85rem;
  z-index: 10;
  padding: 0.4rem 0.7rem;
  background: var(--paper-raised);
  color: var(--ink-muted);
  border: 1px solid var(--rule);
  border-radius: 999px;
  font-family: var(--serif);
  font-size: 0.72rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  cursor: pointer;
}

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
.archive .count { font-size: 0.8rem; color: var(--ink-muted); }

/* ── mobil ────────────────────────────────────────────────────────────── */

@media (max-width: 32rem) {
  body { padding: 0 1rem 3rem; line-height: 1.58; }
  .masthead { padding-top: 3.25rem; }
  .masthead h1 { letter-spacing: 0.03em; }
  .highlights { padding: 1rem 1.1rem; }
  .rubric { margin-top: 2.3rem; }
  .pager { flex-direction: column; }
}

@media print {
  .theme-toggle, .pager { display: none; }
  body { background: #fff; color: #000; }
}
"""

THEME_JS = """
(function () {
  var root = document.documentElement;
  var stored = null;
  try { stored = localStorage.getItem('theme'); } catch (e) {}
  if (stored === 'dark' || stored === 'light') root.setAttribute('data-theme', stored);

  document.addEventListener('DOMContentLoaded', function () {
    var btn = document.querySelector('.theme-toggle');
    if (!btn) return;
    function label() {
      var dark = root.getAttribute('data-theme') === 'dark' ||
        (!root.getAttribute('data-theme') &&
         window.matchMedia('(prefers-color-scheme: dark)').matches);
      btn.textContent = dark ? 'Světlý režim' : 'Tmavý režim';
      btn.setAttribute('aria-pressed', dark ? 'true' : 'false');
    }
    label();
    btn.addEventListener('click', function () {
      var dark = root.getAttribute('data-theme') === 'dark' ||
        (!root.getAttribute('data-theme') &&
         window.matchMedia('(prefers-color-scheme: dark)').matches);
      var next = dark ? 'light' : 'dark';
      root.setAttribute('data-theme', next);
      try { localStorage.setItem('theme', next); } catch (e) {}
      label();
    });
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
<button class="theme-toggle" type="button">Tmavý režim</button>
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


def render_item(item: dict) -> str:
    flag = ""
    if item.get("cross_source"):
        n = len(item["sources"])
        flag = f' <span class="flag">· {n} zdroje</span>' if n < 5 \
            else f' <span class="flag">· {n} zdrojů</span>'
    return f"""<article>
<span class="stamp">{esc(item["time"])}{flag}</span>
<h3>{esc(item["headline"])}</h3>
<p>{esc(item["body"])}</p>
<p class="sources">{render_sources(item["sources"])}</p>
</article>"""


def render_digest(data: dict, prev: str | None, nxt: str | None,
                  *, is_index: bool) -> str:
    items = data["items"]
    parts: list[str] = []

    home = "index.html"
    parts.append(f"""<header class="masthead">
<h1><a href="{home}">{esc(SITE_TITLE)}</a></h1>
<p class="dateline">{esc(long_date(data["date"]))}</p>
<hr class="rule-double">
<p class="meta">{esc(plural_items(len(items)))} &nbsp;·&nbsp; okno {esc(data.get("window_hours", 24))} h &nbsp;·&nbsp; {esc(" · ".join(data.get("sources_used") or []))}</p>
</header>""")

    if data.get("highlights"):
        bullets = "\n".join(
            f"<li>{esc(h)}</li>" for h in data["highlights"]
        )
        parts.append(f"""<section class="highlights">
<h2>Nejdůležitější</h2>
<ul>
{bullets}
</ul>
</section>""")

    for rubric in RUBRIC_ORDER:
        group = [i for i in items if i["rubric"] == rubric]
        if not group:
            continue
        body = "\n".join(render_item(i) for i in group)
        parts.append(
            f'<section class="rubric">\n<h2>{esc(rubric)}</h2>\n{body}\n</section>'
        )

    pager = ['<nav class="pager">']
    pager.append(
        f'<a href="{prev}.html">← {esc(short_date(prev))}</a>' if prev
        else "<span></span>"
    )
    pager.append('<a href="archiv.html">Archiv</a>')
    pager.append(
        f'<a href="{nxt}.html">{esc(short_date(nxt))} →</a>' if nxt
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
        rows.append(
            f'<li><a href="{esc(data["date"])}.html">'
            f'{esc(long_date(data["date"]))}</a>'
            f'<span class="count">{esc(plural_items(len(data["items"])))}</span></li>'
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
    for idx, data in enumerate(digests):
        prev = dates[idx - 1] if idx > 0 else None
        nxt = dates[idx + 1] if idx + 1 < len(dates) else None
        body = render_digest(data, prev, nxt, is_index=False)
        (DOCS / f"{data['date']}.html").write_text(
            page(f"{SITE_TITLE} · {long_date(data['date'])}", body),
            encoding="utf-8",
        )

    latest = digests[-1]
    prev = dates[-2] if len(dates) > 1 else None
    (DOCS / "index.html").write_text(
        page(
            f"{SITE_TITLE} · {long_date(latest['date'])}",
            render_digest(latest, prev, None, is_index=True),
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
