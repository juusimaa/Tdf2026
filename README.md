# Tour de France 2026 — automaattisesti päivittyvä tulossivu

Kokonaisuus koostuu kolmesta osasta:

```
index.html                        # sivu (etapit + tulokset -välilehdet)
data/results.json                 # automaattisesti päivittyvä tulosdata
scripts/fetch_results.py          # hakuskripti (procyclingstats-paketti)
.github/workflows/update-results.yml  # ajastettu GitHub Actions -workflow
```

## Miten automaatio toimii

1. GitHub Actions käynnistää workflow'n ajastetusti (30 min välein klo
   17–23 Suomen aikaa heinäkuussa, kun etapit päättyvät).
2. Workflow ajaa `fetch_results.py`-skriptin, joka hakee procyclingstats.com-
   sivustolta viimeisimmän ajetun etapin jälkeiset tilanteet: kokonaiskilpailu,
   piste-, mäki-, nuorten- ja joukkuekilpailu sekä etappivoittajat.
3. Skripti kirjoittaa `data/results.json`-tiedoston. Jos data muuttui,
   workflow commitoi sen repoon.
4. GitHub Pages tarjoilee sivun, ja `index.html` lukee JSONin selaimessa
   (`fetch('data/results.json')`). Sivu näyttää siis aina tuoreimman
   commitoidun tilanteen ilman käsityötä.

Lisäksi sivu valitsee **päivän etapin automaattisesti** avattaessa
(lepopäivinä seuraavan etapin, kisan jälkeen päätösetapin).

## Käyttöönotto (kertaluontoinen, ~10 min)

1. Luo uusi **julkinen** GitHub-repo (julkisissa repoissa Actions-minuutit
   ovat rajattomat; yksityisissä free-tierissä 2 000 min/kk).
2. Kopioi tämän paketin tiedostot repoon ja pushaa `main`-haaraan.
   Ajastetut workflow't toimivat vain oletushaarassa.
3. Ota GitHub Pages käyttöön: *Settings → Pages → Source: Deploy from a
   branch → main / root*.
4. Testaa heti: *Actions → Päivitä TdF-tulokset → Run workflow*
   (`workflow_dispatch`). Tarkista että `data/results.json` ilmestyy/päivittyy.
5. Avaa sivu osoitteessa `https://<käyttäjä>.github.io/<repo>/`.

## Hyvä tietää — rajoitukset ja varoitukset

- **Cron ei ole täsmällinen.** GitHub jonottaa ajastetut ajot; 10–30 min
  viiveet ovat tavallisia ruuhka-aikoina. Siksi ajo on 30 min välein usean
  tunnin ikkunassa yksittäisen kellonajan sijaan.
- **60 päivän sääntö:** jos repossa ei ole aktiivisuutta 60 päivään, GitHub
  kytkee ajastetut workflow't pois päältä (sähköposti-ilmoitus tulee).
  Tour kestää 3 viikkoa, joten tämä ei ehdi vaikuttaa — mutta jos haluat
  käyttää samaa pohjaa Vueltaan syyskuussa, tee välissä jokin commit.
- **procyclingstats on epävirallinen scraper.** PCS:llä ei ole virallista
  APIa, ja sivurakenteen muuttuessa parsinta voi hajota. Skripti sietää
  yksittäisten kategorioiden virheet (varoitus lokiin, muu data päivittyy),
  ja korjaus on yleensä `pip install procyclingstats --upgrade`.
  Ole kohtuullinen hakutiheydessä — tämä asetus tekee ~15 hakua/vrk,
  mikä on maltillista.
- **file://-avaus:** jos avaat index.html:n suoraan levyltä, selain estää
  fetch-kutsun (CORS), ja sivu näyttää sisäänrakennetun tyhjän tilan.
  Automaattipäivitys edellyttää siis http(s)-tarjoilua (GitHub Pages,
  tai paikallisesti `python -m http.server`).

## Vaihtoehtoiset toteutukset (jos et halua GitHubia)

- **Cloudflare Workers + Cron Triggers:** sama logiikka JS:llä, JSON
  KV-varastoon; ilmainen taso riittää. Enemmän koodattavaa kuin ylläoleva.
- **Kotipalvelin/NAS + cron:** `fetch_results.py` cronilla ja tiedostot
  vaikka pCloud-julkisjakoon — toimii, mutta vaatii aina päällä olevan koneen.
- **Puoliautomaattinen:** aja skripti läppärillä etapin jälkeen ja pushaa —
  automaation arvo on lähinnä siinä, ettei tätä tarvitse muistaa.
