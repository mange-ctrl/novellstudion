"""LLM-klient: OpenAI-kompatibla servrar och Ollama.

Stödjer det som faktiskt används lokalt:

* **llama.cpp-server** (port 8080/8088/8089) — OpenAI-format på ``/v1``.
* **LM Studio, vLLM, text-generation-webui** — samma format.
* **Ollama** — eget format på ``/api``.
* **Moln-API:er** — OpenAI, OpenRouter, Groq ... samma format, med nyckel.

Inga tredjepartspaket. Strömning läses rad för rad och skickas vidare.
"""

from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Iterator

# Rimliga tider: en probe ska kännas omedelbar, en generering får ta tid.
PROBE_TIMEOUT = 2.5
GENERATE_TIMEOUT = 900


class LLMError(Exception):
    """Fel som kan visas för användaren utan teknisk omskrivning."""


# --------------------------------------------------------------- adresser


def normalize_base(raw: str) -> str:
    """``192.168.1.139:8089`` -> ``http://192.168.1.139:8089``."""
    value = (raw or "").strip()
    if not value:
        raise LLMError("Ange en adress, till exempel 127.0.0.1:8088.")
    if "://" not in value:
        value = "http://" + value
    parts = urllib.parse.urlsplit(value)
    if parts.scheme not in ("http", "https"):
        raise LLMError("Adressen måste börja med http:// eller https://.")
    if not parts.hostname:
        raise LLMError(f"Kunde inte läsa någon värd ur adressen {raw!r}.")
    path = parts.path.rstrip("/")
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def _root(base: str) -> str:
    """Ta bort ett avslutande ``/v1`` så att vi kan prova båda API-formaten."""
    if base.endswith("/v1"):
        return base[:-3]
    return base


