"""İK mock araçları. Veri tamamen uydurma örnek kayıtlardır."""

from __future__ import annotations

from langchain_core.tools import tool

from tools.common import COMPANY, detect_department, fold, mentions_record

EMPLOYEES: list[dict[str, object]] = [
    {
        "id": "E-1001",
        "name": "Ayşe Demir",
        "department": "İK",
        "title": "İnsan Kaynakları Uzmanı",
        "location": "İstanbul",
        "start": "2022-03-14",
        "status": "aktif",
        "leave_days": 8,
    },
    {
        "id": "E-1002",
        "name": "Mehmet Kaya",
        "department": "Finans",
        "title": "Muhasebe Müdürü",
        "location": "İstanbul",
        "start": "2019-11-04",
        "status": "aktif",
        "leave_days": 4,
    },
    {
        "id": "E-1003",
        "name": "Zeynep Arslan",
        "department": "Operasyon",
        "title": "Sistem Yöneticisi",
        "location": "Ankara",
        "start": "2021-06-01",
        "status": "aktif",
        "leave_days": 12,
    },
    {
        "id": "E-1004",
        "name": "Can Öztürk",
        "department": "Yazılım",
        "title": "Kıdemli Geliştirici",
        "location": "İzmir",
        "start": "2020-01-20",
        "status": "aktif",
        "leave_days": 6,
    },
    {
        "id": "E-1005",
        "name": "Elif Şahin",
        "department": "Satış",
        "title": "Satış Temsilcisi",
        "location": "İstanbul",
        "start": "2023-04-17",
        "status": "aktif",
        "leave_days": 10,
    },
    {
        "id": "E-1006",
        "name": "Burak Yılmaz",
        "department": "Yazılım",
        "title": "Geliştirici",
        "location": "Ankara",
        "start": "2024-02-12",
        "status": "aktif",
        "leave_days": 3,
    },
    {
        "id": "E-1007",
        "name": "Selin Acar",
        "department": "Finans",
        "title": "Finans Uzmanı",
        "location": "İstanbul",
        "start": "2022-09-05",
        "status": "izinli",
        "leave_days": 9,
    },
    {
        "id": "E-1008",
        "name": "Emre Koç",
        "department": "Operasyon",
        "title": "DevOps Mühendisi",
        "location": "Ankara",
        "start": "2023-08-28",
        "status": "aktif",
        "leave_days": 5,
    },
]

CANDIDATES: list[dict[str, str]] = [
    {
        "id": "C-2001",
        "name": "Deniz Aydın",
        "role": "Backend Geliştirici",
        "department": "Yazılım",
        "stage": "mülakat",
    },
    {
        "id": "C-2002",
        "name": "Harun Çelik",
        "role": "Muhasebe Uzmanı",
        "department": "Finans",
        "stage": "ön değerlendirme",
    },
    {
        "id": "C-2003",
        "name": "Merve Aksoy",
        "role": "Sistem Uzmanı",
        "department": "Operasyon",
        "stage": "teklif",
    },
]


def _employee_line(person: dict[str, object]) -> str:
    return (
        f"- {person['id']} {person['name']} — {person['department']} — "
        f"{person['title']} — {person['status']} — kalan izin {person['leave_days']} gün"
    )


@tool
def list_employees(department: str = "") -> str:
    """Şirket personel listesini ve kadro sayısını döndürür.

    department boşsa tüm şirket gelir. Örnek değerler: İK, Finans, Operasyon, Yazılım, Satış.
    """
    requested = (department or "").strip()
    rows = EMPLOYEES
    label = "tüm şirket"
    if requested:
        target = detect_department(requested) or requested
        rows = [person for person in EMPLOYEES if fold(str(person["department"])) == fold(target)]
        label = target
        if not rows:
            known = ", ".join(dict.fromkeys(str(person["department"]) for person in EMPLOYEES))
            return f"'{requested}' için personel kaydı yok. Kayıtlı departmanlar: {known}."

    counts: dict[str, int] = {}
    for person in rows:
        key = str(person["department"])
        counts[key] = counts.get(key, 0) + 1
    summary = ", ".join(f"{name}: {count}" for name, count in counts.items())
    lines = [f"{COMPANY} personel listesi ({label})", ""]
    lines.extend(_employee_line(person) for person in rows)
    lines.append("")
    lines.append(f"Kadro: {summary}. Toplam: {len(rows)}.")
    return "\n".join(lines)


@tool
def get_employee(query: str) -> str:
    """Ad, soyad veya E-1001 biçimindeki kimlikle tek personel kaydını döndürür."""
    matches = [
        person
        for person in EMPLOYEES
        if mentions_record(query or "", name=str(person["name"]), record_id=str(person["id"]))
    ]
    if not matches:
        return "Eşleşen personel bulunamadı. Tam ad veya E-1001 biçiminde kimlik kullanın."
    blocks = []
    for person in matches:
        blocks.append(
            "\n".join(
                [
                    f"Personel kaydı — {person['name']}",
                    f"ID: {person['id']}",
                    f"Departman: {person['department']}",
                    f"Ünvan: {person['title']}",
                    f"Lokasyon: {person['location']}",
                    f"İşe giriş: {person['start']}",
                    f"Durum: {person['status']}",
                    f"Kalan izin: {person['leave_days']} gün",
                ]
            )
        )
    return "\n\n".join(blocks)


@tool
def list_candidates(status: str = "", name: str = "") -> str:
    """İşe alım adaylarını döndürür.

    status örnekleri: mülakat, teklif, ön değerlendirme. name verilirse aday adına göre süzer.
    """
    rows = CANDIDATES
    status_q = fold(status or "")
    name_q = fold(name or "")
    if status_q:
        rows = [row for row in rows if status_q in fold(row["stage"])]
    if name_q:
        rows = [row for row in rows if name_q in fold(row["name"]) or name_q in fold(row["id"])]
    if not rows:
        return "Bu süzgeçle aday bulunamadı."
    lines = [f"{COMPANY} aday listesi", ""]
    for row in rows:
        lines.append(
            f"- {row['id']} {row['name']} — {row['department']} — {row['role']} — aşama: {row['stage']}"
        )
    lines.append("")
    lines.append(f"Toplam aday: {len(rows)}.")
    return "\n".join(lines)


HR_TOOLS = [list_employees, get_employee, list_candidates]
