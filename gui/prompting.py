"""Promptmotorn: gör en scenbeskrivning och en sexgrad till ett färdigt brev
till modellen — med stilkort, utdrag och exakta förhållningsregler.

All text här är svensk och skriven för att läsas av en språkmodell, inte av en
människa. Det som är mänskligt läsbart ligger i gränssnittet.
"""

from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Any

from . import paths, rag

# --------------------------------------------------------------- sexgrad

SEX_LEVELS: dict[int, dict[str, str]] = {
    1: {
        "label": "Mild",
        "short": "Antydan",
        "description": "Sexualiteten finns i blickar, andning och det som inte sägs. "
        "Inga explicita kroppsdelar, ingen grafisk skildring.",
        "instruction": "Håll scenen på antydans nivå. Sexualiteten ska kännas i blickar, "
        "andning, händer och det som inte sägs. Beskriv inga könsorgan och ingen grafisk sex.",
        "vocab": "närhet, värme, blickar, andhämtning, huden, läppar, händer",
    },
    2: {
        "label": "Sinnlig",
        "short": "Förspel",
        "description": "Kyssar, händer, kläder som glider undan. Sinnligt och närvarande, "
        "men scenen går inte hela vägen.",
        "instruction": "Skriv ett förspel: kyssar, händer, kläder som glider undan. "
        "Sinnligt och kroppsligt, men utan att skildra samlaget grafiskt.",
        "vocab": "kåt, varm, våt, smeka, kyssas, hångel, styv, njuta, stöna",
    },
    3: {
        "label": "Tydlig",
        "short": "Sex",
        "description": "Samlaget skildras, men språket håller igen. Kroppen antyds; "
        "känslan och närvaron bär scenen.",
        "instruction": "Samlaget får skildras, men språket ska hålla igen. Antyd kroppen "
        "snarare än att räkna upp den. Känslan, närvaron och rytmen bär scenen.",
        "vocab": "kuk, fitta, slickar, suger, tränger in, stönar, orgasm, knullar",
    },
    4: {
        "label": "Explicit",
        "short": "Rakt",
        "description": "Rakt språk om kropp och samlag. Konkreta ord, men behåll rytmen, "
        "perspektivet och psykologin.",
        "instruction": "Skriv explicit: rakt språk om kropp och samlag, konkreta ord. "
        "Behåll rytmen, perspektivet och personernas psykologi — ingen anatomisk lista.",
        "vocab": "kuk, fitta, kåt, våt, styv, stöna, slicka, suga, knulla, spruta, orgasm",
    },
    5: {
        "label": "Rå",
        "short": "Grovt",
        "description": "Grovt och direkt språk utan omskrivningar. Fortfarande prosa med "
        "människor, inte en lista av handlingar.",
        "instruction": "Skriv rått och direkt, utan omskrivningar. Grovt språk är tillåtet. "
        "Det ska fortfarande vara prosa om människor — inte en lista av handlingar.",
        "vocab": "kuk, fitta, knulla, spruta, sperma, rövhål, hora, styv, blöt, rå",
    },
}

# Ord som gränssnittet erbjuder som klickbara brickor. Användaren kan lägga
# till egna ord; listan är en startpunkt, inte en gräns.
WORD_PRESETS: dict[int, list[str]] = {
    1: ["huden", "andhämtning", "halsgrop", "läppar", "bröst", "lår", "närhet", "värme"],
    2: ["kåt", "varm", "våt", "smeka", "kyssas", "hångel", "styv", "njuta", "stöna"],
    3: ["kuk", "fitta", "slicka", "suga", "tränger in", "stönar", "orgasm", "knulla"],
    4: ["kåt", "våt", "styv", "stöna", "slicka", "suga", "knulla", "spruta", "orgasm"],
    5: ["knulla", "spruta", "sperma", "rövhål", "hora", "styv", "blöt", "rå"],
}

