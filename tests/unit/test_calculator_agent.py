"""Unit tests for src.agents.calculator.agent."""

import pytest
from src.agents.calculator.agent import CalculatorAgent


def test_calculator_agent_compute_direct():
    agent = CalculatorAgent(llm=None)
    records = [
        {"line_item": "Doanh số thuần", "value": 52618000000.0},
        {"line_item": "Lãi gộp", "value": 19800000000.0},
        {"line_item": "Lãi/(lỗ) ròng sau thuế", "value": 7788000000.0},
        {"line_item": "TỔNG TÀI SẢN", "value": 60000000000.0},
        {"line_item": "VỐN CHỦ SỞ HỮU", "value": 29000000000.0},
    ]

    res = agent.compute(
        query="Tính ROE, ROA và biên lợi nhuận của FPT",
        ticker="FPT",
        data=records,
    )

    assert res["success"] is True
    metrics = res["metrics"]
    assert metrics["roe"] == pytest.approx(7788000000.0 / 29000000000.0, rel=1e-3)
    assert metrics["roa"] == pytest.approx(7788000000.0 / 60000000000.0, rel=1e-3)
    assert metrics["net_margin"] == pytest.approx(7788000000.0 / 52618000000.0, rel=1e-3)
    assert metrics["gross_margin"] == pytest.approx(19800000000.0 / 52618000000.0, rel=1e-3)
    assert res["validation"]["is_valid"] is True


def test_calculator_agent_invoke_end_to_end():
    agent = CalculatorAgent(llm=None)
    state = {
        "query": "Tính toán chỉ số tài chính FPT năm 2023",
        "company_ticker": "FPT",
        "fiscal_years": [2023],
    }

    new_state = agent.invoke(state)

    assert "calculator_results" in new_state
    assert new_state["calculator_results"] != {}
    assert "revenue" in new_state["calculator_results"]
    assert new_state["confidence_score"] >= 0.9
    assert len(new_state["provenance"]) > 0
    assert new_state["provenance"][-1]["agent"] == "CalculatorAgent"
