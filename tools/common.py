"""Araçların paylaştığı biçim ve metin yardımcıları."""

from __future__ import annotations

import re

COMPANY = "Kuzey Yazılım A.Ş."
DISCLAIMER = "Kaynak: örnek şirket verisi (mock). Canlı sisteme bağlı değildir."

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


def mentions_record(text: str, *, name: str, record_id: str) -> bool:
    folded = fold(text)
    if record_id and contains_term(folded, fold(record_id)):
        return True
    full = fold(name)
    if full and full in folded:
        return True
    parts = [part for part in full.split() if part]
    return len(parts) >= 2 and all(contains_term(folded, part) for part in parts)


def tl(amount: float | int) -> str:
    sign = "-" if amount < 0 else ""
    grouped = f"{abs(round(amount)):,}".replace(",", ".")
    return f"{sign}{grouped} TL"


def pct(part: float, whole: float) -> str:
    if whole == 0:
        return "%0,0"
    value = f"{part / whole * 100:.1f}".replace(".", ",")
    return f"%{value}"


def text_table(headers: list[str], rows: list[list[str]]) -> str:
    widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    def format_row(row: list[str]) -> str:
        return "  ".join(cell.ljust(widths[index]) for index, cell in enumerate(row))

    lines = [format_row(headers), format_row(["-" * width for width in widths])]
    lines.extend(format_row(row) for row in rows)
    return "\n".join(lines)


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


DEPARTMENTS: dict[str, tuple[str, ...]] = {
    "İK": ("insan kaynaklari", "insan kaynak", "ik"),
    "Finans": ("muhasebe", "finans"),
    "Operasyon": ("operasyon",),
    "Yazılım": ("yazilim",),
    "Satış": ("satis",),
}


def detect_department(text: str) -> str:
    folded = fold(text)
    pairs = sorted(
        ((alias, name) for name, aliases in DEPARTMENTS.items() for alias in aliases),
        key=lambda item: len(item[0]),
        reverse=True,
    )
    for alias, name in pairs:
        if contains_term(folded, alias):
            return name
    return ""
