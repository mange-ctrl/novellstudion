"""Textverktyg för stil-labbet.

Beroenden: endast stdlib. Inget ML, ingen GPU.
Allt här är avsiktligt enkelt och förutsägbart — det ska gå att lita på
även när korpusen är 2 000 texter och maskinen är upptagen.
"""

from __future__ import annotations

import html
import re
from collections import Counter
from pathlib import Path

# ---------------------------------------------------------------- tokenisering

# Svenska bokstäver måste med, annars klipps "möte" isär.
WORD_RE = re.compile(r"[a-zåäöéü]+")

# Vanliga funktionsord. Används för att (a) hitta innehållsord i stilstatistiken
# och (b) undvika att en sökning matchar på "på", "och", "att".
STOPWORDS: set[str] = {
    "och", "i", "att", "det", "som", "en", "på", "är", "av", "för", "med",
    "till", "den", "har", "de", "inte", "om", "ett", "men", "var", "jag",
    "sig", "från", "vi", "så", "kan", "man", "när", "år", "säger", "hon",
    "under", "också", "efter", "eller", "nu", "sin", "där", "vid", "mot",
    "ska", "skulle", "kommer", "hade", "mycket", "då", "bli", "blir", "upp",
    "ut", "in", "över", "vad", "hur", "alla", "bara", "än", "ja", "nej",
    "här", "dit", "sedan", "igen", "allt", "andra", "många", "hela", "både",
    "varje", "något", "någon", "ingen", "utan", "mellan", "genom", "hos",
    "bland", "enligt", "samt", "såsom", "eftersom", "medan", "fast", "trots",
    "även", "redan", "kanske", "nog", "väl", "ju", "visst", "tydligen",
    "denna", "detta", "dessa", "hans", "hennes", "deras", "honom", "henne",
    "dem", "mig", "min", "mitt", "mina", "din", "ditt", "dina", "vår",
    "vårt", "våra", "er", "era", "ens", "själv", "själva", "varandra",
    "några", "nån", "nått", "nåt", "dom", "mej", "dej", "sej", "blivit",
    "varit", "haft", "kunde", "måste", "bör", "borde", "vill", "ville",
    "får", "fick", "går", "gick", "står", "stod", "sitter", "satt", "kom",
    "tog", "gör", "gjorde", "sade", "sa", "tycker", "tyckte", "tänker",
    "tänkte", "vet", "visste", "blev", "blevet", "hade", "haft", "ha", "hade",
}

# Pronomen för grov perspektivbedömning (inte NLP — bara räkning).
FIRST_PERSON = {"jag", "mig", "min", "mitt", "mina", "vi", "oss", "vår", "vårt", "våra"}
SECOND_PERSON = {"du", "dig", "din", "ditt", "dina", "ni", "er", "ert", "era"}
THIRD_PERSON = {"han", "hon", "hen", "hans", "hennes", "hens", "de", "dem", "deras"}

_ABBREV = {
    "t.ex", "d.v.s", "bl.a", "m.m", "osv", "etc", "ca", "nr", "s.k", "jfr",
    "resp", "inkl", "exkl", "dr", "prof", "kap", "sid", "st", "fig", "t.o.m",
    "fr.o.m", "dvs", "mm",
}


# ---------------------------------------------------------------- inläsning

# HTML-rester från skrapade sidor: "<div class="text-story">", "</p>", "<br />".
# Bara taggliknande sekvenser — ett ensamt "<" i prosan ska inte ätas.
_TAG_RE = re.compile(r"</?[a-zA-Z][a-zA-Z0-9]*(?:\s[^>\n]{0,300})?>")
_ORPHAN_ATTR_RE = re.compile(r'^\s*[a-z-]+="[^"]*">\s*$', re.MULTILINE)


