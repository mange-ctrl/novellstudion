"""Novellstudion — lokal webbserver och API.

    python -m gui.server

Servern binder till 127.0.0.1 och öppnar webbläsaren. Allt körs i ett enda
Python-processor: gränssnittet, korpussökningen och anropet till LLM:en.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import traceback
import urllib.parse
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import llm, loops, paths, prompting, rag, store

STATIC = paths.resource("gui", "static")
CORPUS = rag.Corpus()

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".json": "application/json; charset=utf-8",
    ".woff2": "font/woff2",
}
MAX_BODY = 4 * 1024 * 1024


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _log(message: str) -> None:
    """Skriv en rad till start.log bredvid exe-filen (eller i out/)."""
    try:
        store.OUT.mkdir(parents=True, exist_ok=True)
        with (store.OUT / "start.log").open("a", encoding="utf-8") as handle:
            handle.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {message}\n")
    except OSError:
        pass


def _message_box(text: str, title: str = "Novellstudion", error: bool = False) -> None:
    """Ett synligt meddelande även när webbläsaren hamnar i bakgrunden."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        flags = 0x00000010 if error else 0x00000040
        flags |= 0x00040000 | 0x00010000  # MB_TOPMOST | MB_SETFOREGROUND
        ctypes.windll.user32.MessageBoxW(None, text, title, flags)
    except Exception:  # noqa: BLE001
        pass



