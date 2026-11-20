import json

import pytest


@pytest.fixture(autouse=True)
def offline_llm(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEYS", "")
    monkeypatch.setenv("ADMIN_USERNAME", "")
    monkeypatch.setenv("ADMIN_PASSWORD", "")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("GITHUB_TOKEN", "")
    projects = tmp_path / "projeler"
    projects.mkdir()
    ledger = tmp_path / "giderler.json"
    ledger.write_text(
        json.dumps(
            {
                "company": "BCD TECHNOLOGIES",
                "currency": "TRY",
                "fixed_monthly": [
                    {"id": "ofis", "name": "Ofis ve altyapı", "category": "sabit", "amount": 45000}
                ],
                "project_costs": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("tools.github_tools.PROJECTS_DIR", projects)
    monkeypatch.setattr("tools.finance_tools.LEDGER_PATH", ledger)
    monkeypatch.setattr("tools.crm.CRM_PATH", tmp_path / "crm.json")
    monkeypatch.setattr("agents.context.CONFIG_PATH", tmp_path / "ajan_ayarlari.json")
    monkeypatch.setattr("agents.context.MEMORY_PATH", tmp_path / "hafiza.json")
    knowledge = tmp_path / "bilgi_bankasi"
    knowledge.mkdir()
    monkeypatch.setattr("tools.knowledge.INDEX_PATH", knowledge / "index.json")
    from memory.session import reset_orchestrator

    reset_orchestrator()
    yield
    reset_orchestrator()