def normalize(text: str) -> str:
    """Gör texten förutsägbar: en radbrytningsstil, inga hårda blanksteg."""
    text = text.replace("\ufeff", "")
    text = text.replace("\u00a0", " ").replace("\u2009", " ").replace("\u202f", " ")
    text = _TAG_RE.sub("", text)
    text = _ORPHAN_ATTR_RE.sub("", text)
    text = html.unescape(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# Metadata-block i början av filen ("Titel: ...", "Författare: ...", "Betyg: 4.5").
# Om de får ligga kvar blir varje chunk inledd med en titel istället för prosa,
# och stilstatistiken fylls av ord som "betyg" och "datum".
_META_LINE = re.compile(
    r"^(?:titel|författare|betyg|datum|kategori|taggar|ord|längd|serie|del|"
    r"ålder|age|kapitel|publicerad|upplagd|visningar|kommentarer)\s*:",
    re.IGNORECASE,
)


def strip_metadata(text: str) -> str:
    """Ta bort ett inledande metadata-block. Rör inget om första raden är prosa."""
    lines = text.split("\n")
    first = next((i for i, line in enumerate(lines) if line.strip()), None)
    if first is None or not _META_LINE.match(lines[first].strip()):
        return text
    i = first
    while i < len(lines) and (not lines[i].strip() or _META_LINE.match(lines[i].strip())):
        i += 1
    return "\n".join(lines[i:]).strip()


# Skrapade webbsidor lämnar kvar navigering och cookie-fotter i texten.
# En rad som upprepas tre gånger eller mer i samma novell är layout, inte prosa.
FOOTER_LINES = {
    "datapolicy", "hantera kakor", "cookiepolicy", "integritetspolicy",
    "cookies", "cookieinställningar", "acceptera alla", "avvisa alla",
}

# Rader som är sidnavigering, inte berättelse.
_BOILER_PREFIX = re.compile(
    r"^(?:fler noveller|läs mer|mer från|andra noveller|se även|relaterade|"
    r"tillbaka till|nästa novell|föregående novell)",
    re.IGNORECASE,
)


def strip_boilerplate(text: str) -> str:
    """Ta bort upprepade menyrader, sidfotter och navigeringsrader."""
    lines = text.split("\n")
    counts = Counter(line.strip() for line in lines if line.strip())
    kept: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and counts[stripped] >= 3 and len(stripped) < 150:
            continue
        if stripped.lower() in FOOTER_LINES:
            continue
        if len(stripped) < 150 and _BOILER_PREFIX.match(stripped):
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def read_text(path: Path) -> str:
    """Läs .txt/.md/.markdown, eller .docx om python-docx finns."""
    suffix = path.suffix.lower()
    if suffix in {".docx", ".doc"}:
        try:
            import docx  # type: ignore
        except ImportError as exc:  # pragma: no cover - miljöberoende
            raise RuntimeError(
                f"Kan inte läsa {path.name}: python-docx saknas i den här Python-installationen.\n"
                "Konvertera till .txt först, eller kör skriptet med DSH:s bundlade Python."
            ) from exc
        doc = docx.Document(str(path))
        raw = "\n\n".join(p.text for p in doc.paragraphs)
    else:
        raw = path.read_text(encoding="utf-8", errors="replace")
    return strip_boilerplate(strip_metadata(normalize(raw)))


def iter_files(root: Path, exts: tuple[str, ...] = (".txt", ".md", ".markdown", ".docx")) -> list[Path]:
    """Alla corpusfiler under root, sorterade så att bygget blir reproducerbart."""
    files = [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in exts]
    return sorted(files, key=lambda p: str(p).lower())


# ---------------------------------------------------------------- meningsdelning

_END_RE = re.compile(r"[.!?…]+[\"'”’)]*(?=\s|$)")


def _is_abbrev_tail(segment: str) -> bool:
    s = segment.rstrip("\"'”’)]").rstrip()
    if not s.endswith("."):
        return False
    core = s[:-1].lower()
    match = re.search(r"([a-zåäö][a-zåäö\.]*)$", core)
    return bool(match and match.group(1).rstrip(".") in _ABBREV)


def split_sentences(text: str) -> list[str]:
    """Dela i meningar. Hanterar förkortningar och svenska citattecken så gott det går."""
    out: list[str] = []
    start = 0
    for match in _END_RE.finditer(text):
        segment = text[start:match.end()].strip()
        start = match.end()
        if not segment:
            continue
        if out and _is_abbrev_tail(segment):
            out[-1] = out[-1] + " " + segment
        else:
            out.append(segment)
    tail = text[start:].strip()
    if tail:
        if out:
            out[-1] = out[-1] + " " + tail
        else:
            out.append(tail)
    return [s for s in out if WORD_RE.search(s)]


# ---------------------------------------------------------------- ord & dialog

def tokenize(text: str) -> list[str]:
    return WORD_RE.findall(text.lower())


def content_words(text: str) -> list[str]:
    return [w for w in tokenize(text) if w not in STOPWORDS and len(w) > 1]


def _merge_spans(spans: list[tuple[int, int]]) -> list[list[int]]:
    if not spans:
        return []
    spans_sorted = sorted(spans)
    merged: list[list[int]] = [list(spans_sorted[0])]
    for a, b in spans_sorted[1:]:
        if a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return merged


def dialogue_ratio(text: str) -> float:
    """Andel tecken som är dialog, mätt rad för rad.

    Källtexterna är inkonsekventa: en del använder ”…” korrekt, en del sätter
    bara ” i början av varje replik utan att stänga, och en del använder
    tankstreck. Radbaserad mätning klarar alla tre utan att paranoia-parning
    spänner över hela dokumentet.

    En rad som börjar med ” eller – räknas som replik i sin helhet. Övriga
    rader räknas bara på citatpar inom raden.
    """
    if not text:
        return 0.0

    total = 0
    dialogue = 0

    for line in text.split("\n"):
        stripped = line.lstrip()
        if not stripped:
            continue
        total += len(line)

        if stripped[0] in {"”", "–", "—"}:
            dialogue += len(line)
            continue

        spans: list[tuple[int, int]] = []
        for quote in ("”", '"'):
            positions = [i for i, ch in enumerate(line) if ch == quote]
            spans.extend(zip(positions[0::2], positions[1::2]))
        for opener, closer in (("«", "»"), ("“", "”")):
            starts = [i for i, ch in enumerate(line) if ch == opener]
            ends = [i for i, ch in enumerate(line) if ch == closer]
            for a, b in zip(starts, ends):
                if b > a:
                    spans.append((a, b))

        dialogue += sum(b - a + 1 for a, b in _merge_spans(spans))

    return min(1.0, dialogue / total) if total else 0.0


def paragraphs(text: str) -> list[str]:
    """Stycken separerade av blankrad. Faller tillbaka på enkel radbrytning."""
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    if len(blocks) <= 1:
        blocks = [b.strip() for b in text.split("\n") if b.strip()]
    return blocks
