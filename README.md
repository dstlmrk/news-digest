# news-digest

Denní přehled zpráv ve stylu „rychlých zpráv", který jednou denně vyrobí
cloud routine v Claude Code a commitne do `digests/`.

Motivace: přečíst si jednou denně to podstatné z důvěryhodných českých
zdrojů, včetně sportu, místo průběžného scrollování.

## Jak to funguje

```
sources.toml ──► scripts/fetch_feeds.py ──► /tmp/feed.json ──► agent ──► digests/RRRR-MM-DD.md
   13 RSS feedů      stažení, filtr 24 h,      témata se        výběr,        commit
                     seskupení duplicit        signálem         redakce,      (+ Slack)
                                               relevance        formát
```

Návrh stojí na dvou rozhodnutích:

**RSS, ne web search.** Anotace ve feedech mají 150–470 znaků, což je
přesně délka krátké zprávy — agent tedy většinou nemusí otevírat článek
vůbec. To je podstatné, protože HTML těch portálů je za bot ochranou
(iROZHLAS vrací na článek `403`), zatímco RSS projde bez problémů.
Zároveň to odřezává hlavní riziko sumarizace zpráv jazykovým modelem:
z pevného seznamu feedů se nedá „vyhledat" něco, co neexistuje.

**Deterministická část ve skriptu, úsudek v modelu.** Stahování, časové
okno, deduplikaci URL a párování téže zprávy napříč portály dělá Python.
Model dostane čistý vstup a řeší jen výběr, zkrácení a formulaci.

## Soubory

| Soubor | Co v něm je |
| --- | --- |
| `CLAUDE.md` | Postup běhu, co mě zajímá, redakční pravidla a limity |
| `.claude/skills/digest/SKILL.md` | Přesný formát výstupu |
| `sources.toml` | Seznam feedů, váhy, časové okno, práh clusteringu |
| `scripts/fetch_feeds.py` | Sběr a normalizace feedů (jen stdlib) |
| `SETUP.md` | Jak založit routinu a povolit síť na zpravodajské domény |
| `digests/` | Archiv digestů; slouží i k deduplikaci vůči předchozím dnům |

Chceš něco změnit? Zdroje v `sources.toml`, témata a pravidla v `CLAUDE.md`,
vzhled v `SKILL.md`. Prompt routiny zůstává krátký a odkazuje sem.

## Zdroje

iROZHLAS · ČT24 / ČT Sport · Deník N · Seznam Zprávy · Aktuálně.cz · Voxpot

## Lokální spuštění

```bash
python3 scripts/fetch_feeds.py --out /tmp/feed.json   # vyžaduje Python 3.11+
python3 scripts/fetch_feeds.py --hours 48             # širší okno
```

Skript vypíše na stderr přehled, kolik položek každý feed dodal a které
selhaly. Nastavení routiny je v [SETUP.md](SETUP.md).
