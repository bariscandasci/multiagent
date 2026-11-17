"""Yönetici raporunu dört panele böler."""

from __future__ import annotations

import re


def _lead(text: str) -> str:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    return paragraphs[0] if paragraphs else text.strip()


def split_report(answer: str, department: str) -> dict[str, str]:
    """Brief raporunu yönetici, pazar, Ar-Ge ve finans metinlerine ayırır."""
    sections = {"executive": "", "market": "", "rnd": "", "finance": ""}
    parts = re.split(r"(?m)^##\s+", answer or "")
    preamble = parts[0].strip()
    found = False
    for part in parts[1:]:
        lines = part.splitlines()
        title = fold_heading(lines[0] if lines else "")
        body = "\n".join(lines[1:]).strip()
        if "pazar" in title:
            sections["market"] = body
            found = True
        elif "ar-ge" in title or "arge" in title or "teknik" in title:
            sections["rnd"] = body
            found = True
        elif "maliyet" in title or "finans" in title or "kar" in title:
            sections["finance"] = body
            found = True
    if found:
        sections["executive"] = preamble
        return sections
    target = {"market": "market", "rnd": "rnd", "finance": "finance"}.get(department, "executive")
    sections[target] = (answer or "").strip()
    if target == "executive":
        sections["executive"] = (answer or "").strip()
    else:
        sections["executive"] = _lead(answer or "")
    return sections


def fold_heading(value: str) -> str:
    cleaned = value.strip().lower()
    return (
        cleaned.replace("ı", "i")
        .replace("ş", "s")
        .replace("ğ", "g")
        .replace("ü", "u")
        .replace("ö", "o")
        .replace("ç", "c")
        .replace("â", "a")
        .replace("î", "i")
        .replace("û", "u")
    )
