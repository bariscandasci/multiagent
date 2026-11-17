"""Araçların paylaştığı biçim ve metin yardımcıları."""

from __future__ import annotations

import re

COMPANY = "BCD TECHNOLOGIES"
DISCLAIMER = "Kaynak: BCD TECHNOLOGIES finans defteri ve data/projeler altındaki kayıtlar."

_FOLDS = str.maketrans(
    {
        "ı": "i",
        "ş": "s",
        "ğ": "g",
        "ü": "u",
        "ö": "o",
        "ç": "c",
        "â": "a",
        "î": "i",
        "û": "u",
    }
)


def fold(text: str) -> str:
    """Türkçe karakterleri sadeleştirip küçük harfe çevirir. Eşleştirme içindir."""
    cleaned = (text or "").replace("İ", "i").replace("I", "i")
    return cleaned.lower().translate(_FOLDS)


def contains_term(text: str, term: str) -> bool:
    """Katlanmış metinde terimi arar. Kısa kelimeler tam, uzunlar ek alabilir."""
    if not term:
        return False
    if " " in term:
        return term in text
    if len(term) <= 3:
        pattern = rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])"
    else:
        pattern = rf"(?<![a-z0-9]){re.escape(term)}"
    return re.search(pattern, text) is not None


def tl(amount: float | int) -> str:
    sign = "-" if amount < 0 else ""
    grouped = f"{abs(round(amount)):,}".replace(",", ".")
    return f"{sign}{grouped} TL"


def pct(part: float, whole: float) -> str:
    if whole == 0:
        return "%0,0"
    value = f"{part / whole * 100:.1f}".replace(".", ",")
    return f"%{value}"


def dedupe_calls(calls: list[tuple[str, dict]]) -> list[tuple[str, dict]]:
    seen: set[tuple] = set()
    unique: list[tuple[str, dict]] = []
    for name, args in calls:
        signature = tuple(
            sorted((str(item_key), repr(item_value)) for item_key, item_value in args.items())
        )
        marker = (name, signature)
        if marker in seen:
            continue
        seen.add(marker)
        unique.append((name, args))
    return unique
