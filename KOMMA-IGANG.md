# Komma igång med stil-lab — på en ny dator

Det här dokumentet är hela vägen: från en zip-fil på ett USB till en färdig text
skriven av en språkmodell i din korpus stil.

Läs avsnitt 1–4 första gången. Sedan är det avsnitt 6 och 7 du kommer att leva i.

---

## 0. Vad det här är — och inte är

`stil-lab` är ett **RAG-verktyg för stil**, inte en språkmodell.

Det gör fyra saker:

1. Letar upp de mest relevanta utdragen ur dina 1 471 noveller.
2. Mäter hur din korpus faktiskt skriver (meningslängd, dialog, perspektiv, ordval).
3. Bygger en färdig prompt av stilkkortet + utdragen + din uppgift.
4. Skickar prompten till en LLM — lokal eller i molnet — och sparar svaret.

Det **skriver ingen text själv**. Det ger modellen rätt förutsättningar att göra det.

---

## 1. Vad du behöver

| Krav | Detalj |
|---|---|
| Operativsystem | Windows 10/11, Linux eller macOS |
| Python | **3.10 eller nyare** (inget annat paket behövs) |
| Diskutrymme | ca 200 MB uppackat |
| LLM | Valfritt: Ollama lokalt, eller en API-nyckel |

Kontrollera Python:

```powershell
python --version
```

Får du `3.10` eller högre är du klar. Annars: https://www.python.org/downloads/
(kryssa i **"Add python.exe to PATH"** under installationen).

---

## 2. Flytta paketet

Kopiera `stil-lab-portable.zip` (55 MB) till den nya datorn — USB, extern disk
eller lokalt nätverk.

> **Viktigt:** zip-filen innehåller explicit material från 1 471 noveller.
> Lägg den inte på Google Drive, OneDrive eller någon delad yta.

Packa upp:

```powershell
Expand-Archive stil-lab-portable.zip -DestinationPath stil-lab
cd stil-lab
```

Linux/macOS:

```bash
unzip stil-lab-portable.zip -d stil-lab
cd stil-lab
```

---

## 3. Installera

**Windows** (PowerShell, i mappen du packade upp till):

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

**Linux/macOS:**

```bash
sh install.sh
```

Skriptet gör tre saker:

1. Letar upp Python 3.10+ och säger vilken version den hittade.
2. Skapar startaren `stil.cmd` (Windows) eller `./stil` (Linux/macOS).
3. Kör ett rökprov mot indexet och skriver ut ditt stilkort.

Förväntad utskrift:

```
  stil-lab
  --------------------------------------------------

  Python 3.14 hittad (python)
  Startare skapad: stil.cmd

  Rökprov:
STILKORT (härlett ur korpusen, inte påhittat):
- Perspektiv: första person.
- Meningslängd: i snitt 15.0 ord, median 13, p90 27. ...
```

Ser du stilkortet är allt klart.

---

## 3b. Den enkla vägen: grafiskt gränssnitt

Vill du slippa kommandon finns allt i ett fönster i webbläsaren. Det finns två
färdiga varianter i `dist\`:

- **`Novellstudion.exe`** — en enda fil med allt inbyggt (rekommenderas).
- **`Novellstudion-portabel\Novellstudion-portabel.exe`** — en mapp, om en-filen
  inte startar på din dator.

Dubbelklicka på exe-filen. Servern startar och webbläsaren öppnas på
`http://127.0.0.1:8790/`. Ingen Python-installation behövs.

I gränssnittet:

1. Skriv LLM-adressen högst upp, t.ex. `192.168.1.139:8089`, och tryck **Anslut**.
2. Välj kategori, längd och sexgrad 1–5.
3. Klicka på de sexuella ord du vill ha med (eller skriv egna).
4. Beskriv scenen — en rad räcker.
5. Välj mapp med **Bläddra…** och tryck **Skriv novell**.

Texten strömmar in i pappersarket, sparas automatiskt i mappen du valde och
hamnar i **Bibliotek**. Där finns också **Fortsätt på texten** och möjligheten
att läsa och redigera hela prompten innan den skickas.

> **Har din server liten kontext?** Gränssnittet varnar och visar hur du startar
> om llama.cpp med `-c 16384`. Utan det ryms inte stilprover + en hel novell.

