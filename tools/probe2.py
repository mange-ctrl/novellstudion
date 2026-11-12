"""Felsökning 2: serie/template-läckage, nästan-dubbletter, dialog-extremer."""

import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import index  # noqa: E402
from src.textutil import dialogue_ratio, read_text, tokenize  # noqa: E402

conn = index.connect(Path("out/stil.db"))
rels = [r["relpath"] for r in conn.execute("SELECT relpath FROM stories ORDER BY id")]

texts = {}
for rel in rels:
    try:
        texts[rel] = read_text(Path("corpus") / rel)
    except Exception:  # noqa: BLE001
        continue

print(f"Läste {len(texts)} texter")

# 1. Var kommer "fyra bröllop"/"dagen bok" ifrån?
for needle in ("fyra bröllop", "dagen"):
    hits = [rel for rel, t in texts.items() if needle in t.lower()]
    print(f"\n'{needle}': {len(hits)} texter")
    for rel in hits[:5]:
        print("   ", rel)

# 2. Nästan-dubbletter: samma 12 första ord
buckets: dict[str, list[str]] = defaultdict(list)
for rel, t in texts.items():
    key = " ".join(t.split()[:12]).lower()
    buckets[key].append(rel)
dups = {k: v for k, v in buckets.items() if len(v) > 1}
print(f"\nSamma inledning (12 ord): {len(dups)} grupper, {sum(len(v) - 1 for v in dups.values())} överflödiga")

# 3. Dialog-extremer
ratios = sorted(((dialogue_ratio(t), rel) for rel, t in texts.items()), reverse=True)
print("\nHögst dialogandel:")
for ratio, rel in ratios[:5]:
    print(f"   {ratio:.0%}  {rel}  ({len(tokenize(texts[rel]))} ord)")

# 4. Längdfördelning
lengths = sorted(len(tokenize(t)) for t in texts.values())
print(f"\nOrd per text: min {lengths[0]}, median {lengths[len(lengths)//2]}, max {lengths[-1]}")
print(f"Texter under 200 ord: {sum(1 for n in lengths if n < 200)}")
