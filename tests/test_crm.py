"""Satış hunisi ve kazanılan teklifin gelir satırına bağlanması."""

from fastapi.testclient import TestClient

from api.app import create_app
from memory.session import Orchestrator


def _client() -> TestClient:
    return TestClient(create_app(Orchestrator()))


def test_crm_crud_and_pipeline_total():
    with _client() as client:
        empty = client.get("/api/crm")
        created = client.post(
            "/api/crm",
            json={
                "musteri_adi": "Ankara Büyükşehir",
                "proje_basligi": "bariscandasci/ankaras",
                "teklif_tutari": 120000,
                "durum": "Taslak",
                "notlar": "PDF teklif",
            },
        )
        sent = client.patch(
            f"/api/crm/{created.json()['id']}",
            json={"durum": "Gönderildi", "teklif_tutari": 150000},
        )
        listing = client.get("/api/crm")
        blank = client.post("/api/crm", json={"musteri_adi": " "})
        unknown = client.patch("/api/crm/crm-999", json={"durum": "Taslak"})
        invalid = client.patch(f"/api/crm/{created.json()['id']}", json={"durum": "Askıda"})
        removed = client.delete(f"/api/crm/{created.json()['id']}")
        missing = client.delete("/api/crm/crm-999")

    assert empty.status_code == 200
    assert empty.json()["opportunities"] == []
    assert empty.json()["pipeline_total"] == 0
    assert created.status_code == 200
    assert created.json()["durum"] == "Taslak"
    assert created.json()["para_birimi"] == "TRY"
    assert sent.status_code == 200
    assert sent.json()["durum"] == "Gönderildi"
    assert sent.json()["teklif_tutari"] == 150000
    assert listing.json()["pipeline_total"] == 150000
    assert blank.status_code == 422
    assert unknown.status_code == 404
    assert invalid.status_code == 422
    assert removed.status_code == 200
    assert removed.json()["opportunities"] == []
    assert missing.status_code == 404


def test_won_deal_posts_income_once_and_leaves_when_reopened():
    with _client() as client:
        created = client.post(
            "/api/crm",
            json={"musteri_adi": "Kuzey Belediye", "proje_basligi": "ankaras", "teklif_tutari": 80000},
        )
        deal_id = created.json()["id"]
        won = client.patch(f"/api/crm/{deal_id}", json={"durum": "Kazanıldı"})
        again = client.patch(f"/api/crm/{deal_id}", json={"durum": "Kazanıldı", "teklif_tutari": 90000})
        ledger = client.get("/api/expenses")
        lost = client.patch(f"/api/crm/{deal_id}", json={"durum": "Kaybedildi"})
        cleared = client.get("/api/expenses")
        reopened = client.patch(f"/api/crm/{deal_id}", json={"durum": "Kazanıldı"})
        client.delete(f"/api/crm/{deal_id}")
        deleted = client.get("/api/expenses")

    assert won.status_code == 200
    body = ledger.json()
    assert body["realized_income"] == 90000
    assert body["fixed_total"] == 45000
    assert len(body["income"]) == 1
    assert body["income"][0]["id"] == deal_id
    assert body["income"][0]["amount"] == 90000
    assert again.json()["teklif_tutari"] == 90000
    assert lost.status_code == 200
    assert cleared.json()["realized_income"] == 0
    assert cleared.json()["income"] == []
    assert reopened.status_code == 200
    assert deleted.json()["realized_income"] == 0
    assert deleted.json()["income"] == []
    assert deleted.json()["monthly_total"] == 45000