TONE_OPTIONS = [
    "lågmäld",
    "varm",
    "kylig",
    "rå",
    "ömsint",
    "lekfull",
    "mörk",
    "melankolisk",
    "spänd",
]
ENDING_OPTIONS = ["öppet", "lyckligt", "mörkt", "oväntat", "eftertänksamt"]
POV_OPTIONS = [
    ("auto", "Låt stilen avgöra"),
    ("jag", "Jag — första person"),
    ("han", "Han — tredje person"),
    ("hon", "Hon — tredje person"),
    ("du", "Du — andra person"),
]
TENSE_OPTIONS = [
    ("auto", "Låt stilen avgöra"),
    ("preteritum", "Dåtid (preteritum)"),
    ("presens", "Nutid (presens)"),
]
DIALOGUE_OPTIONS = [
    ("auto", "Som stilen"),
    ("lite", "Sparsam dialog"),
    ("måttlig", "Måttlig dialog"),
    ("mycket", "Dialogtung"),
]

LENGTH_PRESETS = [
    {"words": 600, "label": "Kort scen"},
    {"words": 1200, "label": "Novell"},
    {"words": 2500, "label": "Lång novell"},
    {"words": 4000, "label": "Långt kapitel"},
]


DEFAULT_BRIEF: dict[str, Any] = {
    "title": "",
    "category": "",
    "length": 1200,
    "sex_level": 3,
    "words_include": [],
    "words_avoid": [],
    "scene": "",
    "place": "",
    "characters": "",
    "stakes": "",
    "tone": "lågmäld",
    "ending": "öppet",
    "pov": "auto",
    "tense": "auto",
    "dialogue": "auto",
    "extra": "",
    "k": 3,
    "per_story": 1,
    "category_filter": True,
    "use_style_card": True,
    "search_query": "",
    "exclude_ids": [],
}

DEFAULT_LLM: dict[str, Any] = {
    "base_url": "http://127.0.0.1:8088",
    "kind": "openai",
    "model": "",
    "api_key": "",
    "remember_key": False,
    "temperature": 0.85,
    "top_p": 0.9,
    "max_tokens": 0,
    "seed": None,
    "repeat_penalty": 1.2,
    "disable_thinking": True,
    "context": 0,
}

DEFAULT_SAVE: dict[str, Any] = {
    "folder": paths.default_novel_folder(),
    "filename": "",
    "autosave": True,
}


def sex_level_brief(level: int) -> dict[str, str]:
    return SEX_LEVELS.get(int(level), SEX_LEVELS[3])


def words_for_level(level: int) -> list[str]:
    """Ord som hör till nivån och de lägre — för klickbara brickor."""
    words: list[str] = []
    for current in range(1, max(1, int(level)) + 1):
        for word in WORD_PRESETS.get(current, []):
            if word not in words:
                words.append(word)
    return words


# --------------------------------------------------------------- hjälpare


def pages(words: int) -> float:
    """Ungefärligt sidantal: en svensk textsida är cirka 300 ord."""
    return round(max(0, int(words)) / 300, 1)


def suggest_max_tokens(words: int) -> int:
    return max(512, min(16384, int(int(words) * 2.3) + 200))


def slug(text: str, limit: int = 48) -> str:
    text = (text or "").lower()
    text = text.replace("å", "a").replace("ä", "a").replace("ö", "o").replace("é", "e")
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:limit].strip("-") or "novell"


def suggest_filename(brief: dict, stamp: datetime | None = None) -> str:
    stamp = stamp or datetime.now()
    title = (brief.get("title") or "").strip()
    base = slug(title) if title else slug(brief.get("scene") or "novell", 32)
    return f"{stamp:%Y-%m-%d-%H%M}-{base}.md"


