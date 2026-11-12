"""Stilanalys: räknar ut en stilprofil ur en korpus och renderar ett stil kort.

Ingen maskininlärning. Det här är meningen: kvantitativa, granskningsbara
mått som går att lita på, och som direkt kan översättas till instruktioner
till en språkmodell.
"""

from __future__ import annotations

import math
from collections import Counter
from statistics import median

from .textutil import (
    FIRST_PERSON,
    SECOND_PERSON,
    STOPWORDS,
    THIRD_PERSON,
    content_words,
    dialogue_ratio,
    split_sentences,
    tokenize,
)


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, round((pct / 100) * (len(ordered) - 1))))
    return float(ordered[idx])


def _stdev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((v - mean) ** 2 for v in values) / (len(values) - 1))


def _detect_pov(tokens: list[str]) -> str:
    first = sum(1 for t in tokens if t in FIRST_PERSON)
    second = sum(1 for t in tokens if t in SECOND_PERSON)
    third = sum(1 for t in tokens if t in THIRD_PERSON)
    counts = {"första person": first, "andra person": second, "tredje person": third}
    winner = max(counts, key=counts.get)  # type: ignore[arg-type]
    total = sum(counts.values()) or 1
    # Kräv lite marginal, annars säger vi "blandat" hellre än att gissa fel.
    if counts[winner] / total < 0.45:
        return "blandat"
    return winner


def analyze_story(text: str) -> dict:
    sentences = split_sentences(text)
    tokens = tokenize(text)
    sent_lengths = [len(tokenize(s)) for s in sentences]
    sent_lengths = [n for n in sent_lengths if n > 0]
    paras = [p for p in text.split("\n\n") if p.strip()]
    para_lengths = [len(tokenize(p)) for p in paras]

    return {
        "words": len(tokens),
        "sentences": len(sent_lengths),
        "sent_len": sent_lengths,
        "para_len": para_lengths,
        "dialogue": dialogue_ratio(text),
        "pov": _detect_pov(tokens),
        "ttr": (len(set(tokens)) / len(tokens)) if tokens else 0.0,
    }


def analyze_corpus(stories: list[dict]) -> dict:
    """stories: [{"title": str, "text": str}]"""
    per_story = []
    all_sent_len: list[int] = []
    all_para_len: list[int] = []
    dialogue_weighted = 0.0
    total_words = 0
    pov_counts: Counter[str] = Counter()
    word_freq: Counter[str] = Counter()
    bigrams: Counter[str] = Counter()

    for story in stories:
        m = analyze_story(story["text"])
        per_story.append({"title": story["title"], **m})
        all_sent_len.extend(m["sent_len"])
        all_para_len.extend(m["para_len"])
        dialogue_weighted += m["dialogue"] * m["words"]
        total_words += m["words"]
        pov_counts[m["pov"]] += 1

        for sent in split_sentences(story["text"]):
            cw = content_words(sent)
            word_freq.update(cw)
            for a, b in zip(cw, cw[1:]):
                if a != b:
                    bigrams[f"{a} {b}"] += 1

    total_words = max(1, total_words)
    short_ratio = (
        sum(1 for n in all_sent_len if n <= 8) / len(all_sent_len) if all_sent_len else 0.0
    )
    long_ratio = (
        sum(1 for n in all_sent_len if n >= 25) / len(all_sent_len) if all_sent_len else 0.0
    )

    punct = Counter()
    for story in stories:
        punct["kommatecken"] += story["text"].count(",")
        punct["tankstreck"] += story["text"].count("—") + story["text"].count("–")
        punct["ellips"] += story["text"].count("…") + story["text"].count("...")
        punct["fragetecken"] += story["text"].count("?")
        punct["utropstecken"] += story["text"].count("!")

    return {
        "corpus": {
            "stories": len(stories),
            "words": total_words,
            "sentences": len(all_sent_len),
        },
        "sentence": {
            "mean": sum(all_sent_len) / len(all_sent_len) if all_sent_len else 0.0,
            "median": median(all_sent_len) if all_sent_len else 0.0,
            "p90": _percentile([float(x) for x in all_sent_len], 90),
            "stdev": _stdev([float(x) for x in all_sent_len]),
            "short_ratio": short_ratio,
            "long_ratio": long_ratio,
        },
        "paragraph": {
            "mean_words": sum(all_para_len) / len(all_para_len) if all_para_len else 0.0,
        },
        "dialogue_ratio": dialogue_weighted / total_words,
        "pov": dict(pov_counts),
        "top_words": word_freq.most_common(20),
        "top_bigrams": [(b, c) for b, c in bigrams.most_common(15) if c >= 2],
        "punct_per_1000": {k: round(v * 1000 / total_words, 2) for k, v in punct.items()},
        "per_story": per_story,
    }


def _pct(x: float) -> int:
    return round(100 * x)


