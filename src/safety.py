"""Skyddsnät mot texter som sexualiserar minderåriga.

Principen: vi dömer inte, vi flaggar. Filer som flaggas indexeras inte,
och ingen text ur dem skrivs ut någonstans — bara filnamnet.

Det här är avsiktligt trubbigt. Ett falskt alarm kostar en fil som du kan
granska manuellt. Ett missat alarm kostar något som inte går att göra ogjort.
"""

from __future__ import annotations

import re

# Hårda markörer: explicit ålder i minderårigt spann, eller entydiga begrepp.
HARD_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"\b(?:1[0-7]|[6-9])\s*[-–]?\s*(?:årig|åriga|åringen)\b", re.IGNORECASE),
        "ålder-årig",
    ),
    (
        re.compile(
            r"\b(?:1[0-7]|[6-9])\s*års?\s*(?:gammal|gammalt|gamma1|ung|ungt)\b",
            re.IGNORECASE,
        ),
        "ålder-gammal",
    ),
    (
        re.compile(
            r"\b(?:minderårig\w*|underårig\w*|barnporr\w*|lolita|preteen|underage|jailbait)\b",
            re.IGNORECASE,
        ),
        "term",
    ),
]

# Mjuka markörer: rapporteras för manuell granskning, exkluderas inte automatiskt.
# "barn" förekommer i all möjlig oskyldig prosa, så det får aldrig ensamt fälla en text.
SOFT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"\b(?:barn|barnet|barnen|barnvakt\w*|dagis|förskola|grundskola|"
        r"lågstadiet|mellanstadiet|skolbarn)\b",
        re.IGNORECASE,
    ),
]


def scan(text: str) -> list[str]:
    """Returnera vilka hårda markörer som finns i texten. Aldrig själva texten."""
    return [label for pattern, label in HARD_PATTERNS if pattern.search(text)]


def soft_scan(text: str) -> int:
    """Antal mjuka träffar — underlag för manuell granskning."""
    return sum(len(p.findall(text)) for p in SOFT_PATTERNS)
