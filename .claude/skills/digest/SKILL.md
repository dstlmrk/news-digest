---
name: digest
description: Formát denního přehledu zpráv - JSON schéma souboru v digests/ a redakční forma položek. Použij při psaní digestu v tomto repozitáři.
---

# Formát digestu

Digest se ukládá jako **JSON** do `digests/RRRR-MM-DD.json`. Z něj se
skriptem `scripts/build_site.py` generuje web do `docs/`. JSON je jediný
zdroj pravdy — HTML nikdy needituj ručně.

Redakční pravidla a limity jsou v `CLAUDE.md`. Tady je struktura a forma.

> **ŽELEZNÉ PRAVIDLO (viz `CLAUDE.md`): nic si nevymýšlej.** Každé tvrzení
> v `headline`, `body` i `highlights` musí být doslova doložené ve
> `feed.json` nebo v článku, který jsi v tomto běhu otevřel a přečetl.
> Každé `url` je kopie pole `link`, nikdy vlastní konstrukce. Co nemáš
> ve zdroji, do JSONu nepatří — bez výjimky.

## Schéma

```json
{
  "date": "2026-08-03",
  "window_hours": 24,
  "sources_used": ["iROZHLAS", "ČT24", "Deník N", "Seznam Zprávy", "E15"],
  "failed_feeds": [],
  "weather": {
    "place": "Hradec Králové",
    "icon": "cloudy",
    "summary": "Zataženo, 18 až 34 °C, beze srážek. Kvalita ovzduší zhoršená.",
    "outlook": "V úterý vedro až 38 °C, ve čtvrtek přijdou přeháňky a ochlazení na 28 °C."
  },
  "highlights": [
    "Jedna věta o nejdůležitější zprávě dne.",
    "Jedna věta o druhé."
  ],
  "items": [
    {
      "rubric": "Domov",
      "time": "11:11",
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
| `date` | ano | `RRRR-MM-DD`, dnešní datum v zóně Europe/Prague. Musí odpovídat názvu souboru. |
| `window_hours` | ano | Časové okno, ze kterého zprávy pocházejí. Ber z `feed.json`. |
| `sources_used` | ano | Názvy zdrojů, které do digestu **skutečně** přispěly. Ne celý seznam z configu. |
| `failed_feeds` | ano | Názvy feedů, které se nepodařilo načíst. Prázdné pole, když je vše v pořádku. |
| `weather` | ne | Počasí z `/tmp/weather.json` (viz krok 2 v CLAUDE.md). `summary` povinné (1–2 věty o dnešku), `outlook` jen při výrazné situaci v dalších dnech, `place` nech "Hradec Králové". `icon` zkopíruj z `days[0].icon` — povolené hodnoty: `clear`, `partly`, `cloudy`, `fog`, `rain`, `snow`, `storm`. Když počasí není k dispozici, celé pole vynech. |
| `highlights` | ne | 2–4 věty o nejdůležitějším. Bez odkazů. Když se nestalo nic zásadního, vynech nebo dej prázdné pole. |
| `items` | ano | Položky v pořadí, v jakém se mají zobrazit. |

### Pole položky

| Pole | Povinné | Význam |
| --- | --- | --- |
| `rubric` | ano | Přesně jedna z: `Domov`, `Hradec Králové`, `Svět`, `Ekonomika`, `Technologie`, `Společnost a kultura`, `Za pozornost`, `Sport`. Jiná hodnota build skript zastaví. |
| `time` | ano | `HH:MM`, čas vydání z pole `published` přepočtený na Europe/Prague. U témat z více zdrojů čas nejnovějšího. |
| `headline` | ano | Celá věta, která říká, co se stalo. Bez tečky na konci. |
| `body` | ano | 1–3 věty, u důležitých zpráv 4–8. Prostý text, jeden odstavec, bez Markdownu a bez odrážek. **Jen fakta doložená ve zdroji — nic z paměti, nic domyšleného.** |
| `cross_source` | ne | `true`, když téma přišlo z více portálů (`source_count` > 1). Web to označí. |
| `sources` | ano | Alespoň jeden zdroj. `name` z pole `source_name`, `url` **zkopírovaný** z pole `link`. **Nikdy URL neskládej, nezkracuj ani neopravuj** — vymyšlený odkaz je horší než žádná zpráva. |

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
