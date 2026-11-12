"""Lagring: inställningar, historik och de färdiga novellfilerna.

I källkörning ligger allt under ``out/``. I den fristående exe-filen hamnar
samma filer i ``Novellstudion-data`` bredvid exe-filen. Novellerna sparas som
Markdown med en liten frontmatter som gör dem läsbara både för människa och
för nästa verktyg.
"""

from __future__ import annotations

import json
import os
import re
import string
import subprocess
import sys
import tempfile
import uuid
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from . import paths

BASE = paths.relative_base()
OUT = paths.data_root()
STATE_FILE = OUT / "gui-state.json"
HISTORY_FILE = OUT / "gui-historik.json"
DEFAULT_NOVEL_DIR = OUT / "noveller"
MAX_HISTORY = 300


# --------------------------------------------------------------- läs & skriv


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def load_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def save_json(path: Path, data: Any) -> None:
    _atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2))


def load_state() -> dict:
    data = load_json(STATE_FILE, {})
    if not isinstance(data, dict):
        return {}
    return data


def _archive_novels(folder: Path) -> Path | None:
    """Flyttar allt i novellmappen till en daterad backupmapp.

    En nollställning ska aldrig radera text som användaren skrivit. Returnerar
    backupmappen, eller ``None`` om det inte fanns något att flytta.
    """
    try:
        items = sorted(folder.iterdir(), key=lambda item: item.name.lower())
    except OSError:
        return None
    if not items:
        return None

    stamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    target = folder.parent / f"noveller-fore-nollstallning-{stamp}"
    suffix = 2
    while target.exists():
        target = folder.parent / f"noveller-fore-nollstallning-{stamp}-{suffix}"
        suffix += 1
    target.mkdir(parents=True, exist_ok=True)

    for item in items:
        destination = unique_path(target, item.name)
        try:
            shutil.move(str(item), str(destination))
        except OSError:
            continue
    return target


def reset_all() -> dict:
    """Nollställer inställningar och historik, och flyttar undan novellerna.

    Novellfilerna raderas inte: de hamnar i en daterad mapp bredvid
    novellmappen, så att en nollställning alltid går att ångra.
    """
    backup = _archive_novels(DEFAULT_NOVEL_DIR)
    save_json(STATE_FILE, {})
    save_json(HISTORY_FILE, [])
    return {"backup": str(backup) if backup else ""}


def save_state(state: dict) -> None:
    save_json(
        STATE_FILE,
        {
            "brief": state.get("brief") or {},
            "llm": state.get("llm") or {},
            "save": state.get("save") or {},
            "updated": datetime.now().isoformat(timespec="seconds"),
        },
    )


# --------------------------------------------------------------- filnamn


_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def safe_filename(name: str, fallback: str = "novell") -> str:
    stem = Path(name or "").stem if name else fallback
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", stem).strip(" .-")
    stem = re.sub(r"\s+", " ", stem)
    if not stem:
        stem = fallback
    if stem.upper() in _WINDOWS_RESERVED:
        stem = f"_{stem}"
    suffix = Path(name).suffix.lower() if name else ".md"
    if suffix not in (".md", ".txt"):
        suffix = ".md"
    return f"{stem[:120]}{suffix}"


def unique_path(folder: Path, filename: str) -> Path:
    candidate = folder / filename
    if not candidate.exists():
        return candidate
    stem, suffix = candidate.stem, candidate.suffix
    for index in range(2, 1000):
        candidate = folder / f"{stem}-{index}{suffix}"
        if not candidate.exists():
            return candidate
    return folder / f"{stem}-{uuid.uuid4().hex[:6]}{suffix}"


def resolve_folder(value: str | None) -> Path:
    raw = (value or "").strip().strip('"')
    if not raw:
        return DEFAULT_NOVEL_DIR
    path = Path(os.path.expandvars(raw)).expanduser()
    if not path.is_absolute():
        path = BASE / path
    return path


# --------------------------------------------------------------- spara novell


def build_frontmatter(meta: dict) -> str:
    fields = {
        "titel": meta.get("title") or "",
        "datum": meta.get("created") or datetime.now().isoformat(timespec="seconds"),
        "kategori": meta.get("category") or "",
        "sexgrad": meta.get("sex_level") or "",
        "ord": meta.get("words") or 0,
        "modell": meta.get("model") or "",
        "server": meta.get("base_url") or "",
        "stilprover": meta.get("hits") or 0,
    }
    lines = ["---"]
    for key, value in fields.items():
        lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
    lines.append("---")
    return "\n".join(lines)


def _slug(text: str, limit: int = 44) -> str:
    value = (text or "").lower()
    value = (
        value.replace("å", "a").replace("ä", "a").replace("ö", "o").replace("é", "e")
    )
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value[:limit].strip("-")


def _derive_title(text: str, limit: int = 80) -> str:
    text = " ".join((text or "").split())
    if not text:
        return ""
    first = re.split(r"(?<=[.!?])\s+", text)[0]
    first = first.strip().strip('"”').strip()
    if len(first) > limit:
        first = first[:limit].rsplit(" ", 1)[0]
    return first[:1].upper() + first[1:] if first else ""


