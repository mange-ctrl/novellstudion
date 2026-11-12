"""Importera noveller direkt ur HTML-originalen (speglingen av sexnovell.se).

Fördelar mot de skrapade .txt-filerna:
  - titel, författare, betyg, röster, datum och kategori läses ur strukturen
  - brödtexten hämtas ur div.text-story, utan meny, sidfot eller HTML-rester
  - betygsfiltret görs vid källan, inte i efterhand

Kör:
    python tools/import_html.py --src "H:\\...\\www.sexnovell.se" --out corpus-html --min-rating 4.5
"""

from __future__ import annotations

import argparse
import html as htmlmod
import json
import re
import sys
import time
from html.parser import HTMLParser
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import safety  # noqa: E402

TITLE_RE = re.compile(r"<title>\s*(.*?)\s*\|\s*Sexnovell", re.DOTALL | re.IGNORECASE)
AUTHOR_RE = re.compile(r"Författare:\s*</strong>\s*<a[^>]*>(.*?)</a>", re.DOTALL)
DATE_RE = re.compile(r"Datum:\s*</strong>\s*([\d\-: ]+)", re.DOTALL)
RATING_RE = re.compile(r"Betyg:\s*</strong>\s*([\d.]+)\s*\((\d+)\s*röster\)", re.DOTALL)
CATEGORY_RE = re.compile(r"Kategori:\s*</strong>\s*<a[^>]*>(.*?)</a>", re.DOTALL)

EXCLUDED_CATEGORIES = {"ageplay"}


def norm_category(value: str) -> str:
    """'Age Play', 'age-play' och 'ageplay' måste bli samma sak."""
    return re.sub(r"[^a-z]", "", value.lower())


class BodyParser(HTMLParser):
    """Plockar ut texten innanför div.text-story. <br> blir radbrytning."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.started = False
        self.depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if not self.started:
            if tag == "div":
                self.started = True
                self.depth = 1
            return

        a = dict(attrs)
        cls = (a.get("class") or "").lower()
        ident = (a.get("id") or "").lower()

        # Sidan fortsätter med kommentarer och "mer av författaren" i egna block.
        # Texten slutar där — annars hamnar läsarkommentarer i novellen.
        if "comment" in cls or "announcement" in cls or ident.startswith("comment"):
            self.started = False
            return
        if tag in {"script", "style", "table"}:
            self.started = False
            return

        if tag == "div":
            self.depth += 1
        elif tag == "br":
            self.parts.append("\n")
        elif tag in {"p", "h1", "h2", "h3", "li", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if not self.started:
            return
        if tag == "div":
            self.depth -= 1
            if self.depth <= 0:
                self.started = False

    def handle_data(self, data):
        if self.started:
            self.parts.append(data)


def extract_body(raw: str) -> str:
    marker = raw.find('class="text-story"')
    if marker == -1:
        return ""
    start = raw.rfind("<div", 0, marker)
    if start == -1:
        return ""
    parser = BodyParser()
    try:
        parser.feed(raw[start:])
    except Exception:  # noqa: BLE001 - trasig HTML ska inte stoppa hela importen
        return ""
    text = "".join(parser.parts)
    text = htmlmod.unescape(text)
    text = re.sub(r"[ \t\u00a0]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Sista skyddsnätet: klipp vid kända sektionsrubriker om de slunkit med.
    cut = re.search(
        r"\n(?:Kommentarer|Datapolicy|Hantera kakor|Visa samtliga noveller|"
        r"Kommentera denna novell|Fler noveller|Mer av denna författare)\b",
        text,
    )
    if cut:
        text = text[: cut.start()]
    return text.strip()


def _clean(text: str | None) -> str:
    if not text:
        return ""
    return htmlmod.unescape(re.sub(r"\s+", " ", text)).strip()


def parse_story(path: Path) -> dict | None:
    raw = path.read_text(encoding="utf-8", errors="replace")

    rating_match = RATING_RE.search(raw)
    if not rating_match:
        return None

    body = extract_body(raw)
    if len(body) < 500:
        return None

    return {
        "title": _clean(TITLE_RE.search(raw).group(1) if TITLE_RE.search(raw) else path.parent.name),
        "author": _clean(AUTHOR_RE.search(raw).group(1) if AUTHOR_RE.search(raw) else ""),
        "date": _clean(DATE_RE.search(raw).group(1) if DATE_RE.search(raw) else ""),
        "rating": float(rating_match.group(1)),
        "votes": int(rating_match.group(2)),
        "category": _clean(CATEGORY_RE.search(raw).group(1) if CATEGORY_RE.search(raw) else ""),
        "body": body,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", default="corpus-html")
    ap.add_argument("--min-rating", type=float, default=4.5)
    ap.add_argument("--min-votes", type=int, default=0)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    src = Path(args.src) / "novell"
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    files = sorted(src.glob("*/*/index.html"))
    if args.limit:
        files = files[: args.limit]
    print(f"Novellsidor: {len(files)}")

    stats = {
        "seen": 0, "kept": 0, "low_rating": 0, "no_rating": 0,
        "too_short": 0, "excluded_category": 0, "guard": 0,
    }
    t0 = time.time()
    meta_path = out / "meta.jsonl"

    with meta_path.open("w", encoding="utf-8") as meta_file:
        for i, path in enumerate(files, 1):
            stats["seen"] += 1
            if i % 2000 == 0:
                rate = i / max(1e-6, time.time() - t0)
                print(f"  {i}/{len(files)}  ({rate:.0f} filer/s)  behållna: {stats['kept']}")

            story_id = path.parent.parent.name
            slug = path.parent.name

            try:
                record = parse_story(path)
            except Exception as exc:  # noqa: BLE001
                print(f"  FEL {path}: {exc}")
                continue

            if record is None:
                stats["no_rating"] += 1
                continue
            if record["rating"] < args.min_rating or record["votes"] < args.min_votes:
                stats["low_rating"] += 1
                continue
            if norm_category(record["category"]) in EXCLUDED_CATEGORIES:
                stats["excluded_category"] += 1
                continue
            if safety.scan(record["body"]):
                stats["guard"] += 1
                continue

            body = record["body"]
            if len(body.split()) < 100:
                stats["too_short"] += 1
                continue

            cat_dir = (record["category"] or "okand").lower().replace(" ", "-")
            cat_dir = re.sub(r"[^a-zåäö0-9-]", "", cat_dir) or "okand"
            dst = out / cat_dir
            dst.mkdir(parents=True, exist_ok=True)
            file_path = dst / f"{story_id}-{slug}.txt"
            file_path.write_text(body, encoding="utf-8")

            meta_file.write(json.dumps({
                "id": story_id,
                "slug": slug,
                "file": str(file_path.relative_to(out)).replace("\\", "/"),
                "title": record["title"],
                "author": record["author"],
                "date": record["date"],
                "rating": record["rating"],
                "votes": record["votes"],
                "category": record["category"],
                "words": len(body.split()),
            }, ensure_ascii=False) + "\n")
            stats["kept"] += 1

    print("\n=== RESULTAT ===")
    for key, value in stats.items():
        print(f"  {key}: {value}")
    print(f"  tid: {time.time() - t0:.0f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
