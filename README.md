# Novellstudion

**Stil-RAG för svensk prosa.** Läs en samling noveller, mät stilen kvantitativt,
indexera texterna med BM25 och bygg färdiga prompts där modellen får ett stilkort,
autentiska utdrag och din uppgift.

Ren Python, inga tredjepartspaket, ingen GPU. Allt kör på CPU med
standardbiblioteket — SQLite med FTS5 gör sökningen.

---

## Vad det är

Novellstudion löser ett smalt problem: att få en språkmodell att skriva i **en viss
stil** utan att finjustera den.

En korpus på ett par tusen noveller är för liten för att lära en modell att skriva,
men stor nog att lära den en stil. Att lägga 3–5 autentiska utdrag i kontexten ger
oftast bättre stilåtergivning än en LoRA-träning på samma data — och det går att
mäta, ändra och förklara varje steg.

Verktyget **genererar ingen text själv**. Det producerar en färdig promptfil som du
skickar till valfri modell, och ett grafiskt gränssnitt som gör samma sak med
strömmande svar.

## Funktioner

- **Stilprofil som går att granska.** Meningslängd (snitt, median, p90), stycken,
  dialogandel, skiljeteckenfrekvens, vanligaste innehållsord och ordpar. Skrivs som
  `style-bible.md` (läsbar), `style-card.txt` (klistras in i prompten) och
  `metrics.json` (maskinläsbar).
- **BM25-sökning i SQLite FTS5.** Chunkning med ordgränser och överlapp, max N
  träffar per novell så att en enda text inte tar över resultatet.
- **Promptbygge.** Stilkort + representativa utdrag + din uppgift, i en fil.
- **Lokalt gränssnitt** på `127.0.0.1:8790` — formulär för scen, kategori, längd,
  ordlistor, mappväljare, strömmande generering och ett bibliotek över sparade texter.
- **LLM-klient** som talar llama.cpp, Ollama och OpenAI-format, inklusive servrar
  som kräver `--api-key`.
- **Skyddsnät** som karantänsätter material med åldersmarkörer (se nedan).
- **Bärbart.** Allt ligger i projektmappen; inget installeras, ingen databas startas.

## Snabbstart

Kräver Python 3.10 eller nyare. Inget annat.

```bash
git clone <repo-url> novellstudion
cd novellstudion

# 1. Bygg index ur demokorpusen (5 korta texter som följer med)
python -m src.cli build --corpus demo --db out/demo.db --out out

# 2. Se stilkortet
python -m src.cli stats --db out/demo.db

# 3. Sök
python -m src.cli search --db out/demo.db "regnet mot fönstret" -k 5

# 4. Bygg en prompt
python -m src.cli prompt "en scen i ett kök, två personer som inte säger vad de menar" \
  --db out/demo.db -k 3 --out out
```

`build` skriver tre filer i `out/`:

| Fil | Innehåll |
|---|---|
| `style-bible.md` | Full stilguide i Markdown — läs den själv |
| `style-card.txt` | Kompakt stilkort — klistras in i prompten |
| `metrics.json` | Alla mätvärden, maskinläsbara |

## Grafiskt gränssnitt

```powershell
.\starta-novellstudion.cmd      # Windows
```

```bash
python -m gui.server            # alla plattformar
```

Servern binder till `127.0.0.1` och öppnar webbläsaren. Allt körs i en enda
Python-process: gränssnittet, korpussökningen och anropet till modellen.
Dokumentation: [GUI.md](GUI.md).

## Egna texter

`demo/` räcker för att prova. Vill du använda ditt eget material finns två vägar:

**Som importerad HTML** (`tools/import_html.py`) — läser titel, författare, betyg
och kategori ur sidstrukturen och hämtar brödtexten rent, utan meny och sidfot.
Metadata sparas i `meta.jsonl`.

```bash
python tools/import_html.py --src "<mapp med html>" --out corpus-html --min-rating 4.5
```

**Som `.txt`-filer** — lägg dem i en mapp och peka `--build` dit. Rensningen i
`src/textutil.py` hanterar det mesta av webbrester, men HTML-importen är renare.

```bash
python -m src.cli build --corpus "<din mapp>" --db out/stil.db --out out
```

