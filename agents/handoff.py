"""Ajanlar arasında taşınan bağlamı kısa özete indirger."""

from __future__ import annotations

import re

WORD_LIMIT = 200
_AMOUNT = re.compile(r"(\d[\d.\s]*\d|\d)\s*(tl|try|usd|eur|%)|%\s*\d|\b\d{2,}(?:[.,]\d+)?\b", re.IGNORECASE)


def compact_handoff(text: str, *, limit: int = WORD_LIMIT) -> str:
    """Düz metni en fazla `limit` kelimeye indirir; tutar satırlarını ayrıca korur."""
    raw = (text or "").strip()
    if not raw:
        return ""
    prose: list[str] = []
    numbers: list[str] = []
    for line in raw.splitlines():
        stripped = re.sub(r"\s+", " ", line).strip(" -\t")
        if not stripped or stripped.startswith("#"):
            continue
        if _AMOUNT.search(stripped):
            if stripped not in numbers:
                numbers.append(stripped)
            continue
        prose.append(stripped)
    words = " ".join(prose).split()
    summary = " ".join(words[:limit])
    if len(words) > limit:
        summary = summary.rstrip(".,;:") + "…"
    if not summary:
        summary = "Önceki ajan sayısal sonuç bıraktı."
    parts = ["Yönetici Özeti:", summary]
    if numbers:
        parts.append("Sayısal veriler:")
        parts.extend(f"- {line}" for line in numbers[:16])
    return "\n".join(parts)
