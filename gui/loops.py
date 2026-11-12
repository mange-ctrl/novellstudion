"""Upptäcker när en modell börjar upprepa sig.

Små modeller kan fastna i en slinga och skriva samma stycken om och om igen för
att fylla ut till önskat ordantal. Vi jämför stycken med ord-4-gram (Jaccard)
och en sekvenslikhet; när ett stycke återkommer kapas texten före upprepningen.
Det är avsiktligt konservativt: hellre en kort text än en som upprepar sig.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

_WORD = re.compile(r"[a-zåäöéü]+")
_MIN_WORDS = 25
_LENGTH_RATIO = 0.55
_NGRAM_SIZE = 4


def _words(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def _ngrams(tokens: list[str]) -> set[tuple[str, ...]]:
    if len(tokens) < _NGRAM_SIZE:
        return set()
    return {tuple(tokens[i:i + _NGRAM_SIZE]) for i in range(len(tokens) - _NGRAM_SIZE + 1)}


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _paragraphs(text: str) -> list[tuple[int, str]]:
    """(startposition, stycke) för stycken separerade av blankrad."""
    result: list[tuple[int, str]] = []
    position = 0
    for chunk in re.split(r"(\n\s*\n)", text):
        if chunk.strip():
            start = position + len(chunk) - len(chunk.lstrip())
            result.append((start, chunk.strip()))
        position += len(chunk)
    return result


def find_repetition(
    text: str,
    threshold: float = 0.40,
    ratio_threshold: float = 0.72,
) -> dict | None:
    """Returnera var texten börjar upprepa sig, eller None.

    ``cut`` är teckenpositionen för det första stycke som liknar ett tidigare.
    """
    records: list[tuple[int, list[str], set]] = []
    for start, paragraph in _paragraphs(text):
        tokens = _words(paragraph)
        if len(tokens) < _MIN_WORDS:
            continue
        records.append((start, tokens, _ngrams(tokens)))

    for index in range(1, len(records)):
        start, tokens, grams = records[index]
        for previous in range(index):
            _, other_tokens, other_grams = records[previous]
            shorter = min(len(tokens), len(other_tokens))
            longer = max(len(tokens), len(other_tokens))
            if not longer or shorter / longer < _LENGTH_RATIO:
                continue
            overlap = _jaccard(grams, other_grams)
            if overlap < threshold:
                continue
            ratio = SequenceMatcher(None, tokens, other_tokens).ratio()
            if ratio >= ratio_threshold:
                return {
                    "cut": start,
                    "paragraph": index,
                    "previous": previous,
                    "overlap": round(overlap, 3),
                    "similarity": round(ratio, 3),
                }
    return None


def break_repetition(text: str) -> tuple[str, dict | None]:
    """Kapa texten före den första upprepningen."""
    hit = find_repetition(text)
    if not hit:
        return text, None
    clean = text[: hit["cut"]].rstrip()
    if len(clean) < 200:
        # Om det som återstår är för kort är det bättre att behålla allt och
        # låta användaren se vad som hände.
        return text, None
    return clean, hit
