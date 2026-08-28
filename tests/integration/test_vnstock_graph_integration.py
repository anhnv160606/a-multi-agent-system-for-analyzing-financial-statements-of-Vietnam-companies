"""Integration test for VNStock live data in LangGraph Pipeline."""

import pytest
from src.orchestrator.graph import build_graph, create_initial_state


def test_graph_with_vnstock_market_query():
    """Asking about stock price should trigger VNStockClient inside Retriever."""
    graph = build_graph(config={}, llm=None)
    state = create_initial_state(
        query="Giá cổ phiếu FPT và khối lượng giao dịch gần nhất là bao nhiêu?",
        company_ticker="FPT",
    )
    final_state = graph.invoke(state)

    assert "market_data" in final_state
    assert "market_ratios" in final_state
    assert final_state["market_data"] is not None

    # Check provenance
    agents_run = [p.get("agent") for p in final_state.get("provenance", [])]
    assert "VNStockClient" in agents_run


def test_graph_with_vpb_market_query():
    """Asking about VPB stock price should fetch VPB live data from VNStock."""
    graph = build_graph(config={}, llm=None)
    state = create_initial_state(
        query="Giá cổ phiếu VPB trên sàn chứng khoán hôm nay",
        company_ticker="VPB",
    )
    final_state = graph.invoke(state)

    assert "market_data" in final_state
    assert final_state["company_ticker"] == "VPB"
    agents_run = [p.get("agent") for p in final_state.get("provenance", [])]
    assert "VNStockClient" in agents_run
