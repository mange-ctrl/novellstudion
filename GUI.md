# Novellstudion — grafiskt gränssnitt

Ett fönster i webbläsaren ovanpå `stil-lab`. Du skriver scenen, väljer längd,
kategori, sexgrad och ord — och får en färdig novell tillbaka, strömmad direkt
från din LLM-server, med stilkort och autentiska utdrag ur korpusen som stöd.

Inget att installera: exe-filen har allt inbyggt. Källkörning kräver Python 3.10+.

---

## 1. Starta

Det finns två färdiga varianter i `dist\`:

| Fil | När |
|---|---|
| `dist\Novellstudion.exe` | **Rekommenderas.** En enda fil, allt inbyggt (index, stilkort, gränssnitt). |
| `dist\Starta Novellstudion.cmd` | Startar exe-filen med rätt arbetsmapp om ett dubbelklick på exe inte fungerar. |
| `dist\Novellstudion-portabel\Novellstudion-portabel.exe` | Använd den här mappen om en-filen inte startar (t.ex. företagets temp-spärr). Flytta hela mappen, inte bara exe-filen. |

Dubbelklicka på exe-filen. Ett konsolfönster öppnas, servern startar och
webbläsaren öppnas på:

```
http://127.0.0.1:8790/
```

Lämna fönstret öppet medan du arbetar. Stäng det (eller tryck `Ctrl+C`) när du är
klar. Servern lyssnar bara på din egen dator.

**Var hamnar filerna?** I en mapp som heter `Novellstudion-data` bredvid
exe-filen: noveller, `gui-state.json` och `gui-historik.json`. En-filen packar
upp sig själv i en tillfällig mapp **bredvid exe-filen** — därför måste exe-filen
ligga i en mapp du får skriva i (t.ex. `D:\gui-novell\dist`, inte Program
Files). Första starten kan ta några sekunder extra.

> Windows SmartScreen kan varna för att filen är okänd eftersom den inte är
> signerad. Välj **Mer information → Kör ändå**.

Vill du köra från källkoden i stället:

```powershell
starta-novellstudion.cmd
python -m gui.server --port 8800 --no-browser
```

Porten är 8790 som standard. Är den upptagen provas 8791, 8792 och så vidare.

---

## 2. Anslut till din LLM

Skriv adressen i fältet uppe till vänster och tryck **Anslut**.

| Server | Adress |
|---|---|
| llama.cpp | `127.0.0.1:8088` — eller `192.168.1.139:8089` på en annan dator |
| Ollama | `127.0.0.1:11434` |
| LM Studio | `127.0.0.1:1234` |
| vLLM, text-generation-webui | deras port, samma OpenAI-format |
| Moln (OpenAI, OpenRouter …) | full `https://`-adress + API-nyckel under **Avancerat** |

`http://` läggs till automatiskt. Gränssnittet provar `/v1/models`, `/api/tags`
och `/health` och visar servertyp, modell och kontextstorlek. Modellistan fylls
på och rätt modell väljs automatiskt — även när servern svarar med llama.cpp:s
utökade modellformat.

**Statuspricken** bredvid adressen: grön = ansluten, röd = ingen kontakt,
gul = ansluter.

### Kontexten är en hård gräns

Servern har ett kontextfönster (t.ex. 2 048 eller 16 384 tokens). Stilkort,
stilprover, din uppgift **och** svaret måste rymmas. Gränssnittet läser
kontextstorleken från `/props`, visar den i statusraden och varnar om den är
liten. Prompten och max tokens anpassas så att svaret inte kapas mitt i.

Är kontexten bara 2 048 tokens räcker den inte till tre stilprover och en hel
novell. Starta om llama.cpp med större kontext:

```text
-c 16384
```

eller `--ctx-size 16384`. Knappen **Anpassa** i varningen sänker då till
1 stilprov och 600 ord så att det ryms ändå.

### Resonerande modeller

Qwen3 m.fl. kan lägga hela svarsbudgeten på att "tänka" och lämna själva texten
tom. **Stäng av modellens resonemang** under **Avancerat** är ikryssad som
standard och skickar `enable_thinking: false` till llama.cpp.

---

## 3. Fälten

Överst i vänsterpanelen ligger **Scenen**, under den **Novellen** (kategori,
längd, sexgrad, ord) och sedan **Detaljer**, **Stil och utdrag**, **Var
novellen ska ligga** och **Avancerat**. Panelen scrollar.