Hela fältguiden, sexgradstabellen och felsökningen finns i **[GUI.md](GUI.md)**.
Resten av det här dokumentet beskriver kommandoraden — samma motor, samma index.

---

## 4. Verifiera

```powershell
.\stil.cmd stats
.\stil.cmd search "regnet mot fonstret sent pa kvallen" -k 5
```

`search` ska ge dig fem utdrag ur korpusen med titel och poäng.
Får du inga träffar: se avsnitt 10.

> **Tips om svenska tecken.** I Windows `cmd` kan `å ä ö` bli fel i kommandon.
> Använd **Windows Terminal** eller skriv `chcp 65001` först. I PowerShell går det bra.

---

## 5. Så hänger det ihop

```
corpus-html/  ──►  chunkar (≈220 ord)  ──►  SQLite FTS5 (BM25)
                                                    │
din uppgift  ──────────────────────────────────────►│
                                                    ▼
                                    stilkort + 3 utdrag + uppgift
                                                    │
                                                    ▼
                                    ┌───────────────────────────┐
                                    │  LLM (Ollama / API)       │
                                    └───────────────────────────┘
                                                    │
                                                    ▼
                                          out/svar-*.md
```

**Stylkortet** är mätta siffror, inte påhittade:

| Rad | Betydelse |
|---|---|
| Perspektiv | Vilket pronomen som dominerar (jag/han/du) |
| Meningslängd | Snitt, median, p90 — och andelen korta/långa meningar |
| Stycken | Snitt antal ord per stycke |
| Dialog | Andel av texten som är replik (rad som börjar med `”` eller `–`) |
| Skiljetecken | Per 1 000 ord — avslöjar rytm och andning |
| Ordpar | Återkommande fraser i korpusen |

Det är därför prompten inte behöver säga "skriv som en svensk erotisk novell" —
den säger *exakt* hur din korpus skriver.

---

## 6. Skriva prompten (det här är själva hantverket)

Du skriver **bara uppgiften**. Stilkort och utdrag läggs till automatiskt.
Uppgiften är en beskrivning av scenen — inte en instruktion om stil.

### 6.1 Vad en bra uppgift innehåller

| Del | Exempel |
|---|---|
| Plats | "ett kök, sent på kvällen" |
| Personer | "två grannar som känt varandra i tio år" |
| Vad som står på spel | "hon har bestämt sig för att säga något, han vet det inte" |
| Ton | "lågmäld, inte brådskande" |
| Vad som ska hända | "scenen slutar utan att något blir sagt" |

### 6.2 Dålig och bra uppgift

**Svag:**
```
skriv en sexscen
```
Modellen får inget att hålla i — resultatet blir generisk porr, inte din stil.

**Stark:**
```
En scen i ett kök sent på kvällen. Två grannar som känt varandra i tio år.
Hon har bestämt sig för att säga något. Han vet det inte. Lågmäld ton, inga
stora gester. Scenen slutar utan att det blir sagt.
```

### 6.3 Var du skriver den

**Alternativ A — direkt i kommandot** (enkelt, men fumligt med citattecken):

```powershell
.\stil.cmd prompt "En scen i ett kök sent på kvällen..." --out out
```

**Alternativ B — i en fil** (rekommenderas för längre uppgifter):

Skapa `min-uppgift.txt` och skriv uppgiften där, vanlig text. Sedan:

```powershell
.\stil.cmd prompt "$(Get-Content min-uppgift.txt -Raw)" --out out
```

> **Rekommendation:** använd alternativ A för korta tester, och `ask --from-file`
> (avsnitt 7.4) när du vill skicka en redigerad promptfil direkt.

### 6.4 Var prompten hamnar

```powershell
.\stil.cmd prompt "din uppgift" --out out
```

Skriver `out/prompt-<första orden>.md`. Öppna den i en editor och läs igenom —
det är den texten som går till modellen. Cirka 5 000 tecken: stilkort + 3 utdrag
+ din uppgift.

Justera med flaggor:

| Flagga | Standard | Gör |
|---|---|---|
| `-k 3` | 3 | Antal utdrag. Fler = starkare stil, längre prompt |
| `--per-story 1` | 1 | Max utdrag per novell (spridning) |
| `--length 600` | 600 | Antal ord modellen ska sikta på |

