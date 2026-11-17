"""BCD TECHNOLOGIES satış hunisi. Fırsatlar data/crm.json içinde durur."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from tools import finance_tools
from tools.json_store import json_lock, save_json_safe

ROOT = Path(__file__).resolve().parents[1]
CRM_PATH = ROOT / "data" / "crm.json"
STATUSES = ("Taslak", "Gönderildi", "Görüşmede", "Kazanıldı", "Kaybedildi")
OPEN_STATUSES = ("Taslak", "Gönderildi", "Görüşmede", "Kazanıldı")


def empty_crm() -> dict:
    return {"opportunities": []}


def load_crm() -> dict:
    if not CRM_PATH.is_file():
        return empty_crm()
    payload = json.loads(CRM_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return empty_crm()
    rows = payload.get("opportunities")
    payload["opportunities"] = [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
    return payload


def save_crm(payload: dict) -> None:
    save_json_safe(CRM_PATH, payload)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _next_id(rows: list[dict]) -> str:
    best = 0
    for row in rows:
        raw = str(row.get("id") or "")
        if raw.startswith("crm-") and raw[4:].isdigit():
            best = max(best, int(raw[4:]))
    return f"crm-{best + 1}"


def _amount(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("teklif tutarı sayı olmalı")
    if value < 0:
        raise ValueError("teklif tutarı negatif olamaz")
    return float(value)


def _clean(value: object, *, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _public(row: dict) -> dict:
    return {
        "id": str(row.get("id") or ""),
        "musteri_adi": str(row.get("musteri_adi") or ""),
        "proje_basligi": str(row.get("proje_basligi") or ""),
        "teklif_tutari": float(row.get("teklif_tutari") or 0),
        "para_birimi": str(row.get("para_birimi") or "TRY"),
        "durum": str(row.get("durum") or "Taslak"),
        "olusturma_tarihi": str(row.get("olusturma_tarihi") or ""),
        "notlar": str(row.get("notlar") or ""),
    }


def pipeline_summary(rows: list[dict]) -> dict:
    open_rows = [row for row in rows if row.get("durum") in OPEN_STATUSES]
    currencies = {str(row.get("para_birimi") or "TRY") for row in open_rows}
    total = sum(float(row.get("teklif_tutari") or 0) for row in open_rows)
    if not currencies:
        currency = "TRY"
    elif len(currencies) == 1:
        currency = currencies.pop()
    else:
        currency = "Karma"
    return {"pipeline_total": total, "pipeline_currency": currency}


def list_opportunities() -> dict:
    rows = [_public(row) for row in load_crm().get("opportunities") or []]
    return {"opportunities": rows, **pipeline_summary(rows)}


def create_opportunity(fields: dict) -> dict:
    customer = _clean(fields.get("musteri_adi"), limit=160)
    if len(customer) < 2:
        raise ValueError("müşteri adı gerekli")
    status = _clean(fields.get("durum") or "Taslak", limit=40) or "Taslak"
    if status not in STATUSES:
        raise ValueError("durum geçersiz")
    with json_lock(CRM_PATH):
        payload = load_crm()
        rows = list(payload.get("opportunities") or [])
        row = {
            "id": _next_id(rows),
            "musteri_adi": customer,
            "proje_basligi": _clean(fields.get("proje_basligi"), limit=160),
            "teklif_tutari": _amount(fields.get("teklif_tutari") or 0),
            "para_birimi": (_clean(fields.get("para_birimi") or "TRY", limit=8) or "TRY").upper(),
            "durum": status,
            "olusturma_tarihi": _now(),
            "notlar": _clean(fields.get("notlar"), limit=2000),
        }
        rows.append(row)
        payload["opportunities"] = rows
        save_crm(payload)
    sync_deal_income(row)
    return _public(row)


def update_opportunity(opportunity_id: str, fields: dict) -> dict:
    with json_lock(CRM_PATH):
        payload = load_crm()
        rows = list(payload.get("opportunities") or [])
        found = next((row for row in rows if str(row.get("id") or "") == opportunity_id), None)
        if found is None:
            raise LookupError(opportunity_id)
        if "musteri_adi" in fields and fields["musteri_adi"] is not None:
            customer = _clean(fields["musteri_adi"], limit=160)
            if len(customer) < 2:
                raise ValueError("müşteri adı gerekli")
            found["musteri_adi"] = customer
        if "proje_basligi" in fields and fields["proje_basligi"] is not None:
            found["proje_basligi"] = _clean(fields["proje_basligi"], limit=160)
        if "teklif_tutari" in fields and fields["teklif_tutari"] is not None:
            found["teklif_tutari"] = _amount(fields["teklif_tutari"])
        if "para_birimi" in fields and fields["para_birimi"] is not None:
            found["para_birimi"] = (_clean(fields["para_birimi"], limit=8) or "TRY").upper()
        if "durum" in fields and fields["durum"] is not None:
            status = _clean(fields["durum"], limit=40)
            if status not in STATUSES:
                raise ValueError("durum geçersiz")
            found["durum"] = status
        if "notlar" in fields and fields["notlar"] is not None:
            found["notlar"] = _clean(fields["notlar"], limit=2000)
        payload["opportunities"] = rows
        save_crm(payload)
        public = _public(found)
    sync_deal_income(public)
    return public


def delete_opportunity(opportunity_id: str) -> None:
    with json_lock(CRM_PATH):
        payload = load_crm()
        rows = list(payload.get("opportunities") or [])
        kept = [row for row in rows if str(row.get("id") or "") != opportunity_id]
        if len(kept) == len(rows):
            raise LookupError(opportunity_id)
        payload["opportunities"] = kept
        save_crm(payload)
    sync_deal_income({"id": opportunity_id, "durum": "Kaybedildi"})


def sync_deal_income(deal: dict) -> None:
    """Kazanılan fırsatı tek bir gelir satırına bağlar. Gider toplamına eklemez."""
    income_id = str(deal.get("id") or "")
    won = deal.get("durum") == "Kazanıldı"
    with json_lock(finance_tools.LEDGER_PATH):
        ledger = finance_tools.load_ledger()
        rows = [row for row in ledger.get("income") or [] if str(row.get("id") or "") != income_id]
        if won:
            rows.append(
                {
                    "id": income_id,
                    "name": f"{deal.get('musteri_adi') or 'Müşteri'} · {deal.get('proje_basligi') or 'Teklif'}",
                    "category": str(deal.get("para_birimi") or "TRY"),
                    "amount": float(deal.get("teklif_tutari") or 0),
                    "project": str(deal.get("proje_basligi") or ""),
                    "source": str(deal.get("id") or ""),
                }
            )
        if rows:
            ledger["income"] = rows
        else:
            ledger.pop("income", None)
        finance_tools.save_ledger(ledger)