### Scenen

| Fält | Exempel |
|---|---|
| **Vad ska hända?** | `Ett kök sent på kvällen. Två grannar som känt varandra i tio år.` |
| **Plats** | `ett kök, sent på kvällen` |
| **Personer** | `två grannar i fyrtioårsåldern` |
| **Det som står på spel** | `hon har bestämt sig för att säga något, han vet det inte` |

### Novellen

| Fält | Gör |
|---|---|
| **Kategori** | Styr vilka stilprover som hämtas. `Alla kategorier` blandar fritt. |
| **Längd** | 300–5 000 ord. Snabbval: 600, 1 200, 2 500, 4 000. |
| **Sexgrad 1–5** | Se tabellen nedan. |
| **Sexuella ord** | Klickbara brickor per nivå. Klicka för att ta med, klicka igen för att ta bort. Egna ord läggs till med Enter. Listan scrollar. |
| **Undvik ord** | Kommaseparerad lista som modellen ombeds undvika (under en egen rubrik). |

### Sexgraden

| Nivå | Namn | Innebörd |
|---|---|---|
| 1 | Mild | Antydan. Blickar, andning, det som inte sägs. Inga explicita kroppsdelar. |
| 2 | Sinnlig | Förspel. Kyssar, händer, kläder som glider undan. |
| 3 | Tydlig | Samlaget skildras, men språket håller igen. |
| 4 | Explicit | Rakt språk om kropp och samlag. Konkreta ord. |
| 5 | Rå | Grovt och direkt, utan omskrivningar. Fortfarande prosa. |

Nivån påverkar både instruktionen till modellen och vilka ord som erbjuds.
Orden är förslag — du kan lägga till egna och ta bort alla.

### Detaljer

| Fält | Exempel |
|---|---|
| **Ton** | lågmäld, varm, kylig, rå, ömsint, lekfull, mörk, melankolisk, spänd |
| **Slut** | öppet, lyckligt, mörkt, oväntat, eftertänksamt |
| **Perspektiv** | låt stilen avgöra, jag, han, hon, du |
| **Tempus** | låt stilen avgöra, dåtid, nutid |
| **Dialog** | som stilen, sparsam, måttlig, dialogtung |
| **Titel** | valfri — används i filnamn och rubrik |
| **Extra instruktion** | allt som inte får plats ovan |

> **Tips:** konkreta ord ger bättre stilprover. BM25 letar ord, inte betydelse
> (det står i [KOMMA-IGANG.md](KOMMA-IGANG.md) varför). `köket`, `regnet`,
> `grannarna` fungerar bättre än `en känsla av närhet`.

### Stil och utdrag

| Fält | Standard | Gör |
|---|---|---|
| **Antal stilprover** | 3 | 0–6. Fler = närmare stilen, längre prompt. |
| **Max per novell** | 1 | Spridning: högst 1–3 utdrag från samma novell. |
| **Bara vald kategori** | på | Annars kan prover från andra kategorier smyga in. |
| **Använd stilkortet** | på | Mätta siffror om meningslängd, dialog och ordval. |
| **Visa stilkortet** | — | Läser in `out/style-card.txt`. |

Fliken **Stilprover** visar de utdrag som faktiskt används. Bocka av ett utdrag
för att utesluta det och bygga om prompten. Sökfältet längst upp låter dig söka
egna ord i korpusen — bra när scenen är abstrakt.

### Var novellen ska ligga

| Fält | Gör |
|---|---|
| **Mapp** | Absolut sökväg eller relativ till projektmappen. |
| **Bläddra…** | Klickbar mappväljare med snabbplatser, enheter och "Skapa mapp". |
| **Filnamn** | Tomt = automatiskt: `2026-11-06-1414-koket-sent.md`. |
| **Spara automatiskt** | Skriver filen direkt när texten är klar. |
| **Öppna mappen** | Visar mappen i Utforskaren. |

Standardmappen är `Novellstudion-data\noveller` bredvid exe-filen (i
källkörning `out/noveller`). Allt sparas som Markdown med en liten frontmatter
(titel, datum, kategori, sexgrad, ord, modell, server, antal prover).

### Avancerat

