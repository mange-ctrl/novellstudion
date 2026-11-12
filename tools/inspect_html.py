"""Kartlägg en novellsida: hitta titel, författare, betyg och brödtext.

Skriver bara ut struktur och korta etiketter — aldrig brödtext.
"""

import sys
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]


class Structure(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, str, str]] = []
        self.texts: list[tuple[tuple[tuple[str, str, str], ...], str]] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.stack.append((tag, a.get("class", ""), a.get("id", "")))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        t = data.strip()
        if t:
            self.texts.append((tuple(self.stack), t))


path = Path(sys.argv[1])
print("fil:", path.name, "|", len(path.read_text(encoding="utf-8", errors="replace")), "tecken")

parser = Structure()
parser.feed(path.read_text(encoding="utf-8", errors="replace"))

print("\n=== MEST TEXT ===")
by_path: Counter[str] = Counter()
for p, text in parser.texts:
    key = " > ".join(f"{t}.{c}" if c else t for t, c, _ in p[-4:])
    by_path[key] += len(text)
for key, n in by_path.most_common(8):
    print(f"  {n:>8}  {key}")

print("\n=== KORTA TEXTER (etiketter, titlar) ===")
seen = set()
for p, text in parser.texts:
    if len(text) < 70:
        key = " > ".join(f"{t}.{c}" if c else t for t, c, _ in p[-3:])
        if key in seen:
            continue
        seen.add(key)
        print(f"  [{key[:55]:<55}] {text[:55]}")

print("\n=== ELEMENT MED ID/CLASS ===")
seen2 = set()
for tag, cls, ident in {s for p, _ in parser.texts for s in p if s[1] or s[2]}:
    k = (tag, cls, ident)
    if k in seen2:
        continue
    seen2.add(k)
    print(f"  {tag:<8} class={cls[:45]:<45} id={ident[:25]}")
