"""BCD TECHNOLOGIES finans defteri. Tutarlar data/finans/giderler.json içinden okunur."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from langchain_core.tools import tool

from tools.common import COMPANY, fold, pct, tl
from tools.json_store import json_lock, save_json_safe

ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = ROOT / "data" / "finans" / "giderler.json"
TARGET_MARGIN = 0.35


def empty_ledger() -> dict:
    return {
        "company": COMPANY,
        "currency": "TRY",
        "fixed_monthly": [],
        "project_costs": [],
    }


def load_ledger() -> dict:
    if not LEDGER_PATH.exists():
        return empty_ledger()
    payload = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    payload.setdefault("company", COMPANY)
    payload.setdefault("currency", "TRY")
    payload.setdefault("fixed_monthly", [])
    payload.setdefault("project_costs", [])
    payload.setdefault("income", [])
    return payload


def save_ledger(payload: dict) -> None:
    payload["company"] = COMPANY
    payload["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    save_json_safe(LEDGER_PATH, payload)


def _amount(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("tutar sayı olmalı")
    if value < 0:
        raise ValueError("tutar negatif olamaz")
    return float(value)


def _fixed_total(ledger: dict) -> float:
    return sum(float(item.get("amount") or 0) for item in ledger.get("fixed_monthly") or [])


def _project_rows(ledger: dict, project: str) -> list[dict]:
    rows = list(ledger.get("project_costs") or [])
    needle = fold(project)
    if not needle:
        return rows
    return [row for row in rows if needle in fold(str(row.get("project") or ""))]


def _next_id(prefix: str, rows: list[dict]) -> str:
    best = 0
    for row in rows:
        raw = str(row.get("id") or "")
        head = f"{prefix}-"
        if raw.startswith(head) and raw[len(head):].isdigit():
            best = max(best, int(raw[len(head):]))
    return f"{prefix}-{best + 1}"


def ledger_totals(ledger: dict | None = None) -> dict[str, float]:
    payload = ledger if ledger is not None else load_ledger()
    fixed = _fixed_total(payload)
    project = sum(float(item.get("amount") or 0) for item in payload.get("project_costs") or [])
    if project > 0:
        recommended = round(project / (1 - TARGET_MARGIN))
        profit = float(recommended - project)
    else:
        profit = 0.0
    realized = sum(
        float(item.get("amount") or 0)
        for item in payload.get("income") or []
        if str(item.get("category") or "TRY").upper() in {"TRY", "TL", ""}
    )
    return {
        "fixed_total": fixed,
        "project_total": project,
        "monthly_total": fixed + project,
        "target_profit": profit,
        "realized_income": realized,
    }


def _find_row(ledger: dict, expense_id: str) -> tuple[str, dict] | None:
    for bucket in ("fixed_monthly", "project_costs"):
        for row in ledger.get(bucket) or []:
            if str(row.get("id") or "") == expense_id:
                return bucket, row
    return None


def delete_expense_row(expense_id: str) -> str:
    """Defter satırını kimliğine göre siler. Bulunamazsa Hata ile başlayan metin döner."""
    with json_lock(LEDGER_PATH):
        return _delete_expense_row(expense_id)


def _delete_expense_row(expense_id: str) -> str:
    ledger = load_ledger()
    found = _find_row(ledger, expense_id)
    if found is None:
        return "Hata: gider bulunamadı."
    bucket, row = found
    ledger[bucket] = [item for item in ledger[bucket] if item is not row]
    save_ledger(ledger)
    return f"{COMPANY} defterinden silindi: {row.get('name')}."


def update_expense_row(
    expense_id: str,
    name: str | None = None,
    amount: float | None = None,
    category: str | None = None,
    project: str | None = None,
) -> str:
    """Defter satırını yerinde günceller. Proje alanı doluysa satır proje maliyetine taşınır."""
    with json_lock(LEDGER_PATH):
        return _update_expense_row(expense_id, name, amount, category, project)


def _update_expense_row(
    expense_id: str,
    name: str | None,
    amount: float | None,
    category: str | None,
    project: str | None,
) -> str:
    ledger = load_ledger()
    found = _find_row(ledger, expense_id)
    if found is None:
        return "Hata: gider bulunamadı."
    bucket, row = found
    if name is not None:
        cleaned = name.strip()
        if not cleaned:
            return "Hata: gider adı gerekli."
        row["name"] = cleaned
    if amount is not None:
        try:
            row["amount"] = _amount(amount)
        except ValueError as exc:
            return f"Hata: {exc}"
    if category is not None and category.strip():
        row["category"] = category.strip()
    if project is not None:
        project_name = project.strip()
        if bucket == "fixed_monthly" and project_name:
            ledger["fixed_monthly"] = [item for item in ledger["fixed_monthly"] if item is not row]
            row["project"] = project_name
            ledger["project_costs"].append(row)
        elif bucket == "project_costs" and not project_name:
            ledger["project_costs"] = [item for item in ledger["project_costs"] if item is not row]
            row.pop("project", None)
            ledger["fixed_monthly"].append(row)
        elif project_name:
            row["project"] = project_name
    save_ledger(ledger)
    return f"{COMPANY} defterinde güncellendi: {row.get('name')} — {tl(float(row.get('amount') or 0))}."


@tool
def get_monthly_expenses() -> str:
    """BCD TECHNOLOGIES aylık sabit giderlerini ve proje teknoloji maliyetlerini listeler."""
    ledger = load_ledger()
    lines = [f"{COMPANY} aylık gider defteri", ""]
    fixed_rows = list(ledger.get("fixed_monthly") or [])
    if not fixed_rows:
        lines.append("Sabit gider satırı yok.")
    else:
        lines.append("Sabit giderler:")
        for item in fixed_rows:
            lines.append(f"- {item.get('name')} ({item.get('category') or 'sabit'}): {tl(float(item.get('amount') or 0))}")
    fixed = _fixed_total(ledger)
    lines.append(f"Aylık sabit gider toplamı: {tl(fixed)}")
    lines.append("")
    project_rows = list(ledger.get("project_costs") or [])
    if not project_rows:
        lines.append("Proje bazlı teknoloji veya altyapı maliyeti yok.")
    else:
        lines.append("Proje maliyetleri:")
        for item in project_rows:
            lines.append(
                f"- {item.get('project')}: {item.get('name')} ({item.get('category') or 'teknoloji'}): {tl(float(item.get('amount') or 0))}"
            )
        project_total = sum(float(item.get("amount") or 0) for item in project_rows)
        lines.append(f"Proje maliyetleri toplamı: {tl(project_total)}")
    return "\n".join(lines)


@tool
def add_expense(name: str, amount: float, category: str = "", project: str = "") -> str:
    """Gider ekler. project boşsa aylık sabit giderdir; doluysa proje teknoloji/altyapı maliyetidir.

    amount aylık tutardır ve 0 veya daha büyük olmalıdır.
    """
    try:
        value = _amount(amount)
    except ValueError as exc:
        return f"Hata: {exc}"
    cleaned = name.strip()
    if not cleaned:
        return "Hata: gider adı gerekli."
    with json_lock(LEDGER_PATH):
        return _add_expense_row(cleaned, value, category, project)


def _add_expense_row(cleaned: str, value: float, category: str, project: str) -> str:
    ledger = load_ledger()
    project_name = project.strip()
    if project_name:
        row = {
            "id": _next_id("pj", ledger["project_costs"]),
            "project": project_name,
            "name": cleaned,
            "category": category.strip() or "teknoloji",
            "amount": value,
        }
        ledger["project_costs"].append(row)
        kind = "proje maliyeti"
    else:
        row = {
            "id": _next_id("fx", ledger["fixed_monthly"]),
            "name": cleaned,
            "category": category.strip() or "sabit",
            "amount": value,
        }
        ledger["fixed_monthly"].append(row)
        kind = "sabit gider"
    save_ledger(ledger)
    return f"{COMPANY} defterine {kind} yazıldı: {cleaned} — {tl(value)}."


@tool
def simulate_project_budget(
    project: str,
    monthly_price: float = 0,
    extra_monthly_cost: float = 0,
    note: str = "",
) -> str:
    """Yeni iş veya ek teknoloji maliyeti için fiyat önerisi ve net kâr simülasyonu yapar.

    monthly_price teklif edilen aylık bedeldir. 0 ise doğrudan maliyet üzerinden fiyat önerilir.
    extra_monthly_cost henüz deftere yazılmamış ek sunucu, API veya lisans tutarıdır.
    """
    try:
        price = _amount(monthly_price)
        extra = _amount(extra_monthly_cost)
    except ValueError as exc:
        return f"Hata: {exc}"
    ledger = load_ledger()
    project_name = project.strip() or "yeni iş"
    rows = _project_rows(ledger, project_name)
    direct = sum(float(item.get("amount") or 0) for item in rows) + extra
    fixed = _fixed_total(ledger)
    if direct > 0:
        recommended = round(direct / (1 - TARGET_MARGIN))
    else:
        recommended = 0
    sale = price if price > 0 else recommended
    net = sale - direct
    lines = [
        f"{COMPANY} proje bütçe simülasyonu — {project_name}",
        f"Doğrudan aylık maliyet: {tl(direct)}",
    ]
    if rows:
        for item in rows:
            lines.append(f"- {item.get('name')}: {tl(float(item.get('amount') or 0))}")
    if extra:
        lines.append(f"- Ek teknoloji / sunucu / API: {tl(extra)}")
    if not rows and not extra:
        lines.append("Bu proje için kayıtlı teknoloji maliyeti yok.")
    lines.append(f"Önerilen aylık fiyat (%35 brüt marj): {tl(recommended)}")
    if price > 0:
        lines.append(f"Değerlendirilen teklif: {tl(price)}")
    lines.append(f"Doğrudan net: {tl(net)} ({pct(net, sale) if sale else '%0,0'})")
    lines.append(f"Şirket aylık sabit gideri: {tl(fixed)}")
    lines.append(f"Sabit gider sonrası katkı: {tl(sale - direct - fixed)}")
    if note.strip():
        lines.append(f"Not: {note.strip()}")
    return "\n".join(lines)


def parse_amount(text: str) -> float | None:
    match = re.search(r"(\d+(?:[.\s]\d{3})+|\d+)(?:[,.]\d+)?", fold(text))
    if not match:
        return None
    digits = re.sub(r"[^\d]", "", match.group(1))
    if not digits:
        return None
    return float(digits)


FINANCE_TOOLS = [get_monthly_expenses, add_expense, simulate_project_budget]
