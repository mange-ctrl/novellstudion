"""Felsökning: struktur, dubbletter, header-rader. Skriver aldrig ut brödtext."""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import index  # noqa: E402

conn = index.connect(Path("out/stil.db"))

dupes = conn.execute(
    "SELECT sha, COUNT(*) c FROM stories GROUP BY sha HAVING c > 1 ORDER BY c DESC"
).fetchall()
print(f"Dubbletter: {len(dupes)} grupper, {sum(r['c'] - 1 for r in dupes)} överflödiga filer")

rows = conn.execute("SELECT relpath FROM stories ORDER BY RANDOM() LIMIT 8").fetchall()
for r in rows:
    p = Path("corpus") / r["relpath"]
    lines = [ln.strip() for ln in p.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
    print(f"\n--- {r['relpath']}  ({len(lines)} rader)")
    for ln in lines[:3]:
        print("    |", ln[:80].replace("\t", " "))

# Hur många texter börjar med en kort rad som ser ut som metadata?
short_first = 0
total = 0
for r in conn.execute("SELECT relpath FROM stories"):
    p = Path("corpus") / r["relpath"]
    lines = [ln.strip() for ln in p.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
    if not lines:
        continue
    total += 1
    if len(lines[0]) < 45 and (":" in lines[0] or lines[0].lower() in {"age play", "bdsm", "heterosex"}):
        short_first += 1
print(f"\nFörsta rad ser ut som metadata: {short_first} av {total}")