Korpusen ingår inte i repot. Lägg den i `corpus-html/` eller `corpus/` — båda är
gitignorade.

## Kommandon

| Kommando | Gör |
|---|---|
| `build` | Parsar korpus, bygger SQLite + FTS5-index, räknar stilprofil |
| `stats` | Skriver ut stilkortet för ett befintligt index |
| `search` | BM25-sökning, max N träffar per novell |
| `prompt` | Stilkort + utdrag + uppgift → färdig promptfil |
| `ask` | Skickar prompten till en LLM (Ollama eller OpenAI-format) och sparar svaret |

Flaggor för `build`: `--min-words`, `--target` (ord per chunk), `--max-words`,
`--overlap`, `--exclude <mapp>` (kan upprepas), `--no-guard`.

## Hur det fungerar

```
korpus ──> textutil ──> chunkar ──> SQLite FTS5 ──> BM25 ──┐
                │                                          ├──> prompt + stilkort
                └──> analyze ──> stilkort ─────────────────┘
```

```
novellstudion/
├── demo/               5 korta texter för rökprov (ingår)
├── src/
│   ├── textutil.py     normalisering, tokenisering, dialogmätning
│   ├── analyze.py      stilstatistik och stilkort
│   ├── index.py        SQLite + FTS5, chunkning, BM25
│   ├── safety.py       skyddsnät för åldersmarkörer
│   └── cli.py          kommandoradsgränssnitt
├── gui/
│   ├── server.py       lokal HTTP-server och API
│   ├── llm.py          klient för llama.cpp, Ollama, OpenAI
│   ├── rag.py          korpusåtkomst för gränssnittet
│   ├── prompting.py    promptbygge
│   ├── store.py        bibliotek och inställningar
│   └── static/         HTML, CSS, JS
├── tools/
│   ├── import_html.py  HTML-import med betygsfilter
│   └── probe*.py       felsökning av korpuskvalitet
├── novellstudion.py    startpunkt (även för exe-bygget)
├── Novellstudion.spec  PyInstaller
└── install.ps1 / .sh   verifierar Python, skapar startare, kör rökprov
```

Indexet är en enda SQLite-fil, så det går att flytta med. `insert into` sker i
transaktioner och `build` är idempotent — kör om när korpusen ändrats.

## Skyddsnät

Två lager, båda aktiva som standard:

1. **Kategori-exkludering.** Mappen `age play` / `ageplay` importeras eller
   indexeras aldrig. `--exclude` styr detta i `build`; `EXCLUDED_CATEGORIES` i
   `tools/import_html.py` styr det vid import.
2. **Skyddsnät (`src/safety.py`).** Filer med hårda åldersmarkörer karantänsätts
   och indexeras inte. Filnamnen skrivs till `out/quarantine.txt` så att de kan
   granskas manuellt. Filer med ordet "barn" flaggas mjukt till
   `out/review-manuellt.txt` — de utesluts inte automatiskt, eftersom ordet är
   vanligt i oskyldig prosa.

`--no-guard` stänger av karantänen. Kör den bara på material du själv gått igenom.

## Vad mätningen inte klarar

Det här är medvetet, och står i stilguiden:

- **Tempus** (preteritum/presens) mäts inte. Det kräver ordklasstaggning, och en
  gissning vore värre än ingen siffra.
- **Perspektiv** räknas på pronomen. Vid jämn fördelning rapporteras "blandat"
  hellre än att koden gissar.
- **Dialog** mäts radbaserat: en rad som börjar med `”` eller `–` räknas som replik.
  Källtexter blandar konventionerna, så siffran är en uppskattning.
- Siffrorna beskriver korpusen som helhet. Enskilda noveller kan avvika kraftigt.

## Vägen vidare om BM25 inte räcker

1. **Embeddings** — `bge-m3` via Ollama, hybridscore `0.7 * cosinus + 0.3 * bm25`.
2. **Stil-fingeravtryck** — välj utdrag som ligger nära stilkortet i meningslängd,
   dialogandel och ordval, inte bara i nyckelord.
3. **LoRA** — QLoRA r=32 på en 12B-basmodell. Kräver 24 GB VRAM eller hyrd GPU.
   Utvärdera med blind A/B mot basmodellen.

## Licens

MIT — se [LICENSE](LICENSE).
