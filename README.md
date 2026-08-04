# news-digest

**Odpolední přehled dne** ve stylu „rychlých zpráv", který každý den
v 17:00 vyrobí cloud routine v Claude Code a vydá jako statický web
v novinové sazbě. K tomu **předpověď počasí na další dny**.

Motivace: přečíst si jednou denně to podstatné z důvěryhodných českých
zdrojů, včetně sportu, místo průběžného scrollování — a to v době, kdy
už je den odbytý a je co shrnovat.

## Kdy to běží a co vydání pokrývá

Spouští to **Claude routine každý den v 17:00** (Europe/Prague) — běží
v cloudu, takže na zapnutém notebooku nezávisí. Nastavení je v
[SETUP.md](SETUP.md).

Okno je 24 hodin, takže vydání ze 17:00 obsahuje **celý dnešek až do
odpoledne** a k tomu dobírá **večer předchozího dne**, který se do
včerejšího vydání už nevešel:

- Web se datuje **pokrytým dnem**, což je den vydání („Zprávy za úterý
  4. srpna 2026"). V JSONu to drží pole `covers`; liší se od `date`
  jen u ručního běhu v jinou dobu.
- Zprávy z včerejšího večera mají v digestu `"day": "prev"` a na webu se
  u nich vypisuje i datum, aby se nepletly s dneškem.
- Počasí je jediná část, která nepatří k pokrytému dni, ale dopředu —
  dnešek má čtenář v 17:00 za sebou, takže se ukazuje **zítřek a další
  dny**.
- Konec okna už bývá ve včerejším vydání, proto se nový digest proti
  třem posledním deduplikuje.

Když digest výjimečně vznikne v jinou dobu (ruční běh dopoledne),
nastaví se `covers` na den, ze kterého je většina zpráv.

## Jak to funguje

```
sources.toml ──► fetch_feeds.py ──► feed.json ──► agent ──► digests/*.json ──► build_site.py ──► docs/
  19 RSS feedů    stažení, okno      témata se     výběr,      strukturovaný     validace,      GitHub
                  24 h, dedup,       signálem      redakce,    výstup            novinová       Pages
                  clustering         relevance     formát                        sazba
                              fetch_weather.py ──► předpověď na další dny (Open-Meteo)
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
Model dostane čistý vstup a řeší jen výběr, zkrácení a formulaci. Výstup
je strukturovaný JSON, ne rovnou HTML — sazba webu je pak čistě otázka
šablony, ne toho, co model zvládne napsat.

## Soubory

| Soubor | Co v něm je |
| --- | --- |
| `CLAUDE.md` | Postup běhu, co mě zajímá, redakční pravidla a limity |
| `.claude/skills/digest/SKILL.md` | JSON schéma digestu a forma položek |
| `sources.toml` | Seznam feedů, váhy, časové okno, práh clusteringu |
| `scripts/fetch_feeds.py` | Sběr a normalizace feedů |
| `scripts/fetch_weather.py` | Předpověď na 5 dní a kvalita ovzduší pro Hradec Králové |
| `scripts/build_site.py` | Validace digestů a generování webu do `docs/` |
| `SETUP.md` | Jak založit routinu, povolit síť a zapnout Pages |
| `digests/` | Digesty jako JSON; archiv i podklad pro deduplikaci |
| `docs/` | Generovaný web — nikdy needituj ručně |

Chceš něco změnit? Zdroje v `sources.toml`, témata a pravidla v `CLAUDE.md`,
strukturu výstupu v `SKILL.md`, sazbu webu v `scripts/build_site.py`
(konstanta `CSS`). Prompt routiny zůstává krátký a odkazuje sem.

## Zdroje

iROZHLAS · ČT24 / ČT Sport · Deník N (včetně proudu „minuta") ·
Seznam Zprávy · E15 · Voxpot · Sport.cz · Root.cz · Hacker News ·
Claude Blog (parsuje se HTML výpis, blog nemá RSS) · Hradecký deník ·
iDNES Hradec · Hradecká drbna

Předpověď pro Hradec Králové z Open-Meteo (bez API klíče).

## Web

Statický, bez závislostí a bez build toolchainu. Novinová sazba se serifovým
písmem ze systému, barva novinového papíru, tmavý režim pro čtení večer
(řídí se systémem, ikonový přepínač si volbu pamatuje) a responzivní layout
pro mobil.

Hlavička nese podtitulek „Zprávy z českých zdrojů · nové vydání každý den
v 17:00", aby bylo z první obrazovky jasné, co web je. Pod ní box
s počasím: **zítřek slovně s ikonou a proužek dalších tří dnů** (den,
ikona, denní a noční teplota). Následuje hlavní zpráva dne jako otvírák,
rubriky a archiv s prolistováním po dnech. Kliknutím se zpráva označí
jako přečtená (stav drží localStorage prohlížeče, nikam se neodesílá),
odkazy na původní články se otevírají v novém panelu.

V patičce je čas poslední aktualizace vydání a seznam zdrojů, ze kterých
digest vznikl. Čas bere build skript z gitu — z posledního commitu daného
digestu, a u ještě necommitnutého (tedy právě vznikajícího) z času buildu.
Přegenerování webu proto starším vydáním datum neposune.

## Lokální spuštění

```bash
python3 scripts/fetch_feeds.py --out /tmp/feed.json   # vyžaduje Python 3.11+
python3 scripts/fetch_feeds.py --hours 48             # širší okno

python3 scripts/fetch_weather.py --out /tmp/weather.json   # předpověď na 5 dní

python3 scripts/build_site.py --check                 # jen zvaliduje digesty
python3 scripts/build_site.py                         # přegeneruje docs/

python3 -m http.server 8791 --directory docs          # náhled webu
```

`fetch_feeds.py` vypíše na stderr přehled, kolik položek každý feed dodal
a které selhaly. Nastavení routiny je v [SETUP.md](SETUP.md).