---

## 7. Köra mot en LLM

Fyra vägar. Välj en.

### 7.1 Ingen LLM alls — klistra in manuellt

Enklast, fungerar direkt, kräver inget mer:

```powershell
.\stil.cmd prompt "din uppgift" --out out
```

Öppna `out/prompt-*.md`, kopiera hela innehållet, klistra in i ChatGPT, Claude,
DeepSeek eller vad du har. Klart.

Nackdel: du gör det för hand varje gång.

---

### 7.2 Lokalt med Ollama (rekommenderas)

Gratis, privat, ingen data lämnar datorn.

**Steg 1 — installera Ollama:** https://ollama.com/download

**Steg 2 — hämta en modell.** Välj efter din hårdvara:

| Modell | Storlek | Kommentar |
|---|---|---|
| `qwen2.5:7b` | ≈4,7 GB | Säker på 8 GB VRAM. Bra svenska. |
| `mistral-nemo` | ≈7,1 GB | Bäst svenska av dessa, men trångt på 8 GB |
| `llama3.1:8b` | ≈4,9 GB | Bra allround |

```powershell
ollama pull qwen2.5:7b
```

**Steg 3 — kontrollera att servern kör:**

```powershell
ollama list
```

Får du "could not connect": starta Ollama-appen, eller kör `ollama serve` i ett
eget terminalfönster.

**Steg 4 — kör:**

```powershell
.\stil.cmd ask "En scen i ett kök sent på kvällen..." --model qwen2.5:7b
```

Svaret skrivs ut i terminalen **och** sparas i `out/svar-<orden>.md`.

Flaggor:

```powershell
.\stil.cmd ask "din uppgift" `
  --model qwen2.5:7b `
  -k 4 `
  --length 800 `
  --temperature 0.9 `
  --max-tokens 1600
```

| Flagga | Standard | Effekt |
|---|---|---|
| `--model` | — | Krävs. Namnet från `ollama list` |
| `-k` | 3 | Fler utdrag = närmare stilen |
| `--length` | 600 | Ordantal modellen siktar på |
| `--temperature` | 0.85 | Lägre = tryggare, högre = vildare |
| `--max-tokens` | 1200 | Hård gräns för svarslängd |
| `--base-url` | `127.0.0.1:11434` | Om Ollama kör på annan port/maskin |

> **Räkna med refusals.** Vanliga instruct-modeller är trimmade att vägra
> explicit innehåll. För explicita scener behöver du en modell avsedd för
> skönlitteratur, eller hålla scenen implicit. Det är modellens beteende, inte
> verktygets — `stil-lab` skickar bara texten.

---

### 7.3 Moln-API (OpenAI-kompatibelt)

Fungerar med OpenAI, OpenRouter, Groq, Together m.fl.

**Steg 1 — sätt nyckeln** (en gång, i ett nytt fönster):

```powershell
setx OPENAI_API_KEY "sk-din-nyckel"
```

Stäng och öppna terminalen igen.

**Steg 2 — kör:**

```powershell
.\stil.cmd ask "din uppgift" --backend openai --model gpt-4o-mini
```

Mot en annan leverantör:

```powershell
.\stil.cmd ask "din uppgift" `
  --backend openai `
  --base-url https://openrouter.ai/api `
  --model anthropic/claude-3.5-sonnet `
  --api-key "din-nyckel"
```

---

### 7.4 LM Studio och andra lokala servrar

LM Studio exponerar ett OpenAI-kompatibelt API på port 1234:

```powershell
.\stil.cmd ask "din uppgift" `
  --backend openai `
  --base-url http://127.0.0.1:1234 `
  --model "den-modell-du-laddat" `
  --api-key none
```

Samma sak funkar mot text-generation-webui, vLLM, llama.cpp-server — allt som
talar OpenAI-format.

---

### 7.5 Skicka en redigerad promptfil

Om du byggt en prompt, ändrat i den för hand, och vill köra den:

```powershell
.\stil.cmd prompt "din uppgift" --out out
notepad out\prompt-din-uppgift.md
.\stil.cmd ask --from-file out\prompt-din-uppgift.md --model qwen2.5:7b
```

