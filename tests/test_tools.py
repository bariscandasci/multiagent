"""Araç hesapları ve rapor metinleri."""

from tools.finance_tools import budget_summary, income_expense_summary, list_invoices
from tools.hr_tools import get_employee, list_candidates, list_employees
from tools.ops_tools import list_incidents, plan_technical_tasks, server_status


def test_quarter_profit_is_calculated_from_the_ledger():
    text = income_expense_summary.invoke({"period": "quarter"})
    assert "3.520.000 TL" in text
    assert "2.600.000 TL" in text
    assert "920.000 TL" in text
    assert "%26,1" in text


def test_month_summary_uses_only_the_latest_month():
    text = income_expense_summary.invoke({"period": "month"})
    assert "2026-11" in text
    assert "2026-09" not in text
    assert "1.090.000 TL" in text


def test_overdue_invoice_and_budget_remaining():
    invoices = list_invoices.invoke({"status": "gecikmiş"})
    assert "Bulut Host" in invoices
    assert "18.600 TL" in invoices
    budget = budget_summary.invoke({"department": "Yazılım"})
    assert "540.000 TL" in budget
    assert "%77,5" in budget


def test_employee_and_candidate_lookup():
    person = get_employee.invoke({"query": "Ayşe Demir"})
    assert "E-1001" in person
    assert "İnsan Kaynakları Uzmanı" in person
    people = list_employees.invoke({"department": "Yazılım"})
    assert "Can Öztürk" in people
    assert "Ayşe Demir" not in people
    candidates = list_candidates.invoke({"status": "mülakat"})
    assert "Deniz Aydın" in candidates
    assert "Merve Aksoy" not in candidates


def test_server_status_and_plan_call_out_the_outage():
    status = server_status.invoke({"name": ""})
    assert "worker-01" in status
    assert "kapalı" in status
    assert "1 kapalı" in status
    plan = plan_technical_tasks.invoke({"focus": "db-01"})
    assert "1. db-01" in plan
    incidents = list_incidents.invoke({"open_only": True})
    assert "INC-1844" in incidents
    assert "INC-1837" not in incidents
