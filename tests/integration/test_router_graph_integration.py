"""Integration tests for LangGraph Dynamic Conditional Edges (Phase 5)."""

import pytest
from src.orchestrator.graph import build_graph, create_initial_state


def test_graph_simple_query_path():
    """Simple query should route: Router -> Retriever -> Evaluator -> END."""
    graph = build_graph(config={}, llm=None)
    state = create_initial_state(
        query="Chiến lược công nghệ và AI của FPT",
        company_ticker="FPT",
        fiscal_years=[2023],
    )
    final_state = graph.invoke(state)

    assert final_state["query_type"] == "simple"
    assert final_state["confidence_score"] is not None
    # Provenance contains RouterAgent
    agents_run = [p.get("agent") for p in final_state.get("provenance", [])]
    assert "RouterAgent" in agents_run


def test_graph_calculate_query_path():
    """Calculate query should route: Router -> Calculator -> Analysis -> Evaluator -> END."""
    graph = build_graph(config={}, llm=None)
    state = create_initial_state(
        query="Tính doanh thu và lợi nhuận FPT năm 2023",
        company_ticker="FPT",
        fiscal_years=[2023],
    )
    final_state = graph.invoke(state)

    assert final_state["query_type"] == "calculate"
    assert "calculator_results" in final_state
    assert final_state["calculator_results"] is not None


def test_graph_analysis_query_path():
    """Analysis query should route: Router -> Retriever -> Calculator -> Analysis -> Evaluator -> END."""
    graph = build_graph(config={}, llm=None)
    state = create_initial_state(
        query="Phân tích DuPont toàn diện cho FPT năm 2023",
        company_ticker="FPT",
        fiscal_years=[2023],
    )
    final_state = graph.invoke(state)

    assert final_state["query_type"] == "analysis"
    assert "analysis_results" in final_state
    assert "dupont" in final_state["analysis_results"]
