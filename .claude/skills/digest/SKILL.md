---
name: digest
description: Formát denního přehledu zpráv ve stylu "rychlých zpráv". Použij při psaní souboru do digests/ v tomto repozitáři.
---

# Formát digestu

Styl vychází z „rychlých zpráv" na iROZHLAS: krátké samostatné položky,
každá s časem, tučným titulkem, několika větami a odkazem na zdroj.

Redakční pravidla a limity jsou v `CLAUDE.md`. Tady je jen forma.

## Struktura souboru

````markdown
# Rychlé zprávy · pondělí 3. srpna 2026

*18 zpráv · okno 24 h · iROZHLAS, ČT24, Deník N, Seznam Zprávy, Aktuálně.cz, Voxpot*

## Nejdůležitější

- Jedna věta o nejdůležitější zprávě dne.
- Jedna věta o druhé.
- Jedna věta o třetí.

---

## Domov

**13:03 — Bitcoinová kauza míří k soudu, obžalováni jsou čtyři lidé**
Žalobkyně z Vrchního státního zastupitelství v Olomouci podala obžalobu
ke Krajskému soudu v Brně. Podle náměstka vrchního žalobce je mezi
obžalovanými i exministr spravedlnosti.
[ČT24](https://…) · [Aktuálně.cz](https://…)

**11:20 — Další titulek jako celá věta**
Text zprávy.
[iROZHLAS](https://…)

## Svět

…

## Ekonomika

…

## Společnost a kultura

…

## Sport

**14:10 — Titulek**
Text.
[ČT Sport](https://…)

---

*Nepodařilo se načíst: Deník N Sport.*
````

## Pravidla formy

**Rubriky.** Používej jen ty, pro které máš zprávy — prázdnou rubriku
vynech. Pořadí je vždy: `Domov`, `Svět`, `Ekonomika`,
`Společnost a kultura`, `Sport`. Volitelně můžeš na konec před `Sport`
přidat `Za pozornost` pro analýzy a delší texty (typicky Voxpot, Deník N),
které nejsou zprávou dne, ale stojí za přečtení.

> Rubriky jsou odchylka od iROZHLASu, který má jeden chronologický proud.
> Při 25 položkách a čtení jednou denně se to čte lépe. Když chceš čistě
> chronologický proud, vypusť nadpisy rubrik a řaď všechno podle času
> od nejnovějšího.

**Položka.** Vždy přesně tři části v tomto pořadí, bez prázdného řádku
mezi nimi:

1. `**HH:MM — Titulek**` — čas vydání z pole `published` v čase
   Evropa/Praha. Titulek je celá věta bez tečky na konci.
2. Tělo: 1–3 věty, u důležitých zpráv 4–8. Žádné odrážky.
3. Řádek se zdroji: `[Název zdroje](url)`, více zdrojů oddělených ` · `.
   Název zdroje ber z pole `source_name`. Odkazy kopíruj z `link`.

Mezi položkami je jeden prázdný řádek.

**Řazení v rubrice.** Nejdůležitější první, ne nutně nejnovější. V rámci
srovnatelné důležitosti od nejnovějšího.

**Hlavička.** Datum česky a s názvem dne. Podtitulek uvádí počet zpráv,
časové okno a seznam zdrojů, které do digestu skutečně přispěly.

**Sekce „Nejdůležitější".** Dva až čtyři body, každý jedna věta, bez
odkazů — odkaz je u plné položky níž. Když se za den nestalo nic
zásadního, sekci vynech úplně.

**Poznámka o zdrojích.** Jen když nějaký feed selhal. Kurzívou, na konci,
za vodorovnou linkou. Nic jiného technického do digestu nepatří.
