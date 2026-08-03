# news-digest

Denní přehled zpráv ve stylu „rychlých zpráv", který jednou denně vyrobí
cloud routine v Claude Code a vydá jako statický web v novinové sazbě.
Běží ráno, takže vydání shrnuje **minulý den a ranní zprávy dne vydání** —
web se proto datuje pokrytým dnem, ne dnem, kdy vznikl.

Motivace: přečíst si jednou denně to podstatné z důvěryhodných českých
zdrojů, včetně sportu, místo průběžného scrollování.

## Kdy to běží a co vydání pokrývá

Spouští to **Claude routine každý den v 9:00** (Europe/Prague) — běží
v cloudu, takže na zapnutém notebooku nezávisí. Nastavení je v
[SETUP.md](SETUP.md).

Okno je 24 hodin, takže vydání z 9:00 obsahuje dění **od rána
předchozího dne až do rána, kdy vzniklo**. Není to přehled dneška —
dnešní den v době vydání ještě prakticky nezačal:

- Web se datuje **pokrytým dnem** („Zprávy za neděli 2. srpna 2026"),
  den vydání je jen v řádku s metadaty. V JSONu to drží pole `covers`,
  soubor v `digests/` se ale pořád jmenuje podle dne vydání.
- Zprávy vydané po půlnoci, tedy ráno dne vydání, mají v digestu
  `"day": "issue"` a na webu se u nich vypisuje i datum, aby se nepletly
  s pokrytým dnem.
- Počasí je jediná část, která patří ke dni vydání — je to předpověď na
  dnešek, ne na den, za který jsou zprávy.
- Ranní zprávy pokrytého dne už bývají ve včerejším vydání, proto se
  nový digest proti třem posledním deduplikuje.

Když digest výjimečně vznikne v jinou dobu (ruční běh odpoledne),
nastaví se `covers` na den, ze kterého je většina zpráv.

## Jak to funguje

```
sources.toml ──► fetch_feeds.py ──► feed.json ──► agent ──► digests/*.json ──► build_site.py ──► docs/
  19 RSS feedů    stažení, okno      témata se     výběr,      strukturovaný     validace,      GitHub
                  24 h, dedup,       signálem      redakce,    výstup            novinová       Pages
                  clustering         relevance     formát                        sazba
                              fetch_weather.py ──► počasí pro Hradec Králové (Open-Meteo)
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
| `scripts/fetch_weather.py` | Předpověď a kvalita ovzduší pro Hradec Králové |
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

Počasí pro Hradec Králové z Open-Meteo (bez API klíče).

## Web

Statický, bez závislostí a bez build toolchainu. Novinová sazba se serifovým
písmem ze systému, barva novinového papíru, tmavý režim pro čtení večer
(řídí se systémem, ikonový přepínač si volbu pamatuje) a responzivní layout
pro mobil. Hlavní zpráva dne jako otvírák, box s počasím, archiv
s prolistováním po dnech a kliknutím se zpráva označí jako přečtená
(stav drží localStorage prohlížeče, nikam se neodesílá). Odkazy na
původní články se otevírají v novém panelu.

V patičce je čas poslední aktualizace vydání a seznam zdrojů, ze kterých
digest vznikl. Čas bere build skript z gitu — z posledního commitu daného
digestu, a u ještě necommitnutého (tedy právě vznikajícího) z času buildu.
Přegenerování webu proto starším vydáním datum neposune.

## Lokální spuštění

```bash
python3 scripts/fetch_feeds.py --out /tmp/feed.json   # vyžaduje Python 3.11+
python3 scripts/fetch_feeds.py --hours 48             # širší okno

python3 scripts/build_site.py --check                 # jen zvaliduje digesty
python3 scripts/build_site.py                         # přegeneruje docs/

python3 -m http.server 8791 --directory docs          # náhled webu
```

`fetch_feeds.py` vypíše na stderr přehled, kolik položek každý feed dodal
a které selhaly. Nastavení routiny je v [SETUP.md](SETUP.md).