Temperatur (0,1–1,5), top-p, max tokens (`0` = automatiskt utifrån längden),
seed (tomt = slumpen), upprepningsstraff, API-nyckel för molnservrar och
**Stäng av modellens resonemang** (på som standard).

Upprepningsstraffet är **1,20** som standard. Värden nära 1,0 gör att små
modeller lätt skriver samma stycke om och om igen. Gränssnittet höjer i så fall
till minst 1,10 och skickar dessutom DRY-sampling till llama.cpp, vilket bryter
upprepningar effektivt.

Har din llama.cpp startats med `--api-key` svarar `/health` men `/v1/models`
returnerar 401. Gränssnittet säger då **API-nyckel krävs**, öppnar **Avancerat**
och sätter markören i nyckelfältet. Nyckeln är värdet som står efter `--api-key`
i serverns startkommando. Fyll i den och tryck **Anslut** igen.

Nyckeln sparas bara om du kryssar i **Kom ihåg nyckeln på den här datorn** — då
hamnar den i `gui-state.json` i data-mappen på din egen disk. Annars lever den
bara i webbläsarens minne under sessionen.

---

## 4. Skriv

Tryck **Skriv novell** (eller `Ctrl+Enter`). Texten strömmar in i pappersarket.
Under tiden:

- **Stopp** avbryter; det som hunnit skrivas finns kvar.
- **Upprepningsskydd.** Om modellen börjar skriva samma stycke igen stoppas
  genereringen och texten kapas före upprepningen. En varning visas; det som
  står kvar är sammanhängande och kan sparas eller fortsättas.
- **Fortsätt på texten** skickar det som redan står som sammanhang och fortsätter
  exakt där det slutade. Fungerar även på en text du läst in från biblioteket.
  Autosparande skriver då en ny fil med hela texten — originalet rörs inte.
- **Redigera** gör papperet redigerbart. Ändra direkt i texten och tryck **Klar**;
  spara, kopiera och fortsätt använder den redigerade versionen.
- **Spara** skriver en ny fil även om autosparande är på.
- **Kopiera** och **Ladda ner** tar texten vidare.
- **Töm** rensar rutan (frågar först).

Flikarna till höger:

| Flik | Innehåll |
|---|---|
| **Text** | Novellen, i läsbart skick. |
| **Prompt** | Exakt vad modellen får. Går att redigera — bocka i *Använd den redigerade prompten* för att skicka den istället. |
| **Stilprover** | Utdragen som används, med titel, kategori, betyg och BM25-poäng. |

### Bibliotek

Knappen **Bibliotek** visar sparade texter med datum, ordantal och kategori.
Klicka för att läsa in texten igen. **Mapp** visar filen i Utforskaren.
**Ta bort** tar bort posten ur listan — filen ligger kvar på disken.

---

## 5. Vad som händer under huven

```
formulär  →  scenbeskrivning + kategori + sexgrad + ord
                    │
                    ▼
        BM25 mot 1 471 noveller  →  3 utdrag
                    │
                    ▼
   stilkort + utdrag + uppgift + regler  →  prompt
                    │
                    ▼
        din LLM-server (llama.cpp / Ollama / OpenAI-format)
                    │
                    ▼
        strömmad text  →  pappersarket  →  .md i vald mapp
```

Prompten innehåller alltid:

- en systemroll som säger att alla personer är vuxna och att texten ska vara
  färdig prosa, inte en plan;
- stilkortet (mätta siffror, inga påhitt);
- stilproverna, tydligt märkta som stil — inte handling;
- din uppgift, sexgradens instruktion, ordlistorna och längden.

Skyddsnätet är aktivt i två lager: kategorier med minderåriga är borta ur
indexet, och varje utdrag kontrolleras en sista gång innan det hamnar i en
prompt. Utdrag som nämner en minderårig ålder filtreras bort och räknas i
anteckningen under fliken **Stilprover**.

---

## 6. Felsökning

