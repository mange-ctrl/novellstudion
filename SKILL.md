---
name: stil-lab
description: Bygg och använd en stilkorpus av svenska noveller. Importera HTML-original, indexera med BM25, mäta stil, generera stilkort och färdiga prompts. Använd när användaren vill skriva i en viss författares eller en korpus stil, eller frågar om stil-RAG, finjustering på eget material eller promptbygge.
---

# stil-lab

Ett lokalt stil-RAG-verktyg: det läser en korpus, mäter stilen kvantitativt,
indexerar texterna och sätter ihop prompts med stilkort + autentiska utdrag.

## När verktyget ska användas

- Användaren vill skriva något "i stil med" sina egna texter.
- Användaren frågar hur man tränar eller styr en modell mot en egen korpus.
- Användaren vill veta vilken stil en samling texter faktiskt har.

## Grundflöde

Kör från `stil-lab/`:

```bash
python -m src.cli build --corpus corpus-html --db out/stil.db --out out
python -m src.cli stats --db out/stil.db
python -m src.cli search --db out/stil.db "<scenbeskrivning>" -k 5
python -m src.cli prompt --db out/stil.db "<uppgift>" -k 3 --out out
```

`prompt` skriver en färdig fil i `out/` med stilkort, utdrag och uppgift.
Skicka den till valfri modell — verktyget genererar ingen text själv.

## Grafiskt gränssnitt

`starta-novellstudion.cmd` (eller `python -m gui.server`) startar en lokal server
på `127.0.0.1:8790`: formulär för scen, kategori, längd, sexgrad 1–5, ordlistor,
mappväljare, strömmande generering och bibliotek. Dokumentation: `GUI.md`.
Det finns också färdiga exe-filer i `dist/` (en fil och en portabel mapp) som
inte kräver Python. LLM-klienten i `gui/llm.py` stödjer llama.cpp, Ollama och
OpenAI-format, inklusive servrar som kräver `--api-key`.

## Hårda regler

- **Kör aldrig `build` med `--no-guard`** och importera aldrig kategorierna
  `age-play` / `ageplay`. Skyddsnätet i `src/safety.py` finns av ett skäl.
- Om `out/quarantine.txt` innehåller filer: säg det till användaren och föreslå
  granskning. Indexera dem inte.
- Skriv inte ut brödtext ur korpusen i onödan. `search` visar förhandsvisningar —
  använd `--per-story` och korta svar.

## Tolkning av stilkortet

- `Dialog: X %` är radbaserad andel (replikrader med `”` eller `–`).
- Perspektiv räknas på pronomen; "blandat" betyder att inget perspektiv dominerar.
- Tempus mäts inte alls — hitta inte på en siffra.

## Om användaren vill finjustera istället

Korpusen är för liten för att lära en modell att skriva men stor nog för stil.
Rekommendera i den här ordningen: stilkort + RAG → embeddings (bge-m3) →
LoRA (Mistral-Nemo-12B-Base, QLoRA r=32). Motivera varför, och påpeka att
utvärdering krävs (blind A/B, memoriseringskontroll).
