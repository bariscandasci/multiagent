"""Finans mock araçları. Tutarlar uydurma defter kayıtlarıdır."""

from __future__ import annotations

from langchain_core.tools import tool

from tools.common import COMPANY, detect_department, fold, pct, text_table, tl

LEDGER: list[dict[str, int | str]] = [
    {"month": "2026-06", "revenue": 980_000, "expense": 740_000},
    {"month": "2026-07", "revenue": 1_050_000, "expense": 760_000},
    {"month": "2026-08", "revenue": 1_120_000, "expense": 810_000},
    {"month": "2026-09", "revenue": 1_250_000, "expense": 890_000},
    {"month": "2026-10", "revenue": 1_180_000, "expense": 870_000},
    {"month": "2026-11", "revenue": 1_090_000, "expense": 840_000},
]

INVOICES: list[dict[str, int | str]] = [
    {
        "id": "F-2026-096",
        "party": "Atlas Lojistik",
        "kind": "alacak",
        "amount": 310_000,
        "status": "open",
        "due": "2026-11-28",
    },
    {
        "id": "F-2026-091",
        "party": "Marmara Tedarik",
        "kind": "borç",
        "amount": 125_000,
        "status": "open",
        "due": "2026-11-20",
    },
    {
        "id": "F-2026-084",
        "party": "Bulut Host",
        "kind": "borç",
        "amount": 18_600,
        "status": "overdue",
        "due": "2026-10-30",
    },
    {
        "id": "F-2026-088",
        "party": "Kuzey Ofis",
        "kind": "borç",
        "amount": 42_000,
        "status": "paid",
        "due": "2026-10-15",
    },
    {
        "id": "F-2026-079",
        "party": "Ege Yazılım",
        "kind": "alacak",
        "amount": 86_000,
        "status": "paid",
        "due": "2026-09-30",
    },
]

BUDGETS: list[dict[str, int | str]] = [
    {"department": "Yazılım", "annual": 2_400_000, "spent": 1_860_000},
    {"department": "Operasyon", "annual": 1_200_000, "spent": 980_000},
    {"department": "Satış", "annual": 900_000, "spent": 640_000},
    {"department": "İK", "annual": 450_000, "spent": 310_000},
    {"department": "Finans", "annual": 380_000, "spent": 290_000},
]

_STATUS_ALIASES = {
    "open": "open",
    "acik": "open",
    "bekleyen": "open",
    "odenmemis": "open",
    "paid": "paid",
    "odendi": "paid",
    "odenen": "paid",
    "kapali": "paid",
    "overdue": "overdue",
    "gecikmis": "overdue",
    "geciken": "overdue",
}
_STATUS_LABEL = {"open": "açık", "paid": "ödendi", "overdue": "gecikmiş"}


def _period_rows(period: str) -> tuple[str, list[dict[str, int | str]]]:
    key = fold(period or "quarter")
    if key in {"month", "ay", "bu ay", "aylik"}:
        return "son ay", LEDGER[-1:]
    if key in {"year", "yil", "yillik"}:
        return "kayıtlı tüm aylar", LEDGER
    return "son çeyrek", LEDGER[-3:]


@tool
def income_expense_summary(period: str = "quarter") -> str:
    """Gelir, gider ve kâr özetini hesaplar.

    period: month (son ay), quarter (son 3 ay) veya year (kayıtlı tüm aylar).
    """
    label, rows = _period_rows(period)
    table_rows: list[list[str]] = []
    revenue_total = 0
    expense_total = 0
    for row in rows:
        revenue = int(row["revenue"])
        expense = int(row["expense"])
        revenue_total += revenue
        expense_total += expense
        table_rows.append(
            [str(row["month"]), tl(revenue), tl(expense), tl(revenue - expense)]
        )
    profit = revenue_total - expense_total
    lines = [
        f"{COMPANY} gelir-gider özeti ({label})",
        "",
        text_table(["Dönem", "Gelir", "Gider", "Kâr"], table_rows),
        "",
        f"Toplam gelir: {tl(revenue_total)}",
        f"Toplam gider: {tl(expense_total)}",
        f"Net kâr: {tl(profit)}",
        f"Kâr marjı: {pct(profit, revenue_total)}",
    ]
    return "\n".join(lines)


@tool
def list_invoices(status: str = "") -> str:
    """Alacak ve borç faturalarını listeler.

    status boşsa tümü gelir. Kabul edilen değerler: open, paid, overdue
    veya açık, ödendi, gecikmiş.
    """
    requested = fold(status or "")
    canonical = _STATUS_ALIASES.get(requested, "")
    rows = INVOICES
    label = "tümü"
    if requested:
        if not canonical:
            known = "açık, ödendi, gecikmiş"
            return f"'{status}' fatura durumu tanınmadı. Kullanılabilecekler: {known}."
        rows = [row for row in INVOICES if row["status"] == canonical]
        label = _STATUS_LABEL[canonical]
        if not rows:
            return f"{label} durumunda fatura yok."

    lines = [f"{COMPANY} faturalar ({label})", ""]
    receivable = 0
    payable = 0
    for row in rows:
        amount = int(row["amount"])
        if row["status"] != "paid":
            if row["kind"] == "alacak":
                receivable += amount
            else:
                payable += amount
        lines.append(
            f"- {row['id']} {row['party']} — {row['kind']} — {tl(amount)} — "
            f"{_STATUS_LABEL[str(row['status'])]} — vade {row['due']}"
        )
    lines.append("")
    lines.append(f"Ödenmemiş alacak: {tl(receivable)}")
    lines.append(f"Ödenmemiş borç: {tl(payable)}")
    return "\n".join(lines)


@tool
def budget_summary(department: str = "") -> str:
    """Yıllık departman bütçesini, harcananı ve kalanı döndürür.

    department boşsa bütün departmanlar gelir.
    """
    requested = (department or "").strip()
    rows = BUDGETS
    label = "tüm departmanlar"
    if requested:
        target = detect_department(requested) or requested
        rows = [row for row in BUDGETS if fold(str(row["department"])) == fold(target)]
        label = target
        if not rows:
            known = ", ".join(str(row["department"]) for row in BUDGETS)
            return f"'{requested}' için bütçe kaydı yok. Kayıtlı departmanlar: {known}."

    lines = [f"{COMPANY} bütçe özeti ({label})", ""]
    annual_total = 0
    spent_total = 0
    for row in rows:
        annual = int(row["annual"])
        spent = int(row["spent"])
        annual_total += annual
        spent_total += spent
        remaining = annual - spent
        lines.append(
            f"- {row['department']}: yıllık {tl(annual)}, harcanan {tl(spent)}, "
            f"kalan {tl(remaining)} ({pct(spent, annual)} kullanıldı)"
        )
    lines.append("")
    lines.append(f"Toplam yıllık bütçe: {tl(annual_total)}")
    lines.append(f"Toplam harcanan: {tl(spent_total)}")
    lines.append(f"Toplam kalan: {tl(annual_total - spent_total)}")
    return "\n".join(lines)


FINANCE_TOOLS = [income_expense_summary, list_invoices, budget_summary]