def _pov_label(m: dict) -> str:
    """Ett perspektiv bara om det dominerar klart — annars redovisas mixen."""
    counts = m.get("pov") or {}
    if not counts:
        return "okänt"
    total = sum(counts.values())
    top = max(counts.values())
    mix = ", ".join(f"{k} {v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1]))
    if len(counts) > 1 and top / total < 0.6:
        return f"blandat ({mix})"
    return max(counts, key=counts.get)  # type: ignore[arg-type]


def _dialogue_range(m: dict) -> str:
    per = [s["dialogue"] for s in m.get("per_story", [])]
    if not per:
        return ""
    return f"; per text {_pct(min(per))}–{_pct(max(per))} %"


def render_style_card(m: dict) -> str:
    """Kort, prompt-vänlig sammanfattning (~150 ord). Detta är det som klistras in."""
    s = m["sentence"]
    pov = _pov_label(m)
    tempo = "högt" if s["mean"] < 13 else ("lågt" if s["mean"] > 20 else "måttligt")
    lines = [
        "STILKORT (härlett ur korpusen, inte påhittat):",
        f"- Perspektiv: {pov}.",
        f"- Meningslängd: i snitt {s['mean']:.1f} ord, median {s['median']:.0f}, "
        f"p90 {s['p90']:.0f}. {_pct(s['short_ratio'])} % av meningarna är 8 ord eller kortare, "
        f"{_pct(s['long_ratio'])} % är 25 ord eller längre. Tempo: {tempo}.",
        f"- Stycken: i snitt {m['paragraph']['mean_words']:.0f} ord.",
        f"- Dialog: {_pct(m['dialogue_ratio'])} % av texten står innanför citattecken"
        f"{_dialogue_range(m)}.",
        f"- Skiljetecken per 1 000 ord: komma {m['punct_per_1000'].get('kommatecken', 0)}, "
        f"tankstreck {m['punct_per_1000'].get('tankstreck', 0)}, "
        f"ellips {m['punct_per_1000'].get('ellips', 0)}.",
    ]
    if m["top_bigrams"]:
        phrases = ", ".join(f"\"{b}\"" for b, _ in m["top_bigrams"][:6])
        lines.append(f"- Återkommande ordpar: {phrases}.")
    if m["top_words"]:
        words = ", ".join(w for w, _ in m["top_words"][:12])
        lines.append(f"- Vanligaste innehållsorden: {words}.")
    return "\n".join(lines)


def render_bible(m: dict) -> str:
    """Fullständig stilguide i Markdown. Detta är dokumentet man läser själv."""
    s = m["sentence"]
    c = m["corpus"]
    pov = _pov_label(m)
    pov_mix = ", ".join(f"{k}: {v}" for k, v in sorted(m["pov"].items(), key=lambda kv: -kv[1]))

    rules = [
        f"Håll meningslängden kring {s['mean']:.0f} ord. Korta meningar dominerar "
        f"({_pct(s['short_ratio'])} % ≤ 8 ord) — använd dem för slag, inte för utfyllnad."
        if s["short_ratio"] > 0.3
        else f"Meningarna är långa (snitt {s['mean']:.0f} ord). Bygg med bisatser och låt "
        f"tempot sjunka; undvik att hacka upp texten.",
        (
            f"Låt dialogen utgöra ungefär {_pct(m['dialogue_ratio'])} % av texten."
            if m["dialogue_ratio"] > 0.15
            else "Dialogen är sparsam. Låt kroppsspråk och miljö bära det som sägs."
        ),
        f"Skriv i {pov}." if pov != "blandat" else "Perspektivet växlar i korpusen — välj ett och håll det.",
        f"Stycken på cirka {m['paragraph']['mean_words']:.0f} ord.",
    ]

    return f"""# Stilguide — genererad ur korpusen

> Automatiskt framtagen av `stil-lab`. Siffrorna är mätta, inte gissade.
> Läs igenom och stryk det du inte håller med om — det är din stil, inte min.

## Omfång
{c['stories']} texter, {c['words']:,} ord, {c['sentences']:,} meningar.

## Meningsrytm
| Mått | Värde |
|---|---|
| Medellängd | {s['mean']:.1f} ord |
| Median | {s['median']:.0f} ord |
| 90:e percentil | {s['p90']:.0f} ord |
| Standardavvikelse | {s['stdev']:.1f} |
| Andel ≤ 8 ord | {_pct(s['short_ratio'])} % |
| Andel ≥ 25 ord | {_pct(s['long_ratio'])} % |

## Stycken och dialog
- Stycken: i snitt {m['paragraph']['mean_words']:.0f} ord.
- Dialog: {_pct(m['dialogue_ratio'])} % av tecknen står innanför citattecken.

## Perspektiv
{pov_mix}

## Skiljetecken (per 1 000 ord)
{chr(10).join(f"- {k}: {v}" for k, v in m['punct_per_1000'].items())}

## Ordval
Vanligaste innehållsorden: {", ".join(w for w, _ in m['top_words'])}

Återkommande ordpar: {", ".join(f"{b} ({c}x)" for b, c in m['top_bigrams']) or "—"}

## Skrivregler (härledda)
{chr(10).join(f"{i}. {r}" for i, r in enumerate(rules, 1))}

## Kända begränsningar
- Tempus (preteritum/presens) mäts **inte** — det kräver ordklasstaggning och
  en gissning vore värre än ingen siffra.
- Perspektivet är räknat på pronomen, inte på faktisk berättarröst.
  Blandade pronomen kan ge fel etikett.
- Siffrorna beskriver korpusen som helhet. Enskilda texter kan avvika kraftigt.
"""
