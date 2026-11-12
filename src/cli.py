"""Kommandoradsgränssnitt för stil-labbet.

    python -m src.cli build   --corpus corpus --db out/stil.db --out out
    python -m src.cli stats   --db out/stil.db
    python -m src.cli search  --db out/stil.db "möte på ett tåg" -k 5
    python -m src.cli prompt  --db out/stil.db "en scen där ..." -k 3 --out out
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from . import analyze, index
from .textutil import tokenize

DEFAULT_SYSTEM = (
    "Du skriver skönlitterär prosa på svenska. Följ stil kortet och utdragen "
    "nedan. Skriv färdig text, inte en plan eller ett utkast. Ingen metaberättelse."
)


def _utf8_stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass


def cmd_build(args: argparse.Namespace) -> int:
    corpus = Path(args.corpus)
    db = Path(args.db)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    print(f"Läser {corpus} ...")
    stats = index.build(
        corpus,
        db,
        min_words=args.min_words,
        target=args.target,
        max_words=args.max_words,
        overlap=args.overlap,
        exclude=tuple(args.exclude or ()),
        guard=not args.no_guard,
    )
    print(
        f"Klart: {stats['stories']} texter, {stats['chunks']} chunkar, "
        f"{stats['words']:,} ord -> {db}"
    )

    if stats["excluded"]:
        print(f"Exkluderade kategorier: {len(stats['excluded'])} filer")
    if stats["quarantined"]:
        print(f"Karantän (åldersmarkör): {len(stats['quarantined'])} filer")
        qpath = out / "quarantine.txt"
        qpath.write_text(
            "\n".join(f"{relpath}\t{','.join(labels)}" for relpath, labels in stats["quarantined"]),
            encoding="utf-8",
        )
        print(f"  -> {qpath}")
        for relpath, labels in stats["quarantined"][:5]:
            print(f"  - {relpath} ({','.join(labels)})")
    if stats["soft_flags"]:
        print(f"Att granska manuellt (barn-ord): {len(stats['soft_flags'])} filer")
        ropath = out / "review-manuellt.txt"
        ropath.write_text(
            "\n".join(f"{relpath}\t{count}" for relpath, count in stats["soft_flags"]),
            encoding="utf-8",
        )
        print(f"  -> {ropath}")

    if stats["skipped"]:
        print(f"Hoppade över {len(stats['skipped'])} fil(er):")
        for relpath, reason in stats["skipped"][:10]:
            print(f"  - {relpath}: {reason}")
        if len(stats["skipped"]) > 10:
            print(f"  ... och {len(stats['skipped']) - 10} till")

    conn = index.connect(db)
    stories = index.load_stories(conn)
    conn.close()
    if not stories:
        print("Inga texter att analysera.", file=sys.stderr)
        return 1

    metrics = analyze.analyze_corpus(stories)
    bible_path = out / "style-bible.md"
    bible_path.write_text(analyze.render_bible(metrics), encoding="utf-8")
    (out / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out / "style-card.txt").write_text(
        analyze.render_style_card(metrics), encoding="utf-8"
    )
    print(f"Stilguide: {bible_path}")
    print(f"Stilkort:  {out / 'style-card.txt'}")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    conn = index.connect(Path(args.db))
    stories = index.load_stories(conn)
    conn.close()
    metrics = analyze.analyze_corpus(stories)
    print(analyze.render_style_card(metrics))
    print()
    print(f"Texter: {metrics['corpus']['stories']}  Ord: {metrics['corpus']['words']:,}")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    conn = index.connect(Path(args.db))
    hits = index.search(conn, args.query, k=args.k, per_story=args.per_story)
    conn.close()
    if not hits:
        print("Inga träffar. Prova andra ord — BM25 kräver ordöverlapp.")
        return 0
    for i, hit in enumerate(hits, 1):
        preview = " ".join(hit["text"].split())[:280]
        print(f"\n[{i}] {hit['title']}  (chunk {hit['seq']}, score {hit['score']:.2f})")
        print(f"    {preview}...")
    return 0


def build_prompt_text(
    db: Path, query: str, k: int, per_story: int, length: int
) -> tuple[str, int]:
    """Stilkort + utdrag + uppgift. Returnerar (prompt, antal utdrag)."""
    conn = index.connect(db)
    stories = index.load_stories(conn)
    metrics = analyze.analyze_corpus(stories)
    hits = index.search(conn, query, k=k, per_story=per_story)
    conn.close()

    card = analyze.render_style_card(metrics)
    parts = [DEFAULT_SYSTEM, "", "=== " + card + " ===", ""]
    for i, hit in enumerate(hits, 1):
        parts.append(f"=== UTDRAG {i}: {hit['title']} ===")
        parts.append(hit["text"])
        parts.append("")

    parts.append("=== UPPGIFT ===")
    parts.append(query)
    parts.append("")
    parts.append(
        f"Skriv en scen på cirka {length} ord. Håll dig till stilkortet. "
        "Avsluta scenen, lämna den inte hängande."
    )
    return "\n".join(parts), len(hits)


def cmd_prompt(args: argparse.Namespace) -> int:
    prompt, n_hits = build_prompt_text(
        Path(args.db), args.query, args.k, args.per_story, args.length
    )
    if args.out:
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        slug = "-".join(tokenize(args.query)[:6]) or "prompt"
        path = out_dir / f"prompt-{slug}.md"
        path.write_text(prompt, encoding="utf-8")
        print(f"Prompt skriven: {path}  ({len(prompt)} tecken)")
        print(f"Utdrag: {n_hits}")
    else:
        print(prompt)
    return 0


# --------------------------------------------------------------- LLM-anrop

OLLAMA_DEFAULT = "http://127.0.0.1:11434"
OPENAI_DEFAULT = "https://api.openai.com"


def _post_json(url: str, payload: dict, headers: dict | None = None, timeout: int = 300) -> dict:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def call_model(
    backend: str,
    base_url: str,
    model: str,
    prompt: str,
    temperature: float,
    max_tokens: int,
    api_key: str,
) -> str:
    base = base_url.rstrip("/")
    if backend == "ollama":
        data = _post_json(
            base + "/api/generate",
            {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": temperature, "num_predict": max_tokens},
            },
        )
        return data.get("response", "")

    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    data = _post_json(
        base + "/v1/chat/completions",
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        headers,
    )
    return data["choices"][0]["message"]["content"]


def cmd_ask(args: argparse.Namespace) -> int:
    if args.from_file:
        prompt = Path(args.from_file).read_text(encoding="utf-8")
        n_hits = 0
    else:
        if not args.query:
            print("Ange en uppgift, eller --from-file.", file=sys.stderr)
            return 2
        prompt, n_hits = build_prompt_text(
            Path(args.db), args.query, args.k, args.per_story, args.length
        )

    if not args.model:
        print(
            "Ange --model. Ollama: kör 'ollama list' för att se namn.",
            file=sys.stderr,
        )
        return 2

    base = args.base_url or (OLLAMA_DEFAULT if args.backend == "ollama" else OPENAI_DEFAULT)
    api_key = args.api_key or os.environ.get("OPENAI_API_KEY", "")
    if args.backend == "openai" and not api_key:
        print("Saknar API-nyckel: sätt OPENAI_API_KEY eller --api-key.", file=sys.stderr)
        return 2

    print(
        f"Skickar {len(prompt)} tecken ({n_hits} utdrag) till {args.backend} "
        f"'{args.model}' på {base} ...",
        file=sys.stderr,
    )
    try:
        text = call_model(
            args.backend, base, args.model, prompt, args.temperature, args.max_tokens, api_key
        )
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        print(f"HTTP {exc.code}: {detail}", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(
            f"Kunde inte nå {base} ({exc.reason}).\n"
            "Kör servern? Ollama: 'ollama serve'. Modell hämtad? 'ollama pull <namn>'.",
            file=sys.stderr,
        )
        return 1

    text = text.strip()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = "-".join(tokenize(args.query or "svar")[:6]) or "svar"
    path = out_dir / f"svar-{slug}.md"
    path.write_text(text + "\n", encoding="utf-8")

    print(text)
    print(f"\n-> {path}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    _utf8_stdout()
    parser = argparse.ArgumentParser(prog="stil-lab", description="Stil-RAG för svensk prosa.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_build = sub.add_parser("build", help="Indexera korpus och bygg stilguide")
    p_build.add_argument("--corpus", default="corpus")
    p_build.add_argument("--db", default="out/stil.db")
    p_build.add_argument("--out", default="out")
    p_build.add_argument("--min-words", type=int, default=120)
    p_build.add_argument("--target", type=int, default=220)
    p_build.add_argument("--max-words", type=int, default=450)
    p_build.add_argument("--overlap", type=int, default=1)
    p_build.add_argument(
        "--exclude",
        action="append",
        default=["age play"],
        help="Katalog(er) som hoppas över helt. Kan anges flera gånger.",
    )
    p_build.add_argument(
        "--no-guard",
        action="store_true",
        help="Stäng av karantän för åldersmarkörer (gör inte detta).",
    )
    p_build.set_defaults(func=cmd_build)

    p_stats = sub.add_parser("stats", help="Visa stilprofil")
    p_stats.add_argument("--db", default="out/stil.db")
    p_stats.set_defaults(func=cmd_stats)

    p_search = sub.add_parser("search", help="BM25-sök i korpusen")
    p_search.add_argument("query")
    p_search.add_argument("--db", default="out/stil.db")
    p_search.add_argument("-k", type=int, default=5)
    p_search.add_argument("--per-story", type=int, default=2)
    p_search.set_defaults(func=cmd_search)

    p_prompt = sub.add_parser("prompt", help="Bygg en färdig prompt")
    p_prompt.add_argument("query")
    p_prompt.add_argument("--db", default="out/stil.db")
    p_prompt.add_argument("-k", type=int, default=3)
    p_prompt.add_argument("--per-story", type=int, default=1)
    p_prompt.add_argument("--length", type=int, default=600)
    p_prompt.add_argument("--out", default="out")
    p_prompt.set_defaults(func=cmd_prompt)

    p_ask = sub.add_parser("ask", help="Skicka prompten till en LLM och spara svaret")
    p_ask.add_argument("query", nargs="?", help="Uppgiften, t.ex. 'en scen i ett kök'")
    p_ask.add_argument("--from-file", help="Skicka en redan byggd promptfil istället")
    p_ask.add_argument("--db", default="out/stil.db")
    p_ask.add_argument("-k", type=int, default=3)
    p_ask.add_argument("--per-story", type=int, default=1)
    p_ask.add_argument("--length", type=int, default=600)
    p_ask.add_argument("--backend", choices=["ollama", "openai"], default="ollama")
    p_ask.add_argument("--base-url", help="Standard: Ollama 127.0.0.1:11434, OpenAI api.openai.com")
    p_ask.add_argument("--model", help="Modellnamn, t.ex. mistral-nemo eller gpt-4o-mini")
    p_ask.add_argument("--api-key", help="Annars läses OPENAI_API_KEY")
    p_ask.add_argument("--temperature", type=float, default=0.85)
    p_ask.add_argument("--max-tokens", type=int, default=1200)
    p_ask.add_argument("--out-dir", default="out")
    p_ask.set_defaults(func=cmd_ask)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