def compose_query(brief: dict) -> str:
    """Söktermer för BM25. Konkreta ord ur scenen fungerar bäst."""
    bits = [
        str(brief.get("scene") or ""),
        str(brief.get("place") or ""),
        str(brief.get("characters") or ""),
        str(brief.get("stakes") or ""),
    ]
    if int(brief.get("sex_level") or 0) >= 3:
        bits.extend(str(word) for word in (brief.get("words_include") or [])[:6])
    query = " ".join(bit.strip() for bit in bits if str(bit).strip())
    if not query:
        query = f"{brief.get('category') or ''} novell".strip()
    return query


def _label(options: list[tuple[str, str]], value: str, fallback: str = "") -> str:
    for key, label in options:
        if key == value:
            return label
    return fallback or value


def _bullet(label: str, value: str) -> str:
    value = (value or "").strip()
    return f"{label}: {value}" if value else ""


def _clamp(value: float, low: float, high: float, fallback: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return max(low, min(high, number))


# --------------------------------------------------------------- bygget


def build_prompt(
    brief: dict,
    style_card: str,
    hits: list[dict],
    mode: str = "new",
    continuation: str = "",
) -> dict[str, Any]:
    """Returnera ``{system, user, messages, prompt, words}``.

    ``prompt`` är system + user i ett stycke, för förhandsgranskning.
    """
    brief = {**DEFAULT_BRIEF, **brief}
    level = int(_clamp(brief.get("sex_level"), 1, 5, 3))
    info = sex_level_brief(level)
    words_include = [str(w).strip() for w in (brief.get("words_include") or []) if str(w).strip()]
    words_avoid = [str(w).strip() for w in (brief.get("words_avoid") or []) if str(w).strip()]
    length = int(_clamp(brief.get("length"), 100, 10000, 1200))
    continuation = (continuation or "").strip()

    system_parts = [
        "Du är en svensk författare som skriver skönlitterär prosa för vuxna läsare (18+).",
        "",
        "Regler:",
        "- Skriv färdig prosa, aldrig en plan, punktlista, rubrik eller kommentar om texten.",
        "- Alla personer i texten är vuxna (18 år eller äldre). Du skriver aldrig sexuellt "
        "innehåll som involverar minderåriga.",
        "- Skriv på svenska med svenska citattecken (”…”).",
        "- Följ stilkortet och stilproverna: härma rytmen och ordvalet, men kopiera aldrig "
        "hela meningar.",
        "- Upprepa aldrig en mening, ett stycke eller en formulering. Om scenen är slut, "
        "avsluta den i stället för att fylla ut.",
        "- Håll dig till uppgiften. Hitta inte på nya huvudpersoner eller miljöer.",
    ]
    if level >= 3:
        system_parts.append(
            "- Explicit sex mellan vuxna är tillåtet när uppgiften och sexgraden säger det."
        )
    system = "\n".join(system_parts)

    sections: list[str] = []

    if style_card and brief.get("use_style_card", True):
        sections.append("=== STILKORT (mätt ur korpusen) ===\n" + style_card.strip())

    if hits:
        lines = ["=== STILPROVER (utdrag ur korpusen — härma rytmen, inte innehållet) ==="]
        for number, hit in enumerate(hits, 1):
            title = hit.get("title") or "utan titel"
            category = hit.get("category") or ""
            header = f"[{number}] {title}" + (f" ({category})" if category else "")
            lines.append(header)
            lines.append(str(hit.get("text") or "").strip())
            lines.append("")
        sections.append("\n".join(lines).strip())

    brief_lines = ["=== UPPGIFT ==="]
    category = str(brief.get("category") or "").strip()
    if category:
        brief_lines.append(f"Kategori: {rag.category_label(category)}")
    title = str(brief.get("title") or "").strip()
    if title:
        brief_lines.append(f"Titel: {title}")
    for label, key in (
        ("Plats", "place"),
        ("Personer", "characters"),
        ("Det som står på spel", "stakes"),
        ("Ton", "tone"),
        ("Slut", "ending"),
    ):
        line = _bullet(label, str(brief.get(key) or ""))
        if line:
            brief_lines.append(line)
    if str(brief.get("pov") or "auto") != "auto":
        brief_lines.append(f"Perspektiv: {_label(POV_OPTIONS, str(brief['pov']))}")
    if str(brief.get("tense") or "auto") != "auto":
        brief_lines.append(f"Tempus: {_label(TENSE_OPTIONS, str(brief['tense']))}")
    if str(brief.get("dialogue") or "auto") != "auto":
        brief_lines.append(f"Dialog: {_label(DIALOGUE_OPTIONS, str(brief['dialogue']))}")
    scene = str(brief.get("scene") or "").strip()
    if scene:
        brief_lines.append("")
        brief_lines.append(scene)
    sections.append("\n".join(brief_lines))

    sex_lines = [f"=== SEXGRAD: {level} av 5 — {info['label']} ({info['short']}) ==="]
    sex_lines.append(info["instruction"])
    if words_include:
        sex_lines.append("Använd gärna dessa ord: " + ", ".join(words_include) + ".")
    elif level >= 3:
        sex_lines.append("Ordval som passar nivån: " + info["vocab"] + ".")
    if words_avoid:
        sex_lines.append("Undvik dessa ord och fraser: " + ", ".join(words_avoid) + ".")
    sections.append("\n".join(sex_lines))

    if mode == "continue":
        sections.append(
            "=== FORTSÄTTNING ===\n"
            f"Texten nedan är redan skriven. Fortsätt exakt där den slutar, i samma röst, "
            f"tempo och tempus. Skriv bara fortsättningen på cirka {length} ord — ingen "
            "sammanfattning, ingen upprepning av det som redan står.\n\n"
            "--- BEFINTLIG TEXT (slutet av den) ---\n"
            + continuation
            + "\n--- SLUT PÅ BEFINTLIG TEXT ---"
        )
    else:
        sections.append(
            f"=== LÄNGD ===\nSkriv en sammanhängande scen på högst {length} ord "
            f"(cirka {pages(length)} sidor). Avsluta när scenen är slut. Upprepa aldrig "
            "stycken eller meningar för att nå ett ordantal — hellre kort än upprepad."
        )

    extra = str(brief.get("extra") or "").strip()
    if extra:
        sections.append("=== EXTRA INSTRUKTIONER ===\n" + extra)

    user = "\n\n".join(section for section in sections if section.strip())
    combined = f"{system}\n\n{user}"
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    return {
        "system": system,
        "user": user,
        "messages": messages,
        "prompt": combined,
        "words": length,
        "sex_level": level,
    }


def validate_brief(brief: dict, mode: str = "new", continuation: str = "") -> None:
    """Kasta ValueError med ett meddelande som går att visa direkt."""
    if mode == "continue":
        if len((continuation or "").strip()) < 40:
            raise ValueError("Det finns ingen text att fortsätta på. Skriv eller klistra in text först.")
        return
    scene = str(brief.get("scene") or "").strip()
    place = str(brief.get("place") or "").strip()
    characters = str(brief.get("characters") or "").strip()
    if len(scene) < 15 and not (place and characters):
        raise ValueError(
            "Beskriv scenen lite mer — minst en rad om vad som händer, eller både plats och personer."
        )
    total = len(scene) + len(place) + len(characters)
    if total > 8000:
        raise ValueError("Uppgiften är för lång (över 8 000 tecken). Korta den.")


def prompt_stats(prompt: str) -> dict:
    words = rag.count_words(prompt)
    # Svensk prosa ligger kring 3 tecken per token. Snarare över än under —
    # gränsen mot serverns kontext får inte underskattas.
    tokens = max(1, math.ceil(len(prompt) / 3.0))
    return {
        "characters": len(prompt),
        "words": words,
        "estimated_tokens": tokens,
    }