def _headers(api_key: str | None) -> dict[str, str]:
    headers = {"Accept": "application/json", "User-Agent": "Novellstudion/1.0"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _get_json(url: str, api_key: str | None = None, timeout: float = PROBE_TIMEOUT) -> object:
    request = urllib.request.Request(url, headers=_headers(api_key), method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8", "replace")
    return json.loads(body) if body.strip() else {}


def _describe_url_error(exc: Exception) -> str:
    reason = getattr(exc, "reason", exc)
    if isinstance(reason, socket.timeout):
        return "servern svarade inte i tid"
    if isinstance(reason, ConnectionRefusedError):
        return "ingen lyssnar på den porten"
    return str(reason)


def _is_auth_error(exc: Exception) -> bool:
    return isinstance(exc, urllib.error.HTTPError) and exc.code in (401, 403)


def probe(raw_base: str, api_key: str | None = None) -> dict:
    """Ta reda på vad som kör på adressen och vilka modeller som finns.

    Returnerar ``{ok, base_url, kind, models, detail, latency_ms}``.
    Kastar ``LLMError`` med en begriplig förklaring om inget svarar.
    """
    base = normalize_base(raw_base)
    root = _root(base)
    started = time.perf_counter()
    errors: list[str] = []
    auth_required = False

    models: list[str] = []
    kind = ""
    detail = ""
    context: int | None = None

    # 1. OpenAI-format — vanligast (llama.cpp, LM Studio, vLLM, moln).
    try:
        data = _get_json(f"{root}/v1/models", api_key)
        entries = []
        if isinstance(data, dict):
            # llama.cpp svarar med både "data" och "models"; äldre/Ollama
            # varianter kan ha bara den ena.
            entries = data.get("data") or data.get("models") or []
        elif isinstance(data, list):
            entries = data
        models = [
            str(item.get("id") or item.get("name") or item.get("model"))
            if isinstance(item, dict)
            else str(item)
            for item in entries
            if (isinstance(item, dict) and (item.get("id") or item.get("name") or item.get("model")))
            or (isinstance(item, str) and item)
        ]
        kind = "openai"
    except Exception as exc:  # noqa: BLE001 - vi samlar fel och fortsätter
        if _is_auth_error(exc):
            auth_required = True
        errors.append(f"/v1/models: {_describe_url_error(exc)}")

    # 2. Ollama.
    if not kind:
        try:
            data = _get_json(f"{root}/api/tags", api_key)
            entries = data.get("models", []) if isinstance(data, dict) else []
            models = [
                str(item.get("name") or item.get("model"))
                for item in entries
                if isinstance(item, dict) and (item.get("name") or item.get("model"))
            ]
            kind = "ollama"
        except Exception as exc:  # noqa: BLE001
            if _is_auth_error(exc):
                auth_required = True
            errors.append(f"/api/tags: {_describe_url_error(exc)}")

    # 3. llama.cpp:s hälsokontroll (finns även när /v1/models är avstängd).
    if not kind:
        try:
            health = _get_json(f"{root}/health", api_key, timeout=1.5)
            if isinstance(health, dict) and health.get("status") in ("ok", "no slot available"):
                kind = "llama.cpp"
        except Exception as exc:  # noqa: BLE001
            errors.append(f"/health: {_describe_url_error(exc)}")

    if not kind:
        if auth_required:
            raise LLMError(
                "Servern kräver en API-nyckel (HTTP 401/403). Fyll i den under "
                "Avancerat och tryck Anslut igen."
            )
        joined = "; ".join(errors) if errors else "inget svar"
        raise LLMError(
            f"Ingen LLM-server svarade på {base}. Kontrollera att servern kör och att "
            f"adressen stämmer ({joined})."
        )

    if auth_required and kind == "llama.cpp":
        detail = "API-nyckel krävs — fyll i under Avancerat"

    # 4. Extra kontext från llama.cpp, om den finns.
    if kind in ("llama.cpp", "openai", "ollama"):
        try:
            props = _get_json(f"{root}/props", api_key, timeout=1.2)
            if isinstance(props, dict) and props:
                settings = props.get("default_generation_settings") or {}
                raw_ctx = settings.get("n_ctx") or props.get("n_ctx")
                if raw_ctx:
                    try:
                        context = int(raw_ctx)
                    except (TypeError, ValueError):
                        context = None
                model_path = str(props.get("model_path") or "")
                name = model_path.replace("\\", "/").rstrip("/").split("/")[-1]
                bits = []
                if name:
                    detail = name
                    bits.append(f"modell: {name}")
                if context:
                    bits.append(f"kontext: {context} tokens")
                detail = " · ".join(bits) or detail
                if not models and name:
                    models = [name]
                # /props finns i llama.cpp — även när /v1/models svarar.
                if settings or model_path:
                    kind = "llama.cpp"
        except Exception:  # noqa: BLE001 - helt valfritt
            pass

    if kind == "openai" and not models:
        # En del servrar har bara en modell och ingen lista.
        detail = detail or "OpenAI-kompatibel server"

    elapsed = round((time.perf_counter() - started) * 1000)
    return {
        "ok": True,
        "base_url": base,
        "kind": kind,
        "models": models,
        "detail": detail,
        "context": context,
        "needs_key": auth_required,
        "latency_ms": elapsed,
    }


# --------------------------------------------------------------- generering


def _open(url: str, payload: dict, api_key: str | None, timeout: int) -> urllib.request.addinfourl:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = _headers(api_key)
    headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, method="POST", headers=headers)
    return urllib.request.urlopen(request, timeout=timeout)


def _http_error_text(exc: urllib.error.HTTPError) -> str:
    try:
        raw = exc.read().decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        raw = ""
    raw = raw.strip()
    if not raw:
        return f"HTTP {exc.code}"
    try:
        data = json.loads(raw)
        message = (
            (data.get("error") or {}).get("message")
            if isinstance(data.get("error"), dict)
            else data.get("error")
        )
        if message:
            return f"HTTP {exc.code}: {message}"
    except Exception:  # noqa: BLE001
        pass
    return f"HTTP {exc.code}: {raw[:400]}"


def stream_chat(
    base_url: str,
    kind: str,
    model: str,
    messages: list[dict],
    temperature: float = 0.85,
    top_p: float = 0.9,
    max_tokens: int | None = None,
    seed: int | None = None,
    repeat_penalty: float = 1.1,
    api_key: str | None = None,
    timeout: int = GENERATE_TIMEOUT,
    disable_thinking: bool = True,
) -> Iterator[str]:
    """Skicka meddelandena och ge texten tillbaka bit för bit."""
    base = normalize_base(base_url)
    if kind == "ollama":
        yield from _stream_ollama(
            base, model, messages, temperature, top_p, max_tokens, seed, repeat_penalty,
            disable_thinking, timeout,
        )
        return
    yield from _stream_openai(
        base, kind, model, messages, temperature, top_p, max_tokens, seed, repeat_penalty,
        api_key, timeout, disable_thinking,
    )


def _stream_openai(
    base: str,
    kind: str,
    model: str,
    messages: list[dict],
    temperature: float,
    top_p: float,
    max_tokens: int | None,
    seed: int | None,
    repeat_penalty: float,
    api_key: str | None,
    timeout: int,
    disable_thinking: bool,
) -> Iterator[str]:
    payload = {
        "model": model or "local-model",
        "messages": messages,
        "stream": True,
        "temperature": temperature,
        "top_p": top_p,
    }
    if max_tokens:
        payload["max_tokens"] = int(max_tokens)
    if seed is not None:
        payload["seed"] = int(seed)

    repeat_penalty = max(1.0, float(repeat_penalty or 1.0))
    if kind == "llama.cpp":
        # llama.cpp accepterar dessa extrafält utöver OpenAI-formatet.
        # DRY är särskilt effektivt mot att modellen upprepar stycken.
        payload.update(
            {
                "top_k": 40,
                "min_p": 0.05,
                "repeat_penalty": round(repeat_penalty, 3),
                "repeat_last_n": 512,
                "dry_multiplier": 0.8,
                "dry_base": 1.75,
                "dry_allowed_length": 2,
                "dry_penalty_last_n": 2048,
                "frequency_penalty": 0.2,
                "presence_penalty": 0.2,
            }
        )
    else:
        # OpenAI-formatet saknar repeat_penalty; frekvensstraff är närmast.
        # Ett litet golv hindrar de värsta upprepningarna även vid 1,0.
        payload["frequency_penalty"] = round(
            min(2.0, max(0.1, (repeat_penalty - 1.0) * 2.0)), 3
        )
        payload["presence_penalty"] = 0.2

    if disable_thinking and kind == "llama.cpp":
        # Qwen3 m.fl. lägger annars hela budgeten på reasoning_content.
        payload["chat_template_kwargs"] = {"enable_thinking": False}

    url = _root(base).rstrip("/") + "/v1/chat/completions"
    try:
        response = _open(url, payload, api_key, timeout)
    except urllib.error.HTTPError as exc:
        detail = _http_error_text(exc)
        # Äldre llama.cpp-versioner kan avvisa DRY-fälten med 400. Försök en
        # gång till med bara det som OpenAI-formatet garanterar.
        if exc.code == 400 and kind == "llama.cpp":
            minimal = {
                key: payload[key]
                for key in ("model", "messages", "stream", "temperature", "top_p",
                            "max_tokens", "seed")
                if key in payload
            }
            minimal["frequency_penalty"] = 0.2
            minimal["presence_penalty"] = 0.2
            try:
                response = _open(url, minimal, api_key, timeout)
            except urllib.error.HTTPError as retry_error:
                raise LLMError(_http_error_text(retry_error)) from retry_error
            except urllib.error.URLError as retry_error:
                raise LLMError(
                    f"Kunde inte nå {base}: {_describe_url_error(retry_error)}. Kör servern?"
                ) from retry_error
        else:
            raise LLMError(detail) from exc
    except urllib.error.URLError as exc:
        raise LLMError(
            f"Kunde inte nå {base}: {_describe_url_error(exc)}. Kör servern?"
        ) from exc

    content_type = (response.headers.get("Content-Type") or "").lower()
    try:
        if "text/event-stream" not in content_type:
            raw = response.read().decode("utf-8", "replace")
            try:
                data = json.loads(raw)
                content = data["choices"][0]["message"].get("content") or ""
            except Exception as exc:  # noqa: BLE001
                raise LLMError(
                    f"Servern svarade i ett format som inte kändes igen: {raw[:300]}"
                ) from exc
            if content:
                yield content
            return

        for raw_line in response:
            line = raw_line.decode("utf-8", "replace").strip()
            if not line or line.startswith(":"):
                continue
            if line.startswith("data:"):
                line = line[5:].strip()
            if line == "[DONE]":
                break
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            choices = data.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            piece = delta.get("content")
            if piece:
                yield piece
            if choices[0].get("finish_reason"):
                break
    finally:
        response.close()


def _stream_ollama(
    base: str,
    model: str,
    messages: list[dict],
    temperature: float,
    top_p: float,
    max_tokens: int | None,
    seed: int | None,
    repeat_penalty: float,
    disable_thinking: bool,
    timeout: int,
) -> Iterator[str]:
    options: dict = {
        "temperature": temperature,
        "top_p": top_p,
        "top_k": 40,
        "min_p": 0.05,
        "repeat_penalty": max(1.0, float(repeat_penalty or 1.0)),
        "repeat_last_n": 512,
    }
    if max_tokens:
        options["num_predict"] = int(max_tokens)
    if seed is not None:
        options["seed"] = int(seed)
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "options": options,
    }
    if disable_thinking:
        payload["think"] = False
    url = _root(base).rstrip("/") + "/api/chat"
    try:
        response = _open(url, payload, None, timeout)
    except urllib.error.HTTPError as exc:
        raise LLMError(_http_error_text(exc)) from exc
    except urllib.error.URLError as exc:
        raise LLMError(
            f"Kunde inte nå {base}: {_describe_url_error(exc)}. Kör servern?"
        ) from exc

    try:
        for raw_line in response:
            line = raw_line.decode("utf-8", "replace").strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if data.get("error"):
                raise LLMError(str(data["error"]))
            piece = (data.get("message") or {}).get("content")
            if piece:
                yield piece
            if data.get("done"):
                break
    finally:
        response.close()


__all__ = ["LLMError", "normalize_base", "probe", "stream_chat", "GENERATE_TIMEOUT"]
