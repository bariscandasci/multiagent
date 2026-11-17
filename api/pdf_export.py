"""BCD TECHNOLOGIES kurumsal teklif PDF'i. Türkçe metin gömülü DejaVu ile yazılır."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from fpdf import FPDF

from tools.common import COMPANY, fold, tl
from tools.finance_tools import ledger_totals, load_ledger

FONT_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"
SECTIONS = (
    ("executive", "Yönetici Özeti"),
    ("market", "Operasyon ve Pazar Geliştirme"),
    ("rnd", "Teknik ve Ar-Ge"),
    ("finance", "Muhasebe ve Finans"),
)


def pdf_filename(project_name: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", fold(project_name or "")).strip("-")
    return f"bcd-{cleaned[:40] or 'teklif'}.pdf"


def build_proposal_pdf(project_name: str, sections: dict) -> bytes:
    document = _Proposal(project_name=project_name.strip() or "Genel değerlendirme")
    document.add_page()
    document.write_cover()
    for key, title in SECTIONS:
        document.write_section(title, str(sections.get(key) or ""))
    document.write_finance_table()
    return bytes(document.output())


class _Proposal(FPDF):
    def __init__(self, project_name: str) -> None:
        super().__init__(format="A4", unit="mm")
        self.project_name = project_name
        self.issued_on = datetime.now().strftime("%d.%m.%Y")
        self.add_font("DejaVu", "", str(FONT_DIR / "DejaVuSans.ttf"))
        self.add_font("DejaVu", "B", str(FONT_DIR / "DejaVuSans-Bold.ttf"))
        self.set_margins(16, 30, 16)
        self.set_auto_page_break(auto=True, margin=18)
        self.set_title(f"{COMPANY} — {project_name}")
        self.set_author(COMPANY)

    def header(self) -> None:
        self.set_fill_color(18, 18, 20)
        self.rect(0, 0, 210, 22, "F")
        self.set_xy(16, 5)
        self.set_font("DejaVu", "B", 12)
        self.set_text_color(232, 201, 154)
        self.cell(110, 6, COMPANY, new_x="RIGHT", new_y="TOP")
        self.set_font("DejaVu", "", 9)
        self.set_text_color(228, 228, 231)
        self.cell(0, 6, self.issued_on, align="R", new_x="LMARGIN", new_y="NEXT")
        self.set_x(16)
        self.set_font("DejaVu", "", 8)
        self.set_text_color(180, 180, 186)
        self.cell(0, 5, "Kurumsal teklif ve yönetici raporu", new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(24, 24, 27)
        self.set_y(30)

    def footer(self) -> None:
        self.set_y(-14)
        self.set_draw_color(212, 168, 96)
        self.set_line_width(0.3)
        self.line(16, self.get_y(), 194, self.get_y())
        self.set_y(-12)
        self.set_font("DejaVu", "", 8)
        self.set_text_color(90, 90, 96)
        self.cell(0, 6, f"{COMPANY}  ·  Sayfa {self.page_no()}", align="C")

    def write_cover(self) -> None:
        self.set_font("DejaVu", "", 9)
        self.set_text_color(140, 104, 48)
        self.cell(0, 5, "PROJE", new_x="LMARGIN", new_y="NEXT")
        self.set_font("DejaVu", "B", 16)
        self.set_text_color(24, 24, 27)
        self.multi_cell(0, 8, self.project_name, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def write_section(self, title: str, body: str) -> None:
        self.ln(2)
        self.set_font("DejaVu", "B", 13)
        self.set_text_color(24, 24, 27)
        self.multi_cell(0, 7, title, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(212, 168, 96)
        self.set_line_width(0.4)
        y = self.get_y()
        self.line(16, y, 58, y)
        self.ln(3)
        self._write_markdown(body.strip() or "Bu bölüm için kayıtlı çıktı yok.")

    def write_finance_table(self) -> None:
        ledger = load_ledger()
        totals = ledger_totals(ledger)
        self.ln(3)
        self.set_font("DejaVu", "B", 13)
        self.set_text_color(24, 24, 27)
        self.multi_cell(0, 7, "Finansal Özet", new_x="LMARGIN", new_y="NEXT")
        self.ln(1)
        rows: list[tuple[str, str, str]] = []
        for item in ledger.get("fixed_monthly") or []:
            rows.append((str(item.get("name") or "Sabit gider"), str(item.get("category") or "sabit"), tl(float(item.get("amount") or 0))))
        for item in ledger.get("project_costs") or []:
            label = f"{item.get('project') or 'Proje'} · {item.get('name') or 'Maliyet'}"
            rows.append((label, str(item.get("category") or "teknoloji"), tl(float(item.get("amount") or 0))))
        rows.append(("Sabit gider toplamı", "özet", tl(totals["fixed_total"])))
        rows.append(("Proje maliyeti", "özet", tl(totals["project_total"])))
        rows.append(("Aylık toplam", "özet", tl(totals["monthly_total"])))
        rows.append(("Hedef brüt kâr", "%35 marj", tl(totals["target_profit"])))
        self._table(("Kalem", "Tür", "Tutar"), rows)

    def _table(self, headers: tuple[str, str, str], rows: list[tuple[str, str, str]]) -> None:
        widths = (92, 42, 44)
        self.set_font("DejaVu", "B", 9)
        self.set_fill_color(24, 24, 27)
        self.set_text_color(232, 201, 154)
        for header, width in zip(headers, widths):
            self.cell(width, 8, header, fill=True)
        self.ln()
        self.set_font("DejaVu", "", 9)
        self.set_text_color(24, 24, 27)
        for index, row in enumerate(rows):
            self.set_fill_color(245, 243, 238) if index % 2 else self.set_fill_color(255, 255, 255)
            for value, width in zip(row, widths):
                self.cell(width, 7, _clip(value, 48 if width > 60 else 24), fill=True)
            self.ln()

    def _write_markdown(self, text: str) -> None:
        table: list[list[str]] = []

        def flush() -> None:
            nonlocal table
            if not table:
                return
            width = 178 / max(len(table[0]), 1)
            self.set_font("DejaVu", "", 9)
            self.set_text_color(24, 24, 27)
            for row in table:
                for cell in row:
                    self.cell(width, 6, _clip(cell, 32), border=1)
                self.ln()
            table = []

        for kind, line in _blocks(text):
            if kind == "row":
                table.append(line.split("|"))
                continue
            flush()
            if kind == "blank":
                self.ln(1.5)
                continue
            if kind == "h":
                self.set_font("DejaVu", "B", 11)
            else:
                self.set_font("DejaVu", "", 10)
            self.set_text_color(35, 35, 38)
            prefix = "• " if kind == "li" else ""
            self.multi_cell(0, 5.4, prefix + line, new_x="LMARGIN", new_y="NEXT")
        flush()


def _blocks(text: str):
    for raw in text.splitlines():
        line = _inline(raw.strip())
        if not line:
            yield "blank", ""
            continue
        if line.startswith("|") and line.endswith("|"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if cells and all(set(cell) <= set("-: ") for cell in cells):
                continue
            yield "row", "|".join(cells)
            continue
        if raw.strip().startswith("#"):
            yield "h", line
            continue
        if line.startswith(("- ", "* ")):
            yield "li", line[2:].strip()
            continue
        yield "p", line


def _inline(text: str) -> str:
    cleaned = re.sub(r"^#{1,6}\s*", "", text)
    cleaned = cleaned.replace("**", "").replace("__", "")
    cleaned = re.sub(r"`([^`]*)`", r"\1", cleaned)
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
    return cleaned.strip()


def _clip(value: str, limit: int) -> str:
    text = " ".join(str(value).split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"
