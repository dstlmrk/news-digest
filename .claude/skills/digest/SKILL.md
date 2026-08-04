---
name: digest
description: Formát odpoledního přehledu zpráv - JSON schéma souboru v digests/ a redakční forma položek. Použij při psaní digestu v tomto repozitáři.
---

# Formát digestu

Digest se ukládá jako **JSON** do `digests/RRRR-MM-DD.json`. Z něj se
skriptem `scripts/build_site.py` generuje web do `docs/`. JSON je jediný
zdroj pravdy — HTML nikdy needituj ručně.

Redakční pravidla a limity jsou v `CLAUDE.md`. Tady je struktura a forma.

Digest vzniká v 17:00 a pokrývá **dnešek plus večer předchozího dne** —
soubor se jmenuje podle dne vydání, což je zároveň pokrytý den (`covers`).
Podrobně v `CLAUDE.md` → *Co vydání pokrývá*.

> **ŽELEZNÉ PRAVIDLO (viz `CLAUDE.md`): nic si nevymýšlej.** Každé tvrzení
> v `headline`, `body` i `highlights` musí být doslova doložené ve
> `feed.json` nebo v článku, který jsi v tomto běhu otevřel a přečetl.
> Každé `url` je kopie pole `link`, nikdy vlastní konstrukce. Co nemáš
> ve zdroji, do JSONu nepatří — bez výjimky.

## Schéma

```json
{
  "date": "2026-08-03",
  "covers": "2026-08-03",
  "window_hours": 24,
  "sources_used": ["iROZHLAS", "ČT24", "Deník N", "Seznam Zprávy", "E15"],
  "failed_feeds": [],
  "weather": {
    "place": "Hradec Králové",
    "icon": "cloudy",
    "summary": "Zítra zataženo a horko, přes den až 34 °C, beze srážek. Kvalita ovzduší zhoršená.",
    "outlook": "Ve čtvrtek přijdou vydatné bouřky.",
    "days": [
      { "date": "2026-08-04", "icon": "cloudy", "temp_max_c": 34.1, "temp_min_c": 18.3 },
      { "date": "2026-08-05", "icon": "storm", "temp_max_c": 38.2, "temp_min_c": 20.7 },
      { "date": "2026-08-06", "icon": "rain", "temp_max_c": 28.4, "temp_min_c": 16.1 }
    ]
  },
  "highlights": [
    "Jedna věta o nejdůležitější zprávě dne.",
    "Jedna věta o druhé."
  ],
  "items": [
    {
      "rubric": "Domov",
      "time": "11:11",
      "day": "covered",
      "headline": "Bitcoinová kauza míří k soudu, žalobkyně chce pro Blažka 6,5 roku",
      "body": "Vrchní státní zastupitelství v Olomouci podalo obžalobu na čtyři lidi…",
      "cross_source": true,
      "sources": [
        { "name": "ČT24", "url": "https://ct24.ceskatelevize.cz/clanek/…" },
        { "name": "iROZHLAS", "url": "https://www.irozhlas.cz/…" }
      ]
    }
  ]
}
```

### Pole

| Pole | Povinné | Význam |
| --- | --- | --- |
| `date` | ano | Den **vydání**: `RRRR-MM-DD`, dnešní datum v zóně Europe/Prague. Musí odpovídat názvu souboru. |
| `covers` | ne | Den, **za který** přehled je. Při běhu v 17:00 totéž jako `date`. Web se datuje tímhle dnem. Když pole vynecháš, bere se den vydání. |
| `window_hours` | ano | Časové okno, ze kterého zprávy pocházejí. Ber z `feed.json`. |
| `sources_used` | ano | Názvy zdrojů, které do digestu **skutečně** přispěly. Ne celý seznam z configu. |
| `failed_feeds` | ano | Názvy feedů, které se nepodařilo načíst. Prázdné pole, když je vše v pořádku. |
| `weather` | ne | Předpověď z `/tmp/weather.json` (viz krok 2 v CLAUDE.md). **Dnešek do ní nepatří** — vydání vychází v 17:00, kdy ho má čtenář za sebou. Podrobně níže. Když počasí není k dispozici, celé pole vynech. |
| `highlights` | ne | 2–4 věty o nejdůležitějším. Bez odkazů. Když se nestalo nic zásadního, vynech nebo dej prázdné pole. |
| `items` | ano | Položky v pořadí, v jakém se mají zobrazit. |

### Pole položky