def _merge(defaults: dict, value: object) -> dict:
    merged = dict(defaults)
    if isinstance(value, dict):
        for key, item in value.items():
            if key in merged:
                merged[key] = item
    return merged


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "Novellstudion/1.0"

    # ------------------------------------------------------------- hjälpare

    def log_message(self, fmt: str, *args: object) -> None:  # noqa: A003
        sys.stderr.write(f"[{_now()}] {self.address_string()} {fmt % args}\n")

    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True
        host = self.headers.get("Host", "")
        return urllib.parse.urlsplit(origin).netloc.lower() == host.lower()

    def _send_json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, message: str, status: int = 400) -> None:
        self._send_json({"ok": False, "error": message}, status)

    def _read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0:
            return {}
        if length > MAX_BODY:
            raise ValueError("Förfrågan är för stor.")
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Kunde inte läsa förfrågan som JSON.") from exc
        return data if isinstance(data, dict) else {}

    def _send_file(self, path: Path) -> None:
        try:
            resolved = path.resolve()
            resolved.relative_to(STATIC.resolve())
        except (ValueError, OSError):
            self._send_error_json("Otillåten sökväg.", 403)
            return
        if not resolved.is_file():
            self.send_error(404, "Filen finns inte")
            return
        data = resolved.read_bytes()
        suffix = resolved.suffix.lower()
        self.send_response(200)
        self.send_header("Content-Type", CONTENT_TYPES.get(suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    # ------------------------------------------------------------- routing

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlsplit(self.path)
        path = parsed.path
        try:
            if path in ("/", "/index.html"):
                self._send_file(STATIC / "index.html")
                return
            if path.startswith("/static/"):
                self._send_file(STATIC / path[len("/static/"):])
                return
            if path == "/favicon.svg":
                self._send_file(STATIC / "favicon.svg")
                return
            if path == "/api/bootstrap":
                self._api_bootstrap()
                return
            if path == "/api/fs/list":
                query = urllib.parse.parse_qs(parsed.query)
                self._send_json({"ok": True, **store.list_directory((query.get("path") or [""])[0])})
                return
            if path == "/api/history":
                self._send_json({"ok": True, "items": store.load_history()})
                return
            if path == "/api/history/item":
                query = urllib.parse.parse_qs(parsed.query)
                self._api_history_item((query.get("id") or [""])[0])
                return
            if path == "/api/health":
                self._send_json({"ok": True, "time": _now()})
                return
            self.send_error(404, "Sidan finns inte")
        except Exception as exc:  # noqa: BLE001
            self._fail(exc)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlsplit(self.path)
        if not self._origin_ok():
            self._send_error_json("Otillåtet ursprung.", 403)
            return
        try:
            data = self._read_json()
        except ValueError as exc:
            self._send_error_json(str(exc), 400)
            return
        try:
            route = parsed.path
            if route == "/api/llm/probe":
                self._api_probe(data)
            elif route == "/api/rag/search":
                self._api_rag(data)
            elif route == "/api/prompt":
                self._api_prompt(data)
            elif route == "/api/generate":
                self._api_generate(data)
            elif route == "/api/save":
                self._api_save(data)
            elif route == "/api/reset":
                self._send_json({"ok": True, **store.reset_all()})
            elif route == "/api/state":
                store.save_state(data)
                self._send_json({"ok": True})
            elif route == "/api/fs/mkdir":
                self._api_mkdir(data)
            elif route == "/api/fs/reveal":
                store.reveal(str(data.get("path") or ""))
                self._send_json({"ok": True})
            elif route == "/api/history/delete":
                entry_id = str(data.get("id") or "")
                self._send_json({"ok": store.remove_history(entry_id)})
            else:
                self.send_error(404, "Okänd åtgärd")
        except BrokenPipeError:
            pass
        except Exception as exc:  # noqa: BLE001
            self._fail(exc)

    def _fail(self, exc: Exception) -> None:
        if isinstance(exc, ValueError):
            self._send_error_json(str(exc), 400)
        elif isinstance(exc, FileNotFoundError):
            self._send_error_json(str(exc), 404)
        elif isinstance(exc, PermissionError):
            self._send_error_json(f"Åtkomst nekad: {exc}", 403)
        else:
            traceback.print_exc()
            self._send_error_json(f"Oväntat fel: {exc}", 500)

    # ------------------------------------------------------------- API

    def _api_bootstrap(self) -> None:
        stats = CORPUS.stats()
        state = store.load_state()
        payload = {
            "ok": True,
            "version": "1.0.0",
            "python": sys.version.split()[0],
            "db": stats,
            "categories": stats.get("categories", []),
            "style_card": CORPUS.style_card(),
            "state": {
                "brief": _merge(prompting.DEFAULT_BRIEF, state.get("brief")),
                "llm": _merge(prompting.DEFAULT_LLM, state.get("llm")),
                "save": _merge(prompting.DEFAULT_SAVE, state.get("save")),
            },
            "defaults": {
                "brief": prompting.DEFAULT_BRIEF,
                "llm": prompting.DEFAULT_LLM,
                "save": prompting.DEFAULT_SAVE,
            },
            "sex_levels": [
                {"level": level, "label": info["label"], "short": info["short"],
                 "description": info["description"]}
                for level, info in prompting.SEX_LEVELS.items()
            ],
            "word_presets": {str(level): words for level, words in prompting.WORD_PRESETS.items()},
            "tones": prompting.TONE_OPTIONS,
            "endings": prompting.ENDING_OPTIONS,
            "pov": [{"value": key, "label": label} for key, label in prompting.POV_OPTIONS],
            "tense": [{"value": key, "label": label} for key, label in prompting.TENSE_OPTIONS],
            "dialogue": [
                {"value": key, "label": label} for key, label in prompting.DIALOGUE_OPTIONS
            ],
            "length_presets": prompting.LENGTH_PRESETS,
            "default_folder": str(store.DEFAULT_NOVEL_DIR),
            "history": store.load_history()[:40],
        }
        self._send_json(payload)

    def _api_probe(self, data: dict) -> None:
        base = str(data.get("base_url") or "").strip()
        api_key = str(data.get("api_key") or "").strip() or None
        try:
            result = llm.probe(base, api_key)
        except llm.LLMError as exc:
            self._send_error_json(str(exc), 502)
            return
        self._send_json({"ok": True, **result})

    def _search_payload(self, data: dict) -> tuple[dict, dict]:
        brief = _merge(prompting.DEFAULT_BRIEF, data.get("brief"))
        query = (
            str(data.get("query") or "").strip()
            or str(brief.get("search_query") or "").strip()
            or prompting.compose_query(brief)
        )
        category = ""
        if brief.get("category_filter", True):
            category = str(brief.get("category") or "")
        if "category" in data and data.get("category") is not None:
            category = str(data.get("category") or "")
        result = CORPUS.search(
            query,
            k=int(brief.get("k") or 0),
            per_story=int(brief.get("per_story") or 1),
            category=category,
            exclude_ids=list(brief.get("exclude_ids") or []),
        )
        result["query"] = query
        return brief, result

    def _api_rag(self, data: dict) -> None:
        brief, result = self._search_payload(data)
        self._send_json({"ok": True, "brief": brief, **result})

    def _build(self, data: dict, validate: bool = True) -> dict:
        brief, result = self._search_payload(data)
        mode = str(data.get("mode") or "new")
        continuation = str(data.get("continuation") or "")
        if validate:
            prompting.validate_brief(brief, mode, continuation)
        last_part = continuation[-6000:] if mode == "continue" else ""
        prompt = prompting.build_prompt(
            brief,
            CORPUS.style_card(),
            result["hits"],
            mode=mode,
            continuation=last_part,
        )
        prompt.update(
            {
                "hits": result["hits"],
                "note": result["note"],
                "query": result["query"],
                "brief": brief,
                "mode": mode,
                "stats": prompting.prompt_stats(prompt["prompt"]),
            }
        )
        return prompt

    def _api_prompt(self, data: dict) -> None:
        built = self._build(data, validate=False)
        self._send_json({"ok": True, **built})

    # ------------------------------------------------------------- generera

    def _api_generate(self, data: dict) -> None:
        llm_cfg = _merge(prompting.DEFAULT_LLM, data.get("llm"))
        save_cfg = _merge(prompting.DEFAULT_SAVE, data.get("save"))
        mode = str(data.get("mode") or "new")
        continuation = str(data.get("continuation") or "")
        override = str(data.get("prompt_override") or "").strip()

        if override:
            built = {
                "prompt": override,
                "messages": [{"role": "user", "content": override}],
                "hits": [],
                "stats": prompting.prompt_stats(override),
            }
            brief = _merge(prompting.DEFAULT_BRIEF, data.get("brief"))
        else:
            built = self._build(data)
            brief = built["brief"]

        model = str(llm_cfg.get("model") or "").strip()
        kind = str(llm_cfg.get("kind") or "openai")
        if not model and kind == "ollama":
            raise ValueError("Välj en modell i listan — Ollama behöver ett modellnamn.")
        if not model:
            # llama.cpp och många andra servrar har bara en modell laddad.
            model = "local-model"

        base_url = llm.normalize_base(str(llm_cfg.get("base_url") or ""))
        api_key = str(llm_cfg.get("api_key") or "").strip() or None

        temperature = float(llm_cfg.get("temperature") or 0.85)
        top_p = float(llm_cfg.get("top_p") or 0.9)
        max_tokens = int(llm_cfg.get("max_tokens") or 0) or prompting.suggest_max_tokens(
            int(brief.get("length") or 1200)
        )
        seed_raw = llm_cfg.get("seed")
        seed = int(seed_raw) if seed_raw not in (None, "", 0) else None
        repeat_penalty = float(llm_cfg.get("repeat_penalty") or 1.2)
        if kind in ("llama.cpp", "ollama"):
            # 1,0 ger nästan alltid upprepningar hos små modeller.
            repeat_penalty = max(1.1, min(1.5, repeat_penalty))
        disable_thinking = bool(llm_cfg.get("disable_thinking", True))

        # Serverns kontext är en hård gräns. Prompt + svar måste rymmas.
        context = int(llm_cfg.get("context") or 0)
        prompt_tokens = int((built.get("stats") or {}).get("estimated_tokens") or 0)
        context_warning = ""
        if context > 0 and prompt_tokens > 0:
            available = context - prompt_tokens - 32
            if available < 180:
                raise ValueError(
                    f"Prompten tar ungefär {prompt_tokens} av serverns {context} tokens. "
                    "Det finns inte plats för någon text. Höj serverns kontext — starta "
                    "llama.cpp med -c 16384 — eller sänk antal stilprover och längden."
                )
            if max_tokens > available:
                context_warning = (
                    f"Max tokens sänktes från {max_tokens} till {available} för att rymmas "
                    f"i serverns kontext ({context} tokens). Höj -c i llama.cpp för längre texter."
                )
                max_tokens = available

        # Strömma till webbläsaren.
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Connection", "close")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        self.close_connection = True

        def emit(payload: dict) -> None:
            chunk = f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8")
            self.wfile.write(chunk)
            self.wfile.flush()

        started = time.perf_counter()
        emit(
            {
                "type": "meta",
                "prompt": built["prompt"],
                "hits": len(built.get("hits") or []),
                "stats": built.get("stats"),
                "model": model,
                "base_url": base_url,
                "kind": kind,
                "max_tokens": max_tokens,
                "context": context,
                "prompt_tokens": prompt_tokens,
                "title": brief.get("title") or "",
                "override": bool(override),
            }
        )
        if context_warning:
            emit({"type": "warning", "message": context_warning})

        pieces: list[str] = []
        repetition: dict | None = None
        stream = llm.stream_chat(
            base_url,
            kind,
            model,
            built["messages"],
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            seed=seed,
            repeat_penalty=repeat_penalty,
            api_key=api_key,
            disable_thinking=disable_thinking,
        )
        try:
            buffer = ""
            checked = 0
            for piece in stream:
                if not piece:
                    continue
                pieces.append(piece)
                buffer += piece
                emit({"type": "delta", "text": piece})
                if len(buffer) >= 1200 and len(buffer) - checked >= 400:
                    checked = len(buffer)
                    hit = loops.find_repetition(buffer)
                    if hit:
                        repetition = hit
                        break
        except llm.LLMError as exc:
            emit({"type": "error", "message": str(exc)})
            return
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            try:
                emit({"type": "error", "message": f"Oväntat fel vid genereringen: {exc}"})
            except OSError:
                pass
            return
        finally:
            try:
                stream.close()
            except Exception:  # noqa: BLE001
                pass

        text = "".join(pieces).strip()
        elapsed = round(time.perf_counter() - started, 1)
        if not text:
            emit(
                {
                    "type": "error",
                    "message": (
                        "Modellen returnerade ingen text. Är det en resonerande modell "
                        "(Qwen3 m.fl.)? Kryssa i «Stäng av resonemang» under Avancerat. "
                        "Kontrollera också modellnamnet och serverns logg."
                    ),
                }
            )
            return

        # Sista kontroll: fånga upprepningar som hann skrivas klart.
        if repetition is None and len(text) >= 800:
            repetition = loops.find_repetition(text)
        if repetition:
            clean = text[: repetition["cut"]].rstrip()
            if len(clean) >= 200:
                text = clean
                emit(
                    {
                        "type": "warning",
                        "message": (
                            "Modellen började upprepa sig. Texten stoppades före upprepningen — "
                            "det som står kvar är sammanhängande. Fortsätt gärna med en ny scen."
                        ),
                    }
                )
            else:
                repetition = None

        # Vid fortsättning sparas hela texten, inte bara det nya stycket.
        final_text = text
        if mode == "continue" and continuation.strip():
            final_text = continuation.strip() + "\n\n" + text

        saved = None
        if save_cfg.get("autosave"):
            try:
                saved = store.save_novel(
                    final_text,
                    title=str(brief.get("title") or "").strip(),
                    folder=str(save_cfg.get("folder") or ""),
                    filename=str(save_cfg.get("filename") or ""),
                    meta={
                        "title": str(brief.get("title") or "").strip(),
                        "category": brief.get("category") or "",
                        "sex_level": brief.get("sex_level") or "",
                        "words": rag.count_words(final_text),
                        "model": model,
                        "base_url": base_url,
                        "kind": kind,
                        "hits": len(built.get("hits") or []),
                        "brief": brief,
                        "llm": {
                            "base_url": base_url,
                            "kind": kind,
                            "model": model,
                            "temperature": temperature,
                        },
                    },
                )
            except Exception as exc:  # noqa: BLE001
                traceback.print_exc()
                emit({"type": "warning", "message": f"Texten kunde inte sparas: {exc}"})

        emit(
            {
                "type": "done",
                "full_text": final_text,
                "words": rag.count_words(final_text),
                "seconds": elapsed,
                "saved": saved,
                "title": ((saved or {}).get("entry") or {}).get("title")
                or str(brief.get("title") or "").strip(),
                "category": brief.get("category") or "",
                "repetition": bool(repetition),
            }
        )

    # ------------------------------------------------------------- spara

    def _api_save(self, data: dict) -> None:
        text = str(data.get("text") or "")
        brief = _merge(prompting.DEFAULT_BRIEF, data.get("brief"))
        llm_cfg = _merge(prompting.DEFAULT_LLM, data.get("llm"))
        saved = store.save_novel(
            text,
            title=str(data.get("title") or brief.get("title") or "").strip(),
            folder=str(data.get("folder") or prompting.DEFAULT_SAVE["folder"]),
            filename=str(data.get("filename") or ""),
            meta={
                "title": str(data.get("title") or brief.get("title") or "").strip(),
                "category": brief.get("category") or "",
                "sex_level": brief.get("sex_level") or "",
                "words": rag.count_words(text),
                "model": str(llm_cfg.get("model") or ""),
                "base_url": str(llm_cfg.get("base_url") or ""),
                "kind": str(llm_cfg.get("kind") or ""),
                "hits": int(data.get("hits") or 0),
                "brief": brief,
                "llm": {
                    "base_url": llm_cfg.get("base_url"),
                    "kind": llm_cfg.get("kind"),
                    "model": llm_cfg.get("model"),
                    "temperature": llm_cfg.get("temperature"),
                },
            },
        )
        self._send_json({"ok": True, **saved})

    def _api_mkdir(self, data: dict) -> None:
        result = store.make_directory(str(data.get("parent") or ""), str(data.get("name") or ""))
        self._send_json({"ok": True, **result})

    def _api_history_item(self, entry_id: str) -> None:
        entry = store.find_history(entry_id)
        if not entry:
            raise FileNotFoundError("Posten finns inte i historiken.")
        text = store.read_history_text(entry)
        self._send_json({"ok": True, "entry": entry, "text": text})


# --------------------------------------------------------------- serverstart


def _find_port(host: str, preferred: int) -> int:
    import socket

    for port in range(preferred, preferred + 30):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind((host, port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"Hittade ingen ledig port mellan {preferred} och {preferred + 29}.")


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass

    parser = argparse.ArgumentParser(prog="novellstudion", description="Grafiskt gränssnitt för stil-lab.")
    parser.add_argument("--host", default="127.0.0.1", help="Standard: 127.0.0.1 (endast din dator)")
    parser.add_argument("--port", type=int, default=8790, help="Standard: 8790")
    parser.add_argument("--no-browser", action="store_true", help="Öppna inte webbläsaren automatiskt")
    args = parser.parse_args(argv)

    port = _find_port(args.host, args.port)
    try:
        store.OUT.mkdir(parents=True, exist_ok=True)
        store.DEFAULT_NOVEL_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    server = ThreadingHTTPServer((args.host, port), Handler)
    server.daemon_threads = True

    url = f"http://{args.host}:{port}/"
    _log(
        "START "
        f"frozen={paths.is_frozen()} exe={sys.executable!r} cwd={Path.cwd()!r} "
        f"argv={sys.argv!r} url={url} data={store.OUT!r}"
    )
    print("")
    print("  Novellstudion  ·  stil-lab" + ("  (fristående)" if paths.is_frozen() else ""))
    print("  " + "-" * 46)
    print(f"  Adress:   {url}")
    print(f"  Python:   {sys.version.split()[0]}")
    if paths.is_frozen():
        print(f"  Index:    inbyggt ({CORPUS.db_path.name})")
        print(f"  Data:     {store.OUT}")
    else:
        print(f"  Index:    {CORPUS.db_path}")
        print(f"  Noveller: {store.DEFAULT_NOVEL_DIR}")
    print("  Öppna adressen i webbläsaren om den inte öppnas automatiskt.")
    print("  Stäng fönstret eller tryck Ctrl+C för att avsluta.")
    print("")

    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.kernel32.SetConsoleTitleW("Novellstudion")
        except Exception:  # noqa: BLE001
            pass

    if not args.no_browser:

        def _welcome() -> None:
            opened = False
            try:
                opened = webbrowser.open(url)
            except Exception:  # noqa: BLE001
                opened = False
            _log(f"BROWSER opened={opened}")
            _message_box(
                "Novellstudion körs.\n\n"
                f"Webbläsaren öppnas på:\n{url}\n\n"
                "Om den inte syns: öppna adressen i valfri webbläsare.\n"
                "Låt konsolfönstret ligga kvar. Stäng det för att avsluta.",
                "Novellstudion",
            )

        threading.Timer(1.0, _welcome).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Avslutar.")
    finally:
        server.server_close()
        _log("EXIT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