def save_novel(
    text: str,
    title: str,
    folder: str | None,
    filename: str,
    meta: dict | None = None,
) -> dict:
    text = (text or "").strip()
    if not text:
        raise ValueError("Det finns ingen text att spara.")
    meta = dict(meta or {})
    title = (title or "").strip()
    if not title:
        title = _derive_title(str((meta.get("brief") or {}).get("scene") or "")) or "Novell"

    target_dir = resolve_folder(folder)
    if target_dir.exists() and not target_dir.is_dir():
        raise ValueError(f"Sökvägen är en fil, inte en mapp: {target_dir}")
    target_dir.mkdir(parents=True, exist_ok=True)

    if not (filename or "").strip():
        stamp = datetime.now().strftime("%Y-%m-%d-%H%M")
        base = _slug(title) or "novell"
        filename = f"{stamp}-{base}.md"
    filename = safe_filename(filename)
    path = unique_path(target_dir, filename)

    created = datetime.now().isoformat(timespec="seconds")
    meta.setdefault("created", created)
    meta["title"] = title
    meta["words"] = meta.get("words") or len(text.split())
    body = f"{build_frontmatter(meta)}\n\n# {title}\n\n{text}\n"
    _atomic_write(path, body)

    entry = {
        "id": uuid.uuid4().hex[:12],
        "title": meta["title"],
        "path": str(path),
        "folder": str(target_dir),
        "created": created,
        "words": meta["words"],
        "chars": len(text),
        "category": meta.get("category") or "",
        "sex_level": meta.get("sex_level") or "",
        "model": meta.get("model") or "",
        "kind": meta.get("kind") or "",
        "brief": meta.get("brief") or {},
        "llm": meta.get("llm") or {},
        "hits": meta.get("hits") or 0,
    }
    add_history(entry)
    return {"path": str(path), "folder": str(target_dir), "entry": entry}


# --------------------------------------------------------------- historik


def load_history() -> list[dict]:
    data = load_json(HISTORY_FILE, [])
    return data if isinstance(data, list) else []


def add_history(entry: dict) -> None:
    items = [item for item in load_history() if item.get("id") != entry.get("id")]
    items.insert(0, entry)
    save_json(HISTORY_FILE, items[:MAX_HISTORY])


def remove_history(entry_id: str) -> bool:
    items = load_history()
    remaining = [item for item in items if item.get("id") != entry_id]
    if len(remaining) == len(items):
        return False
    save_json(HISTORY_FILE, remaining)
    return True


def find_history(entry_id: str) -> dict | None:
    for item in load_history():
        if item.get("id") == entry_id:
            return item
    return None


def read_history_text(entry: dict) -> str:
    path = Path(str(entry.get("path") or ""))
    if not path.exists() or not path.is_file():
        raise FileNotFoundError("Filen finns inte längre på sin plats.")
    return path.read_text(encoding="utf-8", errors="replace")


# --------------------------------------------------------------- mappvy


def _places() -> list[dict]:
    home = Path.home()
    candidates = [
        ("Noveller", DEFAULT_NOVEL_DIR),
        ("Data", OUT),
        ("Programmappen" if paths.is_frozen() else "Projektmappen", paths.app_root()),
        ("Skrivbordet", home / "Desktop"),
        ("Skrivbordet", home / "Skrivbord"),
        ("Dokument", home / "Documents"),
        ("Dokument", home / "Dokument"),
        ("Nedladdningar", home / "Downloads"),
        ("Nedladdningar", home / "Nedladdningar"),
        ("Hemmappen", home),
    ]
    onedrive = os.environ.get("OneDrive")
    if onedrive:
        candidates.insert(2, ("OneDrive", Path(onedrive)))
    seen: set[str] = set()
    places = []
    for label, path in candidates:
        if not path.exists():
            continue
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        places.append({"label": label, "path": str(path)})
    return places


def _drives() -> list[dict]:
    if sys.platform != "win32":
        return [{"label": "/", "path": "/"}]
    drives = []
    for letter in string.ascii_uppercase:
        root = Path(f"{letter}:\\")
        if root.exists():
            drives.append({"label": f"{letter}:", "path": str(root)})
    return drives


def list_directory(raw_path: str | None) -> dict:
    if raw_path:
        path = Path(os.path.expandvars(raw_path)).expanduser()
        if not path.is_absolute():
            path = BASE / path
    else:
        path = DEFAULT_NOVEL_DIR if DEFAULT_NOVEL_DIR.exists() else BASE
    try:
        path = path.resolve()
    except OSError:
        path = BASE
    if not path.exists():
        path = BASE
    if not path.is_dir():
        path = path.parent

    entries = []
    try:
        children = list(path.iterdir())
    except PermissionError:
        children = []
    for child in children:
        if not child.is_dir():
            continue
        name = child.name
        if name in {"$Recycle.Bin", "System Volume Information", "__pycache__", ".git"}:
            continue
        hidden = name.startswith(".") or name.startswith("$")
        entries.append({"name": name, "path": str(child), "hidden": hidden})
    entries.sort(key=lambda item: (item["hidden"], item["name"].lower()))

    parent = path.parent if path.parent != path else None
    return {
        "path": str(path),
        "parent": str(parent) if parent else None,
        "dirs": entries,
        "places": _places(),
        "drives": _drives(),
        "writable": os.access(path, os.W_OK),
    }


def make_directory(parent: str, name: str) -> dict:
    clean = safe_filename(name, "ny-mapp")
    clean = Path(clean).stem
    if not clean:
        raise ValueError("Ge mappen ett namn.")
    folder = resolve_folder(parent) / clean
    if folder.exists():
        raise ValueError(f"Mappen finns redan: {folder.name}")
    folder.mkdir(parents=True, exist_ok=False)
    return {"path": str(folder)}


def reveal(path: str) -> None:
    target = Path(path).expanduser()
    if not target.is_absolute():
        target = BASE / target
    if not target.exists():
        raise FileNotFoundError("Sökvägen finns inte.")
    if sys.platform == "win32":
        if target.is_dir():
            os.startfile(str(target))  # noqa: S606 - Windows shell
        else:
            subprocess.Popen(["explorer", "/select,", str(target)])  # noqa: S603,S607
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(target)])  # noqa: S603,S607
    else:
        subprocess.Popen(["xdg-open", str(target if target.is_dir() else target.parent)])  # noqa: S603,S607