| Symptom | Orsak | Lösning |
|---|---|---|
| `Ingen LLM-server svarade` | Servern kör inte, eller fel port | Starta llama.cpp/Ollama, kontrollera adressen |
| `API-nyckel krävs` / `HTTP 401` | Servern startades med `--api-key` | Fyll i nyckeln under **Avancerat** och tryck **Anslut** |
| `Prompten tar … av serverns … tokens` | Kontextfönstret är för litet | Starta llama.cpp med `-c 16384`, eller tryck **Anpassa** i varningen |
| `Modellen returnerade ingen text` | Modellen är resonerande (Qwen3 m.fl.) eller modellnamnet är fel | Kryssa i **Stäng av resonemang**; välj modell i listan |
| Texten blir avhuggen | max tokens eller kontextfönstret | Höj `-c`, höj **Max tokens** eller sänk längden |
| Texten upprepar sig | För lågt upprepningsstraff, hög temperatur eller liten modell | Höj upprepningsstraffet mot 1,2–1,3 och sänk temperaturen; appen stoppar också texten före en upprepning |
| `Could not create temporary directory` | Exe-filen ligger i en mapp som inte går att skriva i | Flytta exe-filen till t.ex. `D:\Novellstudion` eller använd `dist\Novellstudion-portabel\Novellstudion-portabel.exe` |
| Modellen vägrar | Instruct-modell trimmad mot explicit innehåll | Använd en modell avsedd för skönlitteratur, eller sänk sexgraden |
| `Texten kunde inte sparas` | Mappen finns inte eller är skrivskyddad | Välj en annan mapp med **Bläddra…** |
| Inga stilprover | BM25 hittar inga ord | Skriv konkreta ord, eller stäng av kategorifiltret |
| Svenska tecken blir fel | Gammal webbläsare | Använd Edge, Chrome eller Firefox |

Loggen syns i det svarta fönstret där servern startade. Varje anrop skrivs med
tid, metod och status.

---

## 7. Bra att veta

- **Ingen text lämnar datorn** förutom till den LLM-adress du själv anger.
- **Nollställ** i överraden rensar inställningar, historik och 18+-spärren.
  Novellfilerna raderas aldrig: de flyttas till en daterad mapp
  (`noveller-fore-nollstallning-…`) bredvid novellmappen, så allt går att
  plocka tillbaka.
- **Alla figurer är vuxna.** Systemprompten säger det, och gränssnittet är
  märkt 18+.
- **Inget skrivs över.** Autosparande skapar ett nytt filnamn om det redan finns.
- **Indexet är detsamma som CLI:t använder.** Bygger du om `out/stil.db` med
  `stil build` följer källkörningen med — stilkortet räknas om vid behov.
- **En-filen packar upp sig själv** i en tillfällig mapp bredvid exe-filen vid
  varje start. Därför kan första starten ta några sekunder, och exe-filen måste
  ligga i en skrivbar mapp. Den portabla mappen startar snabbare och packar inte
  upp något alls.
- **Data-mappen ligger bredvid exe-filen.** Flyttar du exe-filen, flytta gärna
  `Novellstudion-data` med — annars börjar programmet på en tom historik.
- **Inga beroenden.** Gränssnittet är HTML, CSS och JavaScript; servern är
  inbyggd i exe-filen. Ingen Python-installation behövs.
- **Bygga om exe-filen** kräver Python 3.10+ och PyInstaller:
  `python -m pip install pyinstaller`, sedan `bygg-exe.cmd`. Index och
  metadata läses in i bygget; kör om bygget efter en ny `build` av korpusen.

---

## 8. API (för den nyfikne)

Servern har ett litet JSON-API. Allt lyssnar på `127.0.0.1`.

| Metod | Väg | Gör |
|---|---|---|
| GET | `/api/bootstrap` | Kategorier, stilkort, inställningar, historik |
| POST | `/api/llm/probe` | Identifierar server och modeller |
| POST | `/api/prompt` | Bygger prompt + hämtar utdrag |
| POST | `/api/rag/search` | BM25-sökning med kategorifilter |
| POST | `/api/generate` | Strömmar genereringen (SSE) |
| POST | `/api/save` | Sparar text som Markdown |
| GET | `/api/history` | Sparade texter |
| GET | `/api/fs/list?path=` | Mappvy för väljaren |
| POST | `/api/fs/mkdir` | Skapar mapp |
| POST | `/api/fs/reveal` | Öppnar i Utforskaren |
| POST | `/api/state` | Sparar formulärinställningar |
| POST | `/api/reset` | Nollställer inställningar och historik; novellerna flyttas till en backup-mapp |

Ingen autentisering: servern binder till `127.0.0.1` och ska inte exponeras mot
nätet. Vill du köra den på en annan dator, sätt upp en proxy med lösenord i
stället för att byta `--host`.
