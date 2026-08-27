"""Integration test for CalculatorAgent and AnalysisAgent collaboration.

Tests the full data flow:
  Database / SQLAgent -> CalculatorAgent (PoT) -> AnalysisAgent (DuPont / Trend Analysis)
"""

import pytest

from src.agents.analysis.agent import AnalysisAgent
from src.agents.calculator.agent import CalculatorAgent
from src.agents.calculator.sql_agent import SQLAgent


def test_calculator_to_analysis_pipeline_integration():
    # 1. Initialize Agents
    calculator = CalculatorAgent(llm=None)
    analysis_agent = AnalysisAgent(config={"skip_llm_insights": True}, llm=None)

    # 2. State representing user query
    state = {
        "query": "Phân tích tài chính và tính toán ROE, DuPont của FPT năm 2023",
        "company_ticker": "FPT",
        "fiscal_years": [2023],
        "fiscal_quarter": 0,
    }

    # 3. Invoke Calculator Agent
    state = calculator.invoke(state)

    assert "calculator_results" in state
    assert "revenue" in state["calculator_results"]
    assert state["confidence_score"] >= 0.8
    assert len(state["provenance"]) >= 1

    # 4. Prepare mock table_data if needed for AnalysisAgent
    state["table_data"] = {
        "income_statement": {
            "net_revenue": state["calculator_results"].get("revenue", 52618000000.0),
            "gross_profit": state["calculator_results"].get("gross_profit", 19800000000.0),
            "net_income": state["calculator_results"].get("net_income", 7788000000.0),
            "ebt": 9200000000.0,
            "ebit": 9500000000.0,
        },
        "balance_sheet": {
            "total_assets": state["calculator_results"].get("total_assets", 60000000000.0),
            "equity": state["calculator_results"].get("equity", 29000000000.0),
            "total_liabilities": state["calculator_results"].get("total_liabilities", 31000000000.0),
        },
    }

    # 5. Invoke Analysis Agent
    state = analysis_agent.invoke(state)

    assert "analysis_results" in state
    analysis = state["analysis_results"]
    assert "dupont" in analysis or "trend" in analysis or "data_gaps" in analysis
    assert len(state["provenance"]) >= 2
