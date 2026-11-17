"""Ajan katalogu. API ve yönetici yanıtı aynı metinleri kullanır."""

from __future__ import annotations

AGENTS: list[dict[str, str]] = [
    {
        "id": "supervisor",
        "name": "Yönetici",
        "description": "İsteği analiz eder ve doğru departman ajanına yönlendirir.",
    },
    {
        "id": "hr",
        "name": "İK & Veri",
        "description": "Personel ve aday verilerini analiz eder, kadro raporu çıkarır.",
    },
    {
        "id": "finance",
        "name": "Finans & Muhasebe",
        "description": "Gelir-gider, fatura ve bütçe özetleri üretir.",
    },
    {
        "id": "ops",
        "name": "Teknik & Operasyon",
        "description": "Sunucu durumunu kontrol eder ve teknik iş planı çıkarır.",
    },
]
