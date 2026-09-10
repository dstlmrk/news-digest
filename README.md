# news-digest

**Odpolední přehled dne** ve stylu „rychlých zpráv", který každý den
v 17:00 vyrobí cloud routine v Claude Code a vydá jako statický web
v novinové sazbě. K tomu **předpověď počasí na další dny**.

Motivace: přečíst si jednou denně to podstatné z důvěryhodných českých
zdrojů, včetně sportu, místo průběžného scrollování — a to v době, kdy
už je den odbytý a je co shrnovat.

**Web se čte anglicky.** Zprávy pocházejí z českých zdrojů a agent je
píše česky, ale vydání pak ještě přeloží do angličtiny na úrovni B2–C1.
Čeština na stránce zůstává k porovnání: kliknutím na větu se odkryje její
české znění, přepínačem v rohu se dá přejít rovnou na původní češtinu.
Těžší slova jsou v textu podtržená a nesou anglickou definici s odkazem
do Cambridge Dictionary. Denní přehled zpráv tak slouží zároveň jako
čtení k učení jazyka.

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
                  24 h, dedup,       signálem      redakce,    výstup            dvojjazyčná    Pages
                  clustering         relevance     formát            ▲           novinová sazba
                              fetch_weather.py ──► předpověď         │
                                                   (Open-Meteo)  add_english.py ◄── agent: anglický
                                                                 spáruje věty        překlad + slovíčka
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

Stejná dělba platí pro překlad: model píše jen anglické věty, české úseky
k nim dopáruje `add_english.py` a `build_site.py` pak ověří, že složené
dohromady dají přesně původní český text. Angličtina se tak nemůže
rozejít s češtinou, na kterou se na webu odkazuje.

## Soubory

| Soubor | Co v něm je |
| --- | --- |
| `CLAUDE.md` | Postup běhu, co mě zajímá, redakční pravidla a limity |
| `.claude/skills/digest/SKILL.md` | JSON schéma digestu a forma položek |
| `sources.toml` | Seznam feedů, váhy, časové okno, práh clusteringu |
| `scripts/fetch_feeds.py` | Sběr a normalizace feedů |
| `scripts/fetch_weather.py` | Předpověď na 5 dní a kvalita ovzduší pro Hradec Králové |
| `scripts/add_english.py` | Spojení anglického překladu s českými větami digestu |
| `scripts/build_site.py` | Validace digestů a generování dvojjazyčného webu do `docs/` |
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

Pod hlavičkou je box s počasím: **zítřek slovně s ikonou a proužek dalších
tří dnů** (den, ikona, denní a noční teplota). Následuje **Ve zkratce** —
dvě až čtyři věty o tom podstatném —, hlavní zpráva dne jako otvírák,
rubriky a archiv s prolistováním po dnech. Odkazy na původní články se
otevírají v novém panelu.

**Přečtená zpráva se ztlumí.** Přepíná to zaškrtávací tlačítko vpravo na
řádku se zdroji, tedy tam, kde čtenář skončí. Stav drží localStorage
prohlížeče a nikam se neodesílá.

### Dvojjazyčné čtení

Obě jazykové verze jsou v HTML naráz a přepínač jen mění, která se ukazuje
— na statickém webu není kam pro překlad dojet. Volba se pamatuje
v localStorage.

- **Kliknutí na větu** za ni vloží její české znění. Výrazně se podbarví
  ta věta, kterou čteš — v odstavci se hledá nejhůř —, překlad má slabší
  podbarvení a kurzívu.
- **Kolečko `EN`/`CS`** v rohu vedle přepínače tmavého režimu přepne celou
  stránku do původního českého znění a zpátky.
- **Slova nad úroveň B2** jsou tečkovaně podtržená; po kliknutí ukážou
  definici jednoduchou angličtinou a odkaz do Cambridge Dictionary. Česky
  se slovíčko nepřekládá — smysl je zůstat v jazyce.

Starší vydání z doby před anglickou verzí zůstávají česky a přepínač na
nich není. Angličtinu má vydání buď celou, nebo vůbec — build skript
napůl přeložený digest odmítne.

V patičce je čas poslední aktualizace vydání a seznam zdrojů, ze kterých
digest vznikl. Čas bere build skript z gitu — z posledního commitu daného
digestu, a u ještě necommitnutého (tedy právě vznikajícího) z času buildu.
Přegenerování webu proto starším vydáním datum neposune.

## Lokální spuštění

```bash
python3 scripts/fetch_feeds.py --out /tmp/feed.json   # vyžaduje Python 3.11+
python3 scripts/fetch_feeds.py --hours 48             # širší okno

python3 scripts/fetch_weather.py --out /tmp/weather.json   # předpověď na 5 dní

python3 scripts/add_english.py --digest digests/2026-09-08.json --show
python3 scripts/add_english.py --digest digests/2026-09-08.json \
    --translations /tmp/en.json                       # doplní anglickou verzi

python3 scripts/build_site.py --check                 # jen zvaliduje digesty
python3 scripts/build_site.py                         # přegeneruje docs/

python3 -m http.server 8791 --directory docs          # náhled webu
```

`fetch_feeds.py` vypíše na stderr přehled, kolik položek každý feed dodal
a které selhaly. Nastavení routiny je v [SETUP.md](SETUP.md).