| Pole | Povinné | Význam |
| --- | --- | --- |
| `rubric` | ano | Přesně jedna z: `Domov`, `Hradec Králové`, `Svět`, `Ekonomika`, `Technologie`, `Společnost a kultura`, `Za pozornost`, `Sport`. Jiná hodnota build skript zastaví. |
| `time` | ano | `HH:MM`, čas vydání z pole `published` přepočtený na Europe/Prague. U témat z více zdrojů čas nejnovějšího. |
| `day` | ne | Ke kterému dni čas patří: `covered` (pokrytý den, tedy dnešek — výchozí, můžeš vynechat) nebo `prev` (večer předchozího dne, konec 24hodinového okna). U `prev` web přidá k času datum, aby si čtenář zprávu nepletl s dneškem. Řiď se polem `published`, ne odhadem. |
| `headline` | ano | Celá věta, která říká, co se stalo. Bez tečky na konci. |
| `body` | ano | 1–3 věty, u důležitých zpráv 4–8. Prostý text, jeden odstavec, bez Markdownu a bez odrážek. **Jen fakta doložená ve zdroji — nic z paměti, nic domyšleného.** |
| `cross_source` | ne | `true`, když téma přišlo z více portálů (`source_count` > 1). Web to označí. |
| `sources` | ano | Alespoň jeden zdroj. `name` z pole `source_name`, `url` **zkopírovaný** z pole `link`. **Nikdy URL neskládej, nezkracuj ani neopravuj** — vymyšlený odkaz je horší než žádná zpráva. |

## Počasí

Vydání vychází v 17:00, takže dnešní počasí už je čtenáři k ničemu.
Pole `weather` proto popisuje **zítřek a další dny** — dnešek (položka
s `"relative": "dnes"` ve `/tmp/weather.json`) se celý přeskakuje.

| Pole | Povinné | Význam |
| --- | --- | --- |
| `summary` | ano | 1–2 věty o **zítřku**: charakter počasí a denní teplota (`temp_max_c`), případně srážky, vítr nebo kvalita ovzduší. |
| `days` | ne | 3–4 dny **počínaje zítřkem** pro proužek předpovědi na webu. Dnešek ani dřívější den build skript nepřijme. |
| `icon` | ne | Ikona zítřka — zkopíruj `icon` u dne s `"is_tomorrow": true`. Povolené: `clear`, `partly`, `cloudy`, `fog`, `rain`, `snow`, `storm`. Když ho vynecháš, web vezme ikonu z `days[0]`. |
| `outlook` | ne | Jedna věta jen při výrazné situaci v dalších dnech (vedro nad 30 °C, silné bouřky, vydatný déšť, špatné ovzduší). Teploty a ikony ukazuje proužek sám — neopakuj je. |
| `place` | ne | Nech `"Hradec Králové"`. |

Položka v `days` má `date` (RRRR-MM-DD), `icon`, `temp_max_c` a volitelně
`temp_min_c` — všechno zkopírované z `/tmp/weather.json`. Názvy dnů
(„zítra", „pozítří", „pátek") si web dopočítá sám, do JSONu nepatří.

Kvalitu ovzduší ber z `air_quality` pro **zítřejší datum**, ne pro dnešek.

## Pořadí a rubriky

Položky v `items` seřaď po rubrikách v tomto pořadí:

`Domov` → `Hradec Králové` → `Svět` → `Ekonomika` → `Technologie` →
`Společnost a kultura` → `Za pozornost` → `Sport`

Rubriku, pro kterou nemáš zprávy, prostě vynech — web zobrazí jen ty, které
v datech jsou. `Za pozornost` je na analýzy a delší texty (typicky Voxpot,
Deník N), které nejsou zprávou dne, ale stojí za přečtení. `Hradec Králové`
je pro lokální dění z hradeckých zdrojů, `Technologie` pro Root.cz
a Hacker News (piš česky, i když je zdroj anglický).

V rámci rubriky řaď podle důležitosti, ne podle času. Při srovnatelné
důležitosti od nejnovějšího.

## Forma textu

Titulek nesmí být otázka ani teaser. Nepřebírej ho z portálu slovo od slova,
když je bulvární nebo nedopovězený — přepiš ho tak, aby sám nesl informaci.

Tělo je souvislý text, ne výčet. Když si dva zdroje protiřečí, napiš to
místo toho, abys jeden vybral: *„…podle ČT Sport a iROZHLAS třetí nejdražší
český fotbalista, E15 ho řadí na čtvrté místo."*

Do JSONu nepatří Markdown, HTML tagy ani uvozovky typu `"` uvnitř textu —
používej české `„“`.

## Po zapsání

Vždy spusť build a commitni obojí:

```bash
python3 scripts/build_site.py
```

Skript JSON zvaliduje a přegeneruje `docs/`. Když skončí chybou, oprav JSON
a spusť ho znovu — nikdy necommituj digest, který build neprošel.
