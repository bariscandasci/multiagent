"""Defter hesabı ve GitHub proje kaydı."""

import base64

from tools.analysis import build_market_section, build_rnd_section
from tools.finance_tools import add_expense, get_monthly_expenses, simulate_project_budget
from tools.github_tools import download_repo, format_project, parse_repo_url, read_project, save_project


def test_monthly_total_and_project_profit():
    listing = get_monthly_expenses.invoke({})
    assert "BCD TECHNOLOGIES" in listing
    assert "Ofis ve altyapı" in listing
    assert "45.000 TL" in listing

    added = add_expense.invoke(
        {"name": "Harita API", "amount": 5500, "category": "teknoloji", "project": "ankaras"}
    )
    assert "proje maliyeti" in added
    simulation = simulate_project_budget.invoke(
        {"project": "ankaras", "monthly_price": 20000, "extra_monthly_cost": 0, "note": "pilot"}
    )
    assert "5.500 TL" in simulation
    assert "14.500 TL" in simulation
    assert "8.462 TL" in simulation
    assert "%72,5" in simulation
    assert "45.000 TL" in simulation


def test_repo_url_and_saved_summary_drive_market_and_rnd():
    assert parse_repo_url("https://github.com/bariscandasci/ankaras.git") == ("bariscandasci", "ankaras")
    assert parse_repo_url("bariscandasci/ankaras") == ("bariscandasci", "ankaras")
    record = {
        "company": "BCD TECHNOLOGIES",
        "owner": "bariscandasci",
        "repo": "ankaras",
        "slug": "bariscandasci__ankaras",
        "url": "https://github.com/bariscandasci/ankaras",
        "description": "Belediye hizmet masası",
        "default_branch": "main",
        "private": False,
        "language": "Python",
        "languages": ["Python"],
        "readme": "Ankara belediye taleplerini izler.",
        "tree": ["app.py", "requirements.txt"],
        "dependencies": {"requirements.txt": "fastapi\n"},
        "fetched_at": "2026-11-17T00:00:00+00:00",
    }
    save_project(record)
    text = read_project.invoke({"query": "bariscandasci/ankaras"})
    assert "Belediye hizmet masası" in text
    assert "fastapi" in text
    market = build_market_section("bariscandasci__ankaras")
    rnd = build_rnd_section("bariscandasci__ankaras")
    assert "Kamu ve yerel yönetimler" in market
    assert "Satış stratejisi" in market
    assert "Ar-Ge yol haritası" in rnd
    assert "FastAPI" in rnd


def test_download_repo_reads_readme_tree_and_dependencies(monkeypatch):
    readme = base64.b64encode("Belediye masası\n".encode()).decode()
    requirements = base64.b64encode(b"fastapi\n").decode()

    def fake_get(url: str, required: bool = True):
        del required
        if url.endswith("/repos/bariscandasci/ankaras"):
            return {"default_branch": "main", "description": "Belediye hizmet masası", "private": False, "language": "Python"}
        if url.endswith("/readme"):
            return {"content": readme}
        if "/git/trees/" in url:
            return {"tree": [{"path": "requirements.txt", "type": "blob"}, {"path": "app.py", "type": "blob"}]}
        if "/contents/" in url:
            return {"encoding": "base64", "content": requirements}
        if url.endswith("/languages"):
            return {"Python": 12}
        raise AssertionError(url)

    monkeypatch.setattr("tools.github_tools._get_json", fake_get)
    record = download_repo("bariscandasci", "ankaras")
    assert record["slug"] == "bariscandasci__ankaras"
    assert "Belediye masası" in record["readme"]
    assert record["dependencies"]["requirements.txt"] == "fastapi"
    assert "app.py" in record["tree"]
    saved = format_project(record)
    assert "BCD TECHNOLOGIES proje kaydı" in saved
