"""Ajan katalogu. API ve yönetici yanıtı aynı metinleri kullanır."""

from __future__ import annotations

AGENTS: list[dict[str, str]] = [
    {
        "id": "supervisor",
        "name": "Yönetici",
        "description": "GitHub deposunu okur; pazar, Ar-Ge ve finans ajanlarını tek raporda birleştirir.",
    },
    {
        "id": "market",
        "name": "Operasyon & Pazar Geliştirme",
        "description": "Depoyu sektör, müşteri profili, değer önerisi ve satış stratejisi olarak okur.",
    },
    {
        "id": "finance",
        "name": "Muhasebe & Finans",
        "description": "Sabit giderleri, proje maliyetini, fiyat önerisini ve net kârı hesaplar.",
    },
    {
        "id": "rnd",
        "name": "Teknik & Ar-Ge",
        "description": "Kod yapısını inceler; ayırıcı özellik, kütüphane ve Ar-Ge yol haritası çıkarır.",
    },
]
