"""Index: SQLite + FTS5 (BM25). Ingen vektordatabas, inga tunga beroenden.

FTS5 följer med i Pythons sqlite3 och ger riktig BM25-rankning gratis.
För stil-återvinning är det här ofta *bättre* än embeddings: vi vill hitta
passager med samma ord och samma rytm, inte passager med samma "betydelse".
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from . import safety
from .textutil import STOPWORDS, WORD_RE, iter_files, normalize, read_text, tokenize

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE stories (
    id       INTEGER PRIMARY KEY,
    relpath  TEXT UNIQUE NOT NULL,
    title    TEXT NOT NULL,
    sha      TEXT NOT NULL,
    n_words  INTEGER NOT NULL,
    n_chunks INTEGER NOT NULL
);

CREATE TABLE chunks (
    id       INTEGER PRIMARY KEY,
    story_id INTEGER NOT NULL REFERENCES stories(id),
    seq      INTEGER NOT NULL,
    n_words  INTEGER NOT NULL,
    text     TEXT NOT NULL
);

-- Externt innehåll: texten lagras en gång, i chunks.
CREATE VIRTUAL TABLE chunks_fts USING fts5(
    text,
    content='chunks',
    content_rowid='id',
    tokenize='unicode61 remove_diacritics 0'
);

CREATE INDEX idx_chunks_story ON chunks(story_id);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def chunk_paragraphs(
    paras: list[str], target: int = 220, max_words: int = 450, overlap: int = 1
) -> list[str]:
    """Gruppera stycken till scener om ungefär `target` ord."""
    chunks: list[list[str]] = []
    cur: list[str] = []
    cur_words = 0

    for para in paras:
        words = len(tokenize(para))
        if cur and (cur_words + words > max_words or cur_words >= target):
            chunks.append(list(cur))
            cur = cur[-overlap:] if overlap else []
            cur_words = sum(len(tokenize(p)) for p in cur)
        cur.append(para)
        cur_words += words

    if cur:
        chunks.append(list(cur))
    return ["\n\n".join(c) for c in chunks if make_title_stub(c)]


def make_title_stub(paras: list[str]) -> str:
    return " ".join(paras).strip()


def build(
    corpus_dir: Path,
    db_path: Path,
    min_words: int = 120,
    target: int = 220,
    max_words: int = 450,
    overlap: int = 1,
    exclude: tuple[str, ...] = (),
    guard: bool = True,
) -> dict:
    """Läs korpusen, bygg om databasen från grunden. Idempotent.

    exclude: katalognamn (skiftlägesokänsligt) som hoppas över helt.
    guard:   karantänsätt filer med hårda åldersmarkörer.
    """
    files = iter_files(corpus_dir)
    if not files:
        raise FileNotFoundError(
            f"Inga .txt/.md/.docx-filer hittades under {corpus_dir}"
        )

    if db_path.exists():
        db_path.unlink()
    for suffix in ("-wal", "-shm"):
        side = Path(str(db_path) + suffix)
        if side.exists():
            side.unlink()

    conn = connect(db_path)
    conn.executescript(SCHEMA)

    skipped: list[tuple[str, str]] = []
    excluded: list[str] = []
    quarantined: list[tuple[str, list[str]]] = []
    soft_flags: list[tuple[str, int]] = []
    stats = {"files": len(files), "stories": 0, "chunks": 0, "words": 0}

    excluded_lower = {e.lower() for e in exclude}

    for path in files:
        relpath = str(path.relative_to(corpus_dir)).replace("\\", "/")
        parts = {p.lower() for p in Path(relpath).parts[:-1]}
        if excluded_lower & parts:
            excluded.append(relpath)
            continue

        try:
            text = read_text(path)
        except Exception as exc:  # noqa: BLE001 - vi vill rapportera, inte krascha
            skipped.append((relpath, str(exc)))
            continue

        if guard:
            hits = safety.scan(text)
            if hits:
                quarantined.append((relpath, hits))
                continue
            soft = safety.soft_scan(text)
            if soft:
                soft_flags.append((relpath, soft))

        words = len(tokenize(text))
        if words < min_words:
            skipped.append((relpath, f"för kort ({words} ord)"))
            continue

        paras = [p for p in text.split("\n\n") if p.strip()]
        chunks = chunk_paragraphs(paras, target=target, max_words=max_words, overlap=overlap)
        if not chunks:
            skipped.append((relpath, "inga chunkar"))
            continue

        title = path.stem.replace("_", " ").replace("-", " ").strip()
        sha = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

        cur = conn.execute(
            "INSERT INTO stories(relpath, title, sha, n_words, n_chunks) VALUES (?,?,?,?,?)",
            (relpath, title, sha, words, len(chunks)),
        )
        story_id = cur.lastrowid

        for seq, chunk in enumerate(chunks):
            cur = conn.execute(
                "INSERT INTO chunks(story_id, seq, n_words, text) VALUES (?,?,?,?)",
                (story_id, seq, len(tokenize(chunk)), chunk),
            )
            conn.execute(
                "INSERT INTO chunks_fts(rowid, text) VALUES (?, ?)",
                (cur.lastrowid, chunk),
            )

        stats["stories"] += 1
        stats["chunks"] += len(chunks)
        stats["words"] += words

    conn.commit()
    stats["skipped"] = skipped
    stats["excluded"] = excluded
    stats["quarantined"] = quarantined
    stats["soft_flags"] = soft_flags
    return stats


def load_stories(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT title, relpath FROM stories ORDER BY id").fetchall()
    out = []
    for row in rows:
        chunks = conn.execute(
            "SELECT text FROM chunks WHERE story_id = (SELECT id FROM stories WHERE relpath = ?) ORDER BY seq",
            (row["relpath"],),
        ).fetchall()
        out.append({"title": row["title"], "text": "\n\n".join(c["text"] for c in chunks)})
    return out


def _build_match(query: str) -> str:
    terms = [t for t in WORD_RE.findall(query.lower()) if t not in STOPWORDS and len(t) > 1]
    if not terms:
        terms = WORD_RE.findall(query.lower()) or ["*"]
    # Citattecken kring varje term: undviker att FTS5 tolkar dem som operatorer.
    return " OR ".join(f'"{t}"' for t in terms)


def search(
    conn: sqlite3.Connection,
    query: str,
    k: int = 5,
    per_story: int = 2,
) -> list[dict]:
    """BM25-sökning, max `per_story` träffar per novell för att få spridning."""
    match = _build_match(query)
    rows = conn.execute(
        """
        SELECT c.id, c.text, c.seq, s.title, s.relpath, bm25(chunks_fts) AS rank
        FROM chunks_fts
        JOIN chunks c  ON c.id = chunks_fts.rowid
        JOIN stories s ON s.id = c.story_id
        WHERE chunks_fts MATCH ?
        ORDER BY rank
        LIMIT ?
        """,
        (match, max(k * 6, 30)),
    ).fetchall()

    picked: list[dict] = []
    seen: dict[str, int] = {}
    for row in rows:
        count = seen.get(row["relpath"], 0)
        if count >= per_story:
            continue
        seen[row["relpath"]] = count + 1
        picked.append(
            {
                "title": row["title"],
                "relpath": row["relpath"],
                "seq": row["seq"],
                "score": -row["rank"],  # bm25() är negativ; vänd för läsbarhet
                "text": row["text"],
            }
        )
        if len(picked) >= k:
            break
    return picked


def insert_text(conn: sqlite3.Connection, relpath: str, title: str, text: str) -> int:
    """Lägg till en enskild text (används av tester)."""
    text = normalize(text)
    words = len(tokenize(text))
    cur = conn.execute(
        "INSERT INTO stories(relpath, title, sha, n_words, n_chunks) VALUES (?,?,?,?,?)",
        (relpath, title, hashlib.sha256(text.encode()).hexdigest()[:16], words, 1),
    )
    story_id = cur.lastrowid
    cur = conn.execute(
        "INSERT INTO chunks(story_id, seq, n_words, text) VALUES (?,?,?,?)",
        (story_id, 0, words, text),
    )
    conn.execute("INSERT INTO chunks_fts(rowid, text) VALUES (?, ?)", (cur.lastrowid, text))
    return story_id
