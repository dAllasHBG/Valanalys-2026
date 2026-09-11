# Valanalys 2026 🗳️

En Streamlit-dashboard för att följa opinionsläget inför det svenska riksdagsvalet
den **13 september 2026**, och (när Valmyndigheten börjar publicera data) det
officiella preliminära resultatet på valnatten.

## Innehåll

- **Valnatt** — nedräkning till att vallokalerna stänger, försök att hämta
  officiellt resultat från Valmyndigheten, och länkar till redaktioner som
  sänder valbevakning.
- **Tidslinje (Novus)** — opinionsutveckling över tid per parti, med filter
  och glidande medelvärde.
- **Egna block** — bygg valfria blockkonstellationer genom att dra partier
  mellan rutorna (kräver `streamlit-sortables`, se nedan), eller välj bland
  färdiga exempel som Alliansen, Storkoalition eller Mittenblock.
- **Mandatkollen** — interaktiv mandatberäkning med jämkade uddatalsmetoden
  (samma metod som används i riktiga riksdagsval, förenklad till nationell nivå).
- **Blocken** — stöd för Tidöpartierna respektive de rödgröna partierna över tid.
- **Valmyndigheten API** — teknisk vy för att felsöka API-anropet.

## ⚠️ Innan du kör den här på valnatten

`DEFAULT_VALMYNDIGHETEN_URL` i `app.py` är **inte verifierad** mot
Valmyndighetens faktiska produktions-URL för 2026 — den är satt som ett
rimligt exempel. Innan kvällen den 13 september bör du:

1. Kontrollera den riktiga adressen på [val.se](https://www.val.se) (t.ex.
   via nätverksfliken i webbläsarens devtools medan resultatsidan laddar).
2. Antingen uppdatera `DEFAULT_VALMYNDIGHETEN_URL` i koden, eller mata in
   rätt URL direkt i appens fält **"Valmyndighetens API-URL"** — det kräver
   ingen ny driftsättning.
3. Verifiera att fältnamnen i JSON-svaret matchar det appen letar efter
   (`förkortning`, `antalRöster`, `andelRöster`). Fliken **"Valmyndigheten
   API"** är till för just den typen av felsökning.

Appen är medvetet designad för att **aldrig hitta på siffror eller
nyheter**. Om det officiella resultatet inte går att hämta visas ett
tydligt "väntar på data"-läge istället för påhittade tal — det är avsiktligt,
inte en bugg.

## Köra lokalt

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Publicera

Enklast är [Streamlit Community Cloud](https://streamlit.io/cloud):
pusha till ett publikt GitHub-repo, koppla det på share.streamlit.io, och peka
på `app.py`.

## Licens / ansvarsfriskrivning

Opinionssiffrorna är manuellt inmatade från Novus och kan innehålla fel —
dubbelkolla alltid mot Novus originalkällor. Mandatberäkningen är en
förenklad, nationell approximation av det faktiska valsystemet och ska inte
tolkas som en prognos.
