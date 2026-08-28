"""Unit tests for RouterAgent (Task 5.3)."""

import pytest
from src.orchestrator.router import RouterAgent


@pytest.fixture
def router():
    return RouterAgent(config={}, llm=None)


def test_router_classify_simple(router):
    res = router.classify("Chiến lược phát triển AI và AI Factory của FPT")
    assert res["query_type"] == "simple"
    assert res["ticker"] == "FPT"
    assert res["confidence"] >= 0.8


def test_router_classify_calculate(router):
    res = router.classify("Tính doanh thu và lợi nhuận sau thuế của VNM năm 2023")
    assert res["query_type"] == "calculate"
    assert res["ticker"] == "VNM"
    assert 2023 in res["fiscal_years"]


def test_router_classify_analysis(router):
    res = router.classify("Phân tích bóc tách mô hình DuPont của FPT năm 2022 và 2023")
    assert res["query_type"] == "analysis"
    assert res["ticker"] == "FPT"
    assert 2022 in res["fiscal_years"]
    assert 2023 in res["fiscal_years"]


def test_router_classify_valuation(router):
    res = router.classify("Định giá cổ phiếu HPG theo phương pháp P/E và DCF")
    assert res["query_type"] == "valuation"
    assert res["ticker"] == "HPG"


def test_router_invoke_state(router):
    state = {
        "query": "Tính tỷ suất lợi nhuận gộp của FPT năm 2023",
        "company_ticker": "",
        "fiscal_years": [],
        "run_id": "test_run_123",
    }
    updated_state = router.invoke(state)
    assert updated_state["query_type"] == "calculate"
    assert updated_state["company_ticker"] == "FPT"
    assert 2023 in updated_state["fiscal_years"]
    assert "provenance" in updated_state
