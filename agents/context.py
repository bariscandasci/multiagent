"""Kalıcı ajan direktifleri ve şirket hafızası."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from config import get_settings
from tools.common import COMPANY
from tools.json_store import json_lock, save_json_safe

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "data" / "ajan_ayarlari.json"
MEMORY_PATH = ROOT / "data" / "hafiza.json"

AGENT_IDS = ("supervisor", "market", "rnd", "finance")

DEFAULT_DIRECTIVES: dict[str, str] = {
    "supervisor": (
        f"Sen {COMPANY} içindeki yönlendiricisin. İsteği tek bir route değerine ayır.\n"
        "market: sektör, müşteri, satış stratejisi.\n"
        "finance: gider, maliyet, fiyat, kâr.\n"
        "rnd: kod, kütüphane, Ar-Ge yol haritası.\n"
        "brief: GitHub deposu veya pazar, teknik ve finansın birlikte istendiği inceleme.\n"
        "general: selamlama veya belirsiz istek.\n"
        "Kısa takip cümlesinde önceki akışı koru."
    ),
    "market": (
        f"Sen {COMPANY} içindeki Operasyon ve Pazar Geliştirme ajanısın.\n"
        "Projeyi fetch_github_repo veya read_project ile oku. Dosyada olmayan müşteri, sektör veya fiyat uydurma.\n"
        "Hangi sektörlere, hangi ölçekteki firmalara ve hangi karar vericilere satılabileceğini yaz.\n"
        f"Değer önerisini ve üç adımlık satış stratejisini {COMPANY} adına, Türkçe ve kısa tut."
    ),
    "rnd": (
        f"Sen {COMPANY} içindeki Teknik ve Ar-Ge ajanısın.\n"
        "Depodaki dosya ağacını ve bağımlılık dosyalarını read_project ile oku. Repoda olmayan kütüphane sürümü veya metrik yazma.\n"
        "Projeyi rakiplerinden ayıracak özelliği, eklenebilecek güncel kütüphaneleri, yapay zeka entegrasyonunu "
        "ve adım adım Ar-Ge yol haritasını Türkçe yaz."
    ),
    "finance": (
        f"Sen {COMPANY} içindeki Muhasebe ve Finans ajanısın.\n"
        "Tutarları yalnızca get_monthly_expenses, add_expense ve simulate_project_budget sonuçlarından yaz.\n"
        "Aylık sabit gideri, yeni bir iş veya ek teknoloji maliyetini, önerilen fiyatı ve net kârı Türkçe özetle.\n"
        "Deftere yazılmayan tutarı gerçekleşmiş gider gibi gösterme."
    ),
}


def _clamp_temperature(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    return max(0.0, min(2.0, number))


def _read_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _saved_agents() -> dict[str, dict]:
    payload = _read_json(CONFIG_PATH) or {}
    found: dict[str, dict] = {}
    for item in payload.get("agents") or []:
        if isinstance(item, dict) and item.get("id") in AGENT_IDS:
            found[str(item["id"])] = item
    return found


def agent_settings(agent_id: str) -> dict:
    saved = _saved_agents().get(agent_id) or {}
    directive = str(saved.get("directive") or "").strip() or DEFAULT_DIRECTIVES[agent_id]
    if "temperature" in saved and saved.get("temperature") is not None:
        temperature = _clamp_temperature(saved.get("temperature"))
        explicit = True
    else:
        temperature = _clamp_temperature(get_settings().temperature)
        explicit = False
    return {"directive": directive, "temperature": temperature, "explicit_temperature": explicit}


def agent_temperature(agent_id: str) -> float | None:
    """Kayıtlı sıcaklık varsa onu, yoksa ortam değişkeninin geçerli olması için None döndürür."""
    saved = _saved_agents().get(agent_id) or {}
    if "temperature" not in saved or saved.get("temperature") is None:
        return None
    return _clamp_temperature(saved.get("temperature"))


def memory_notes() -> list[dict]:
    payload = _read_json(MEMORY_PATH) or {}
    notes = []
    for item in payload.get("notes") or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        notes.append(
            {
                "id": str(item.get("id") or ""),
                "text": text,
                "created_at": str(item.get("created_at") or ""),
            }
        )
    return notes


def memory_block() -> str:
    notes = memory_notes()
    if not notes:
        return ""
    lines = [
        f"{COMPANY} şirket hafızası. Aşağıdaki kuralları uydurmadan uygula:",
        *[f"- {note['text']}" for note in notes],
    ]
    return "\n".join(lines)


def compose_prompt(agent_id: str, fallback: str, extra: str = "", query: str = "") -> str:
    directive = agent_settings(agent_id)["directive"] if agent_id in DEFAULT_DIRECTIVES else fallback
    if not str(directive).strip():
        directive = fallback
    parts = [str(directive).strip()]
    if extra.strip():
        parts.append(extra.strip())
    memory = memory_block()
    if memory:
        parts.append(memory)
    if query.strip() and agent_id in DEFAULT_DIRECTIVES:
        from tools.knowledge import reference_block

        reference = reference_block(agent_id, query)
        if reference:
            parts.append(reference)
    return "\n\n".join(part for part in parts if part)


def save_agents(agents: list[dict]) -> list[dict]:
    incoming = {str(item.get("id") or ""): item for item in agents}
    rows = []
    for agent_id in AGENT_IDS:
        item = incoming.get(agent_id) or {}
        directive = str(item.get("directive") or "").strip() or DEFAULT_DIRECTIVES[agent_id]
        rows.append(
            {
                "id": agent_id,
                "directive": directive,
                "temperature": _clamp_temperature(item.get("temperature", 0)),
            }
        )
    save_json_safe(CONFIG_PATH, {"agents": rows})
    return rows


def _next_note_id(notes: list[dict]) -> str:
    best = 0
    for note in notes:
        raw = str(note.get("id") or "")
        if raw.startswith("mem-") and raw[4:].isdigit():
            best = max(best, int(raw[4:]))
    return f"mem-{best + 1}"


def add_note(text: str) -> dict:
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("hafıza metni gerekli")
    with json_lock(MEMORY_PATH):
        notes = memory_notes()
        note = {
            "id": _next_note_id(notes),
            "text": cleaned,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        notes.append(note)
        _write_notes(notes)
    return note


def delete_note(note_id: str) -> bool:
    with json_lock(MEMORY_PATH):
        notes = memory_notes()
        kept = [note for note in notes if note["id"] != note_id]
        if len(kept) == len(notes):
            return False
        _write_notes(kept)
    return True


def _write_notes(notes: list[dict]) -> None:
    save_json_safe(MEMORY_PATH, {"notes": notes})
