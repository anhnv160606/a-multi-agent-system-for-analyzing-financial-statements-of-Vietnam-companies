"""LangGraph Conditional Edges & Routing Logic (Task 5.4 & Task 5.5).

Provides routing functions for LangGraph StateGraph:
    1. `route_by_query_type`     — Rẽ nhánh từ Router Node dựa trên query_type.
    2. `route_after_retriever`   — Rẽ nhánh từ Retriever Node (simple vs analysis).
    3. `route_after_evaluator`   — Quyết định retry hay kết thúc (Reflection Loop).
"""

from __future__ import annotations

from typing import Any, Literal
from langgraph.graph import END

from src.orchestrator.state import FinancialAnalysisState
from src.utils.logger import get_logger

logger = get_logger("src.orchestrator.edges")


def route_by_query_type(state: FinancialAnalysisState) -> Literal["retriever", "calculator"]:
    """Quyết định node tiếp theo sau khi Router phân loại câu hỏi.

    Nhánh:
      - "calculate": Đi thẳng tới `calculator_node` (SQL & Sandbox math).
      - "simple", "analysis", "valuation": Đi tới `retriever_node` (Semantic & Table RAG).
    """
    query_type = state.get("query_type", "analysis")

    if query_type == "calculate":
        logger.info("route_by_query_type: Routing to 'calculator' (direct quantitative path)")
        return "calculator"

    logger.info(f"route_by_query_type: Routing to 'retriever' (query_type={query_type})")
    return "retriever"


def route_after_retriever(state: FinancialAnalysisState) -> Literal["calculator", "synthesis"]:
    """Quyết định node tiếp theo sau khi Retriever tìm kiếm xong.

    Nhánh:
      - "simple": Chuyển sang `synthesis` để tổng hợp và trả lời câu hỏi trực tiếp.
      - "analysis", "valuation", "calculate": Tiếp tục chuyển sang `calculator_node`.
    """
    query_type = state.get("query_type", "analysis")

    if query_type == "simple":
        logger.info("route_after_retriever: Simple query RAG pass complete. Routing to 'synthesis'.")
        return "synthesis"

    logger.info("route_after_retriever: Routing to 'calculator' for quantitative modeling.")
    return "calculator"


def route_after_evaluator(state: FinancialAnalysisState) -> Literal["router", "__end__"]:
    """Quyết định có kích hoạt Reflection / Retry Loop hay kết thúc.

    Điều kiện Retry:
      - Confidence score < 0.5
      - retry_count < max_retries
    """
    confidence = float(state.get("confidence_score", 0.8) or 0.8)
    retry_count = int(state.get("retry_count", 0))
    max_retries = int(state.get("max_retries", 2))

    if confidence < 0.5 and retry_count < max_retries:
        logger.warning(
            f"route_after_evaluator: Low confidence ({confidence:.2f}) with retry {retry_count}/{max_retries}. "
            "Triggering reflection & retry loop."
        )
        return "router"

    logger.info(f"route_after_evaluator: Graph execution approved (confidence={confidence:.2f}). Routing to END.")
    return END
