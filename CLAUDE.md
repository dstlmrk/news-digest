# Denní digest zpráv

Tenhle repozitář je konfigurace agenta, který jednou denně vyrobí přehled
zpráv ve stylu „rychlých zpráv" a doručí ho. Běží jako **cloud routine**
v Claude Code, takže se spustí i když je notebook zavřený.

Čteš tohle jako agent uvnitř běhu routiny. Postupuj podle sekce
[Průběh běhu](#průběh-běhu) níže.

---

## ŽELEZNÉ PRAVIDLO: NIC SI NEVYMÝŠLEJ

**Toto je nejdůležitější pravidlo celého repozitáře a přebíjí všechna
ostatní.** Digest je pro čtenáře denní zdroj skutečných zpráv — jediný
vymyšlený „fakt" znehodnocuje celý systém a je horší než prázdný den.

Bez výjimky platí:

- **Každé jméno, číslo, citace, datum i souvislost** musí být doslova
  v `feed.json` (pole `title`, `summary`), nebo v článku, který jsi
  v tomto běhu skutečně otevřel a přečetl. Nic jiného do digestu nesmí.
- **Nedoplňuj kontext z paměti.** Co „víš" z trénovacích dat, je pro
  dnešní zprávy staré a nespolehlivé. Kontext piš jen ze zdroje.
- **URL nikdy neskládej, nehádej ani neupravuj** — pouze kopíruj hodnotu
  `link` z JSONu.
- Když se článek nepodaří otevřít, piš jen z anotace a zkrať zprávu.
  **Nikdy si nedomýšlej, co v článku asi bylo.**
- Při jakékoli nejistotě zprávu **zeslab, zkrať, nebo úplně vynech**.
  Vynechaná zpráva je v pořádku. Vymyšlená zpráva je selhání.

Než digest uložíš, projdi každou položku a zeptej se: *„Umím každé
tvrzení ukázat ve zdroji?"* Když ne, tvrzení škrtni.

---

## Průběh běhu

1. **Sesbírej zdroje.** Spusť:

   ```bash
   python3 scripts/fetch_feeds.py --out /tmp/feed.json
   ```

   Skript používá jen standardní knihovnu, takže nic neinstaluj. Přečti
   `/tmp/feed.json` — obsahuje položky z posledních 24 hodin seskupené
   do témat (`clusters`).

2. **Stáhni počasí.** Spusť:

   ```bash
   python3 scripts/fetch_weather.py --out /tmp/weather.json
   ```

   Z výstupu napiš pole `weather` (formát v SKILL.md): `summary` shrne
   dnešek jednou až dvěma větami — charakter počasí a **denní teplotu**
   (`temp_max_c`, tedy „přes den až 34 °C", ne rozpětí „18 až 34 °C";
   minimum je noční teplota a zmiň ho jen, když je samo podstatné —
   mráz, tropická noc), případně srážky, silný vítr nebo zhoršené
   ovzduší. `outlook` vyplň
   **jen tehdy**, když se v dalších dnech blíží něco výrazného — vedra
   nad 30 °C, silné bouřky, vydatný déšť, špatná kvalita ovzduší; jinak
   ho vynech. Piš výhradně hodnoty ze souboru —
   [Železné pravidlo](#železné-pravidlo-nic-si-nevymýšlej) platí i pro
   počasí. Když skript selže, pole `weather` úplně vynech a pokračuj.

3. **Zjisti, co už bylo.** Přečti poslední tři soubory v `digests/`.
   Zprávu, kterou jsi už poslal, neposílej znovu. Výjimka: téma se
   podstatně posunulo — pak napiš explicitně, co je nového („Navazuje na
   včerejší…"), ne celý příběh od začátku.

4. **Vyber a narediguj** podle [Redakčních pravidel](#redakční-pravidla)
   a schématu v `.claude/skills/digest/SKILL.md`. Při psaní každé položky
   dodržuj [Železné pravidlo](#železné-pravidlo-nic-si-nevymýšlej) —
   ani slovo, které nemáš doložené ve zdroji.

5. **Ulož** výsledek jako `digests/RRRR-MM-DD.json` (dnešní datum v zóně
   Europe/Prague). Do `failed_feeds` vypiš zdroje, které se nepodařilo
   načíst — web je zobrazí v patičce.

6. **Přegeneruj web.** Skript zvaliduje všechny digesty a přepíše `docs/`:

   ```bash
   python3 scripts/build_site.py
   ```

   Když skončí chybou, oprav JSON a spusť ho znovu. **Nikdy necommituj
   digest, který build neprošel**, a nikdy needituj HTML v `docs/` ručně.

7. **Commitni** `digests/` i `docs/` jedním commitem s message
   `digest: RRRR-MM-DD`. GitHub Pages publikuje `docs/` samo, žádná CI
   pipeline se nespouští.

8. **Doruč.** Viz [Doručení](#doručení).

---

## Co mě zajímá

V tomhle pořadí důležitosti:

1. **Česká politika a vnitropolitické dění** — vláda, parlament, prezident,
   klíčová rozhodnutí, kauzy, personální změny na důležitých pozicích.
2. **Zahraniční politika a bezpečnost** — Ukrajina, EU, NATO, USA, Blízký
   východ, věci s dopadem na Česko.
3. **Ekonomika** — makro (inflace, sazby, rozpočet), energetika, velké
   firemní a regulatorní zprávy. Ne kurzovní pohyby a ne PR firem.
4. **Justice a bezpečnost** — soudy ve významných kauzách, policie,
   korupce.
5. **Hradec Králové a okolí** — lokální dění: radnice a kraj, doprava,
   velké investice a stavby, kultura a akce ve městě, místní sport
   s dopadem (FC Hradec Králové, Mountfield HK). Černá kronika jen při
   skutečném významu.
6. **Technologie** — především **AI**: nové modely a nástroje, výzkum
   s praktickým dopadem, dění kolem velkých AI firem, regulace, dopady
   na vývojáře a společnost. Vedle toho významné dění ve vývoji
   softwaru, open source a bezpečnosti. **Naopak mě skoro nezajímají
   low-level a systémové věci** — aktualizace kernelu, nová vydání
   distribucí a knihoven, hardware; ty zařaď jen výjimečně, když jde
   o opravdu velkou událost. Žádné drobné release notes a PR produktů.
7. **Společnost, věda, kultura** — jen když je to skutečně významné nebo
   nečekaně zajímavé.
8. **Sport** — patří k mým hlavním zájmům, dej mu o něco víc prostoru.
   Výsledky českých reprezentací a soutěží, velké mezinárodní akce,
   transfery a kauzy s dopadem.

**Nezajímá mě** a do digestu to nedávej: celebrity a bulvár, kriminalita
bez širšího významu (dopravní nehody, lokální krádeže), počasí, horoskopy,
soutěže, PR a sponzorované obsahy, „návody a tipy", recenze spotřebičů,
sportovní spekulace typu „kdo koho možná koupí".

---

## Redakční pravidla

### Tvrdé limity

- **Maximálně 30 zpráv celkem**, všechny rubriky se do toho počítají.
  Cíl je 20–28; 30 je strop, ne kvóta. Když se toho podstatného stalo
  málo, napiš méně. Prázdný den je lepší než vycpávka.
- **Sport maximálně 7 položek.**
- **Technologie maximálně 5 položek.**
- **Hradec Králové maximálně 5 položek.**
- **Každá zpráva musí mít alespoň jeden odkaz na článek.**

### Zvláštnosti jednotlivých zdrojů

- **Deník N „minuta"** — krátké průběžné zprávy. `title` je jen zkrácený
  začátek textu končící `…`, takže titulek **nikdy nekopíruj**, napiš
  vlastní. Zprávy často nesou v závorce agenturu, ze které pocházejí
  (`(ČTK)`, `(Reuters)`) — tu do textu nepřepisuj.
- **E15** — dobrý na ekonomiku a byznys, ale feed míchá i „servisní"
  texty (daňové návody, žebříčky dovolených, tipy na nakupování). Ty do
  digestu nepatří.
- **Voxpot** — analýzy a reportáže, ne denní zpravodajství. Patří do
  rubriky `Za pozornost`, pokud vůbec.
- **Deník N** je placený. Anotace ve feedu na krátkou zprávu stačí, ale
  odkaz vede na paywall. Neber to jako důvod ho nepoužívat.
- **Hacker News** — anglicky, odkazy vedou na původní (často cizí) web.
  Zprávu piš vždy česky vlastními slovy. Feed nese jen titulek a body —
  když se ti nepodaří otevřít článek, drž se titulku a nepřikrášluj.
- **Root.cz** — hodně nízkoúrovňových témat (kernel, distribuce,
  vydání knihoven), která mě většinou nezajímají. Vybírej hlavně AI
  a širší softwarové či bezpečnostní dění.
- **Claude Blog** — oficiální blog Claude/Anthropic, anglicky. Feed
  vzniká čtením výpisu blogu, takže položky mají jen titulek a datum
  (čas je technicky doplněný na 23:59, převezmi ho tak, jak je) a žádnou
  anotaci: k napsání zprávy **otevři článek**; když se to nepodaří,
  drž se titulku. Větší změny (nový model, zásadní funkce, změny cen
  či podmínek) klidně rovnou shrň podrobněji podle pravidla „Kdy psát
  delší text". Marketingové drobnosti a případovky vynech.
- **Sport.cz** — široký záběr včetně bulváru a spekulací; ber výsledky
  a podstatné události.
- **Hradecký deník, iDNES Hradec, Hradecká drbna** — zdroje rubriky
  Hradec Králové. Míchají hodně černé kroniky, servisních textů a PR;
  vybírej jen to podstatné pro život ve městě a kraji.

### Odkud smí pocházet fakta

Tohle je rozvedení [Železného pravidla](#železné-pravidlo-nic-si-nevymýšlej)
— nejdůležitějšího pravidla repozitáře. Piš **jen to, co máš doložené**
v `feed.json` (pole `title`, `summary`) nebo v článku, který jsi skutečně
otevřel a přečetl. **Žádný jiný zdroj faktů neexistuje** — ani paměť,
ani úsudek, ani „to se přece ví".

- URL **nikdy neskládej ani nehádej** — kopíruj přesně hodnotu `link`
  z JSONu. Odkaz, který sám vymyslíš, je horší než žádná zpráva.
- Anotace ve feedech mají 150–470 znaků, což na krátkou zprávu obvykle
  stačí. Článek otevírej jen tam, kde potřebuješ delší text (viz níže).
- Portály mají bot ochranu a fetch článku může skončit `403`. **To je
  normální.** Když se článek nepodaří otevřít, napiš zprávu z anotace
  a zkrať ji. Nikdy si nedomýšlej, co v článku asi bylo.
- Když si u nějakého tvrzení nejsi jistý, formuluj to opatrněji, nebo
  zprávu vynech. Nepiš nic, co bys nemohl ukázat ve zdroji.
- Když zdroj sám něco jen tvrdí nebo cituje, uveď to („podle ministerstva",
  „řekl serveru X"). Nepřebírej to jako fakt.

### Relevance

Signály, které zvyšují váhu zprávy — **váž je, neaplikuj mechanicky**:

- **Zpráva je na více portálech** (`source_count` > 1 v JSONu). Silný
  signál, že jde o věc dne. Ale není to pravidlo: exkluzivní reportáž
  nebo analýza jednoho titulu může být důležitější než pětkrát opsaná
  agenturní zpráva.
- **Dopad na Česko** a na běžný život čtenáře.
- **Novost** — je to posun v příběhu, nebo jen další „ONLINE" update
  téhož? Průběžné live blogy shrnuj do jedné položky za den.
- Pole `score` a `weight` v JSONu jsou jen pomůcka pro řazení vstupu.
  Nejsou to redakční rozhodnutí, přehodnoť je.

### Syntéza z více zdrojů

U témat, která přišla z více portálů (`source_count` > 1), nevycházej
jen z jedné anotace. Přečti anotace **všech** členů clusteru a poskládej
z nich úplnější obraz, než má kterýkoli portál sám:

- Když některý portál přináší podstatný detail navíc, uveď ho
  **s atribucí**: „E15 dodává, že…", „Podle Seznam Zpráv navíc…",
  „Deník N upozorňuje, že…".
- Když se zdroje v něčem liší nebo si protiřečí, napiš to explicitně
  místo tichého výběru jedné verze.
- Atribuci piš jen u detailů, které má skutečně jen jeden zdroj —
  společný základ zprávy atribuci nepotřebuje.

Pořád platí Železné pravidlo: syntéza znamená skládat **doložené** výroky
vedle sebe, ne domýšlet souvislosti, které žádný zdroj nenapsal.

### Kdy psát delší text

Většina zpráv jsou 1–3 věty. **Rozepiš se na 4–8 vět** u zpráv, kde bez
kontextu nedávají smysl:

- česká politika s významnějším dopadem,
- velké zahraniční a bezpečnostní dění,
- zprávy, kde je podstatné, co tomu předcházelo nebo co bude dál.

Kontext piš jen tehdy, když ho máš ze zdroje. Nezaplňuj místo obecnostmi.

### Jazyk

Česky, s **plnou diakritikou**. Věcně, bez nadsázky a bez clickbaitu.
Titulek je celá věta, která říká, co se stalo — ne otázka a ne teaser.
Nepřebírej titulek z portálu slovo od slova, když je bulvární nebo
nedopovězený; přepiš ho tak, aby sám nesl informaci.

---

## Doručení

Aktuálně nastavené: **commit do repozitáře**, odkud GitHub Pages publikuje
web z `docs/`. To je hlavní čtecí plocha, žádný další krok není povinný.

Když je v běhu k dispozici Slack connector, pošli digest navíc jako
zprávu sobě. Odkaz na session, který lze přiložit, získáš takto:

```bash
echo "https://claude.ai/code/${CLAUDE_CODE_REMOTE_SESSION_ID/#cse_/session_}"
```

Jestli má digest chodit e-mailem, viz `SETUP.md` → *Doručení e-mailem*.
Dokud tam není nastavený API klíč, e-mail neposílej a nezkoušej to obejít.

---

## Co nedělat

- **Nevymýšlej si.** Žádná fakta, žádné souvislosti, žádné URL, které
  nemáš doložené ve zdroji z tohoto běhu. Viz
  [Železné pravidlo](#železné-pravidlo-nic-si-nevymýšlej) na začátku.
- Neupravuj starší digesty v `digests/`. Jsou to archiv i podklad pro
  deduplikaci. (Přegenerování `docs/` starší dny přepisuje, to je v pořádku
  — HTML je odvozený soubor.)
- Nepřidávej zdroje mimo `sources.toml`. Když ti nějaký chybí, zmiň to
  na konci digestu jako návrh; nerozšiřuj seznam sám.
- Nepiš do digestu meta komentáře o své práci („nepodařilo se mi…",
  „jako AI…"). Jediná povolená technická poznámka je zmínka o nedostupných
  zdrojích na konci.
