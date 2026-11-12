"""Korpusåtkomst för gränssnittet: kategorier, stilkkort och BM25-utdrag.

``src/index.py`` äger indexet. Här läggs det som bara gränssnittet behöver:
kategorifilter (från ``corpus-html/meta.jsonl``), betyg och en begriplig
träffbild. Ingen ny databas, inga nya beroenden.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from pathlib import Path

from src import analyze, index, safety
from src.textutil import tokenize

from . import paths

DEFAULT_DB = paths.resource("out", "stil.db")
META_PATH = paths.resource("corpus-html", "meta.jsonl")
STYLE_CARD_PATH = paths.resource("out", "style-card.txt")

# Kategorier som indexet avsiktligt aldrig innehåller.
BLOCKED_CATEGORIES = {"age play", "ageplay", "age-play"}

# Skyddsnätet i src/safety.py fångar filer vid import. Här görs en sista
# kontroll på själva utdraget: inget stilprov som nämner en minderårig ålder
# ska hamna i en prompt. Trubbigt med flit — ett hoppat utdrag kostar lite.
_MINOR_AGE = re.compile(
    r"\b(?:1[0-7]|[6-9])\s*(?:-|–)?\s*(?:årig|åriga|åringen|års?\s+gammal\w*)\b",
    re.IGNORECASE,
)
_MINOR_PHRASE = re.compile(
    r"\b(?:var|är|blott|endast|bara|knappt)\s+(?:1[0-7]|[6-9])\b",
    re.IGNORECASE,
)


def unsafe_excerpt(text: str) -> bool:
    if safety.scan(text):
        return True
    return bool(_MINOR_AGE.search(text) or _MINOR_PHRASE.search(text))

_DISPLAY = {
    "heterosex": "Heterosex",
    "homo": "Homo",
    "lesbiskt": "Lesbiskt",
    "bdsm": "BDSM",
    "kinky": "Kinky",
    "fetish": "Fetish",
    "gruppsex": "Gruppsex",
    "trekant": "Trekant",
    "onani": "Onani",
    "första gången": "Första gången",
    "none": "Okategoriserad",
}


def category_label(key: str) -> str:
    value = (key or "").strip()
    if not value:
        return ""
    return _DISPLAY.get(value.lower(), value[:1].upper() + value[1:])


class Corpus:
    def __init__(self, db_path: Path = DEFAULT_DB, meta_path: Path = META_PATH) -> None:
        self.db_path = Path(db_path)
        self.meta_path = Path(meta_path)
        self._lock = threading.Lock()
        self._meta: dict[str, dict] | None = None
        self._style_card: str | None = None

    # ------------------------------------------------------------- metadata

    def _load_meta(self) -> dict[str, dict]:
        if self._meta is not None:
            return self._meta
        with self._lock:
            if self._meta is not None:
                return self._meta
            meta: dict[str, dict] = {}
            if self.meta_path.exists():
                with self.meta_path.open(encoding="utf-8") as handle:
                    for line in handle:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            row = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        relpath = str(row.get("file") or "").replace("\\", "/")
                        if relpath:
                            meta[relpath] = row
            self._meta = meta
            return meta

    def categories(self) -> list[dict]:
        counts: dict[str, int] = {}
        for row in self._load_meta().values():
            raw = str(row.get("category") or "").strip()
            if not raw or raw.lower() in BLOCKED_CATEGORIES:
                continue
            key = raw.lower()
            counts[key] = counts.get(key, 0) + 1
        items = [
            {"key": key, "label": _DISPLAY.get(key, key.title()), "count": count}
            for key, count in counts.items()
        ]
        return sorted(items, key=lambda item: (-item["count"], item["label"]))

    def stats(self) -> dict:
        if not self.db_path.exists():
            return {"ok": False, "stories": 0, "chunks": 0, "words": 0, "error": "Index saknas"}
        conn = index.connect(self.db_path)
        try:
            stories, words = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(n_words), 0) FROM stories"
            ).fetchone()
            chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        finally:
            conn.close()
        return {
            "ok": True,
            "stories": stories,
            "chunks": chunks,
            "words": words,
            "categories": self.categories(),
        }

    # --------------------------------------------------------------- stil

    def style_card(self) -> str:
        """Använd den förberäknade filen när den finns — annars räkna om."""
        if self._style_card is not None:
            return self._style_card
        with self._lock:
            if self._style_card is not None:
                return self._style_card
            card = ""
            if STYLE_CARD_PATH.exists():
                card = STYLE_CARD_PATH.read_text(encoding="utf-8", errors="replace").strip()
            if not card and self.db_path.exists():
                conn = index.connect(self.db_path)
                try:
                    stories = index.load_stories(conn)
                finally:
                    conn.close()
                card = analyze.render_style_card(analyze.analyze_corpus(stories))
            self._style_card = card
            return card

    # -------------------------------------------------------------- sökning

    def _connect(self) -> sqlite3.Connection:
        if not self.db_path.exists():
            raise FileNotFoundError("Indexet out/stil.db saknas. Kör build först.")
        return index.connect(self.db_path)

    def _query_rows(
        self, conn: sqlite3.Connection, query: str, limit: int
    ) -> list[sqlite3.Row]:
        match = index._build_match(query)  # samma tokenisering som CLI:t
        return conn.execute(
            """
            SELECT c.id, c.text, c.seq,
                   s.title, s.relpath, s.id AS story_id,
                   bm25(chunks_fts) AS rank
            FROM chunks_fts
            JOIN chunks c  ON c.id = chunks_fts.rowid
            JOIN stories s ON s.id = c.story_id
            WHERE chunks_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (match, limit),
        ).fetchall()

    def _fallback_rows(
        self, conn: sqlite3.Connection, category: str, limit: int
    ) -> list[sqlite3.Row]:
        """BM25 kräver ordöverlapp. När inget matchar: ta högst betygsatta."""
        meta = self._load_meta()
        rows = conn.execute(
            """
            SELECT c.id, c.text, c.seq, s.title, s.relpath, s.id AS story_id
            FROM stories s
            JOIN chunks c ON c.story_id = s.id AND c.seq = 0
            """
        ).fetchall()
        wanted = category.strip().lower()
        picked: list[sqlite3.Row] = []
        for row in rows:
            info = meta.get(str(row["relpath"]), {})
            if wanted and str(info.get("category") or "").lower() != wanted:
                continue
            picked.append(row)
        picked.sort(key=lambda r: -float(meta.get(str(r["relpath"]), {}).get("rating") or 0))
        return picked[:limit]

    def search(
        self,
        query: str,
        k: int = 3,
        per_story: int = 1,
        category: str = "",
        exclude_ids: list[int] | None = None,
    ) -> dict:
        query = (query or "").strip()
        k = max(0, min(int(k), 12))
        per_story = max(1, min(int(per_story), 4))
        excluded = {int(i) for i in (exclude_ids or [])}
        meta = self._load_meta()
        wanted = (category or "").strip().lower()
        note = ""

        if k == 0:
            return {"hits": [], "note": "Utdrag avstängda (k = 0).", "relaxed": False}

        conn = self._connect()
        filtered = 0
        try:
            rows = self._query_rows(conn, query, max(k * 30, 120)) if query else []
            picked: list[dict] = []
            seen: dict[str, int] = {}

            def add(row: sqlite3.Row, score: float = 0.0, src: str = "bm25") -> None:
                nonlocal filtered
                relpath = str(row["relpath"])
                count = seen.get(relpath, 0)
                if count >= per_story:
                    return
                if int(row["id"]) in excluded:
                    return
                if unsafe_excerpt(str(row["text"])):
                    filtered += 1
                    return
                seen[relpath] = count + 1
                info = meta.get(relpath, {})
                picked.append(
                    {
                        "id": int(row["id"]),
                        "seq": int(row["seq"]),
                        "title": str(info.get("title") or row["title"]),
                        "relpath": relpath,
                        "category": str(info.get("category") or ""),
                        "rating": info.get("rating"),
                        "author": info.get("author") or "",
                        "score": round(float(score), 3),
                        "source": src,
                        "text": str(row["text"]),
                    }
                )

            for row in rows:
                info = meta.get(str(row["relpath"]), {})
                if wanted and str(info.get("category") or "").lower() != wanted:
                    continue
                add(row, -float(row["rank"]))
                if len(picked) >= k:
                    break

            if not picked and wanted:
                # Kategorin gav inget: låt användaren se det och sök bredare.
                for row in rows:
                    add(row, -float(row["rank"]))
                    if len(picked) >= k:
                        break
                if picked:
                    note = f"Inga träffar i {category} — visar träffar från alla kategorier."

            if not picked:
                for row in self._fallback_rows(conn, wanted, max(k * 3, 12)):
                    add(row, 0.0, "fallback")
                    if len(picked) >= k:
                        break
                if picked:
                    note = (
                        "Inga ordträffar — använder högst betygsatta texter"
                        + (f" i {category}" if wanted else "")
                        + " som stilprover. Skriv konkreta ord för bättre urval."
                    )
        finally:
            conn.close()

        if filtered:
            note = (
                f"{filtered} utdrag filtrerades bort av skyddsnätet (minderåriga)."
                + (f" {note}" if note else "")
            )

        return {"hits": picked, "note": note, "relaxed": bool(note)}

    def categories_for_hits(self) -> list[dict]:
        return self.categories()


def count_words(text: str) -> int:
    return len(tokenize(text))


def load_novel(path: Path) -> str:
    return Path(path).read_text(encoding="utf-8", errors="replace")
