"""Felsökning 3: vad är 'fyra bröllop' för något, och finns det en gemensam fot?"""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.textutil import read_text  # noqa: E402

samples = [
    "heterosex/bok-2-grekland-kapitel-3.txt",
    "heterosex/bonden-och-pigan-5.txt",
    "trekant/vernattning-med-ovantade-aktiviteter.txt",
]

for rel in samples:
    path = Path("corpus") / rel
    if not path.exists():
        print(f"saknas: {rel}")
        continue
    text = read_text(path)
    lines = text.split("\n")
    print(f"\n--- {rel}  ({len(lines)} rader)")
    for i, line in enumerate(lines):
        if "bröllop" in line.lower():
            print(f"  rad {i}: {line[:150]}")
    print("  sista rader:")
    for line in lines[-3:]:
        print("   |", line[:100])
