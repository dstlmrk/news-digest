# Nastavení cloud routiny

Repozitář je hotový, ale routinu musíš jednou založit ručně — a hlavně jí
**povolit síť na zpravodajské domény**, protože výchozí `Trusted` allowlist
obsahuje jen package registry, GitHub a cloud API. Bez toho každý fetch
feedu skončí `403` s hlavičkou `x-deny-reason: host_not_allowed`.

## 1. Cloud environment se sítí na zpravodajské servery

Na [claude.ai/code](https://claude.ai/code) klikni na ikonu cloudu nad
polem pro zprávu → **Add cloud environment**.

- **Name:** `news`
- **Network access:** `Custom`
- **Allowed domains:** zaškrtni *Also include default list of common
  package managers* a vlož:

  ```
  irozhlas.cz
  *.irozhlas.cz
  ceskatelevize.cz
  *.ceskatelevize.cz
  denikn.cz
  *.denikn.cz
  seznamzpravy.cz
  *.seznamzpravy.cz
  e15.cz
  *.e15.cz
  voxpot.cz
  *.voxpot.cz
  ```

- **Setup script:** nechej prázdný. `scripts/fetch_feeds.py` používá jen
  standardní knihovnu, takže se nic neinstaluje.

Kdykoli přidáš zdroj do `sources.toml`, přidej jeho doménu i sem.

## 2. Routina

Buď v CLI:

```
/schedule daily news digest at 7:00
```

nebo na [claude.ai/code/routines](https://claude.ai/code/routines) →
**New routine**. Nastav:

- **Repositories:** tenhle repozitář
- **Environment:** `news` z kroku 1
- **Trigger:** Schedule → `daily`, čas ve své lokální zóně
  (běh přijde o několik minut později kvůli staggeru)
- **Model:** na sumarizaci stačí Sonnet
- **Connectors:** **odeber všechny**, které nepotřebuješ. Routina je smí
  během běhu použít včetně zápisů, bez ptaní. Nech si jen Slack, pokud
  chceš doručovat do Slacku.

### Prompt routiny

```
Vyrob dnešní přehled zpráv podle CLAUDE.md a .claude/skills/digest/SKILL.md
v tomhle repozitáři. Postupuj podle sekce "Průběh běhu": sesbírej feedy,
přečti poslední tři digesty kvůli deduplikaci, narediguj, ulož jako JSON do
digests/, přegeneruj web přes scripts/build_site.py a commitni digests/
i docs/. Zdroje, které se nepodařilo načíst, dej do failed_feeds.
```

Prompt nech krátký a odkazuj se z něj do repa. Pravidla se pak mění
commitem, ne překlikáváním v UI.

## 3. GitHub Pages

Web je připravený v `docs/` a je potřeba Pages jen zapnout:

```bash
gh api -X POST repos/<uživatel>/news-digest/pages \
  -f 'source[branch]=master' -f 'source[path]=/docs'
```

Nebo v repozitáři: **Settings → Pages → Source: Deploy from a branch →
`master` / `/docs`**. Adresa pak bude `https://<uživatel>.github.io/news-digest/`.

> **Pozor na plán.** GitHub Pages pro **privátní** repozitář vyžaduje
> GitHub Pro / Team / Enterprise. Na free plánu API vrátí
> `422 Your current plan does not support GitHub Pages for this repository`.
> Buď repozitář zveřejni (digest obsahuje jen shrnutí a odkazy, žádné
> secrets — v `docs/` ani `digests/` nic tajného není), nebo si Pro pořiď.

Náhled bez Pages funguje i lokálně:

```bash
python3 scripts/build_site.py
python3 -m http.server 8791 --directory docs
```

## 4. Ověření prvních běhů

Klikni na **Run now** a **přečti si transcript**. Zelený status znamená jen
to, že session naběhla a skončila bez infrastrukturní chyby — *neznamená*,
že úkol dopadl dobře. Blokované requesty, chybějící tooly i špatný výstup
se poznají jen z transcriptu.

Prvních pět až sedm běhů kontroluj a doťukávej `sources.toml` (co chodí),
`CLAUDE.md` (co tě zajímá) a `SKILL.md` (jak to má vypadat).

Lokálně si vstup i web vyzkoušíš kdykoli:

```bash
python3 scripts/fetch_feeds.py --out /tmp/feed.json
python3 scripts/build_site.py && python3 -m http.server 8791 --directory docs
```

## Doručení mimo web

Web v `docs/` je hlavní čtecí plocha. Když chceš navíc notifikaci:

1. **Slack connector** — DM sám sobě s odkazem na dnešní vydání. Connector
   traffic jde přes servery Anthropicu, takže **nepotřebuje nic
   v allowlistu**. Na ranní čtení na telefonu nejpraktičtější.
2. **Transactional e-mail API** (Resend, Mailgun, SendGrid) přes `curl`:
   - přidej API doménu (např. `api.resend.com`) do allowlistu environmentu,
   - přidej klíč jako environment variable, např. `RESEND_API_KEY`,
   - dopiš do `CLAUDE.md` → *Doručení*, že se má e-mail poslat, a na jakou
     adresu.

   **Pozor:** cloud environment **není secrets store**. Dokumentace
   výslovně varuje, že proměnné vidí každý, kdo environment používá.
   U osobního environmentu jsi tam jen ty, ale použij klíč s co nejmenším
   oprávněním (jen odesílání) a měj možnost ho snadno zneplatnit.

## Limity, na které narazíš

- **Daily cap na počet běhů routin** na účet, navíc k běžným limitům
  předplatného. Jeden běh denně je hluboko pod ním.
- **Routina patří tvému osobnímu účtu**, nedá se sdílet s kolegy. Commity
  ponesou tvou GitHub identitu.
- **Research preview** — chování a limity se mohou změnit.
- Feedy občas vypadnou nebo se přejmenují. Skript to nezakryje: selhané
  zdroje reportuje a digest je zmíní na konci.