Det här är det mest flexibla arbetssättet: du ser exakt vad modellen får.

---

## 8. Arbetsflödet som faktiskt fungerar

1. **Skriv uppgiften** — plats, personer, insats, ton.
2. **`ask`** med `-k 3`, `--temperature 0.85`.
3. **Läs svaret.** Nästan allt blir mediokert första gången. Det är normalt.
4. **Justera en sak i taget:**
   - Stilen för svag → höj `-k` till 5.
   - För långt/för kort → ändra `--length`.
   - Förutsägbart → höj `--temperature` till 1.0.
   - För rörigt → sänk till 0.7.
5. **Spara det som funkar.** `out/svar-*.md` skrivs över vid samma uppgift —
   döp om filen när du vill behålla den.

---

## 9. Kommandoreferens

| Kommando | Gör |
|---|---|
| `stil stats` | Visa stilkkortet |
| `stil search "ord" -k 5` | Sök i korpusen (BM25) |
| `stil prompt "uppgift" --out out` | Bygg promptfil |
| `stil ask "uppgift" --model X` | Bygg + skicka till LLM + spara svar |
| `stil build --corpus mapp` | Bygg om indexet från en ny mapp |

`stil` = `.\stil.cmd` på Windows, `./stil` på Linux/macOS.

---

## 10. Om något går fel

| Symptom | Orsak | Lösning |
|---|---|---|
| `Kunde inte nå http://127.0.0.1:11434` | Ollama kör inte | Starta Ollama-appen eller `ollama serve` |
| `model not found` | Modellen är inte nedladdad | `ollama pull <namn>` |
| `Inga träffar` | BM25 kräver ordöverlapp | Använd ord som faktiskt finns i texterna |
| `Python 3.10 eller nyare hittades inte` | Fel Python eller ej i PATH | Installera om med "Add to PATH" |
| `'stil.cmd' is not recognized` | Du står i fel mapp | `cd` till mappen med `stil.cmd` |
| Svenska tecken blir `ö` | Konsolens teckenkodning | Använd Windows Terminal, eller `chcp 65001` |
| `HTTP 401` | Fel/saknad API-nyckel | Sätt `OPENAI_API_KEY` igen, nytt fönster |
| Svaret blir avhugget | `--max-tokens` för lågt | Höj till 2000 |

---

## 11. Lägga till egna texter

```powershell
# lägg .txt-filer i en mapp, t.ex. mina-texter/
.\stil.cmd build --corpus mina-texter --db out\stil.db --out out
```

Det bygger om indexet och stilguiden från grunden. `--exclude "katalog"` hoppar
över en underkatalog; skyddsnätet (`src/safety.py`) är på som standard och
karantänsätter filer med åldersmarkörer till `out/quarantine.txt`.

Använd **inte** `--no-guard` på material du inte själv gått igenom.

---

## 12. Säkerhet — det här gäller

- Kategorierna `age-play`/`ageplay` importeras eller indexeras aldrig.
- Filer med hårda åldersmarkörer (`13-årig`, `minderårig`, `lolita` …) hamnar i
  `out/quarantine.txt` och indexeras inte.
- Filer med ordet "barn" listas i `out/review-manuellt.txt` för manuell
  granskning — de är inte automatiskt uteslutna.
- Paketet innehåller explicit material. Flytta det, lägg det inte i molnet.

---

## 13. Vad verktyget inte kan

- **Tempus** (preteritum/presens) mäts inte — det kräver ordklasstaggning.
- **Perspektiv** räknas på pronomen; vid jämn fördelning står det "blandat".
- **Dialog** mäts radbaserat och är en uppskattning, inte en exakt siffra.
- **BM25** hittar ord, inte betydelse. "Samma stämning med andra ord" kräver
  embeddings, vilket inte ingår i det här paketet.

---

## 14. Snabbkoll — hela vägen på fyra rader

```powershell
cd stil-lab
powershell -ExecutionPolicy Bypass -File .\install.ps1
ollama pull qwen2.5:7b
.\stil.cmd ask "En scen i ett kök sent på kvällen. Två grannar. Hon har bestämt sig för att säga något." --model qwen2.5:7b
```

Klart.
