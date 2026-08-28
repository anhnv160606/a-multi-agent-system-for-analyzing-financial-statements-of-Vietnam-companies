"""LangGraph Graph Definition cho hệ thống phân tích tài chính (MVP).

Topology MVP (5 agents):
    START --> router_node --> retriever_node --> calculator_node
                                                      --> analysis_node
                                                      --> synthesis_node
                                                      --> report_node
                                                      --> evaluator_node --> END / RETRY

Khi advanced agents được implement (đồng đội code sau), chỉ cần thêm nodes và
edges vào hàm build_graph() — không cần sửa state.py hay nodes.py.

Cách sử dụng:
    from src.orchestrator.graph import build_graph, create_initial_state

    graph = build_graph(config=config, llm=llm)
    initial = create_initial_state(
        query="Phan tich ROE cua VNM 2023",
        company_ticker="VNM",
        fiscal_years=[2023],
    )
    final_state = graph.invoke(initial)
    print(final_state["analysis_results"])

Task: 5.2 (feature_list.md)
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from langgraph.graph import END, StateGraph

from src.orchestrator.edges import (
    route_by_query_type,
    route_after_retriever,
    route_after_evaluator,
)
from src.orchestrator.nodes import build_nodes
from src.orchestrator.state import FinancialAnalysisState
from src.utils.logger import get_logger

logger = get_logger("src.orchestrator.graph")


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_graph(
    config: dict[str, Any],
    llm: Any = None,
    *,
    vector_store: Any = None,
    mysql_loader: Any = None,
    checkpointer: Any = None,
) -> Any:
    """Build và compile StateGraph cho toàn bộ hệ thống Multi-Agent (Phase 5).

    Topology (MVP — 5 agents chính):
        START --> router_node
                    ├── (query_type == 'calculate')  --> calculator_node --> analysis_node --> synthesis_node --> report_node --> evaluator_node --> END / RETRY
                    ├── (query_type == 'simple')     --> retriever_node  ----------------------------------------------------> evaluator_node --> END / RETRY
                    └── (query_type == 'analysis')   --> retriever_node  --> calculator_node --> analysis_node --> synthesis_node --> report_node --> evaluator_node --> END / RETRY
    """
    # 1. Khởi tạo tất cả agent nodes
    nodes = build_nodes(
        config=config,
        llm=llm,
        vector_store=vector_store,
        mysql_loader=mysql_loader,
    )

    # 2. Tạo StateGraph với FinancialAnalysisState làm schema
    graph = StateGraph(FinancialAnalysisState)

    # 3. Đăng ký nodes vào graph
    graph.add_node("router",     nodes["router"])
    graph.add_node("retriever",  nodes["retriever"])
    graph.add_node("calculator", nodes["calculator"])
    graph.add_node("analysis",   nodes["analysis"])
    graph.add_node("synthesis",  nodes["synthesis"])
    graph.add_node("report",     nodes["report"])
    graph.add_node("evaluator",  nodes["evaluator"])

    # 4. Entry point: bắt đầu bằng router_node
    graph.set_entry_point("router")

    # 5. Dynamic Conditional Edges (Task 5.3, 5.4, 5.5, 5.7)
    graph.add_conditional_edges(
        "router",
        route_by_query_type,
        {
            "calculator": "calculator",
            "retriever":  "retriever",
        },
    )

    graph.add_conditional_edges(
        "retriever",
        route_after_retriever,
        {
            "calculator": "calculator",
            END:          "evaluator",
        },
    )

    graph.add_edge("calculator", "analysis")
    graph.add_edge("analysis",   "synthesis")
    graph.add_edge("synthesis",  "report")
    graph.add_edge("report",     "evaluator")

    graph.add_conditional_edges(
        "evaluator",
        route_after_evaluator,
        {
            "router": "router",
            END:      END,
        },
    )

    # 6. Compile
    compiled = graph.compile(checkpointer=checkpointer)

    logger.info(
        "build_graph: graph compiled successfully with dynamic conditional edges",
        extra={
            "event": "graph_compiled",
            "nodes": ["router", "retriever", "calculator", "analysis",
                      "synthesis", "report", "evaluator"],
        },
    )
    return compiled


# ---------------------------------------------------------------------------
# Initial state helper
# ---------------------------------------------------------------------------

def create_initial_state(
    query: str,
    company_ticker: str = "",
    fiscal_years: list[int] | None = None,
    *,
    query_type: Literal["simple", "calculate", "analysis", "valuation"] | None = None,
    run_id: str | None = None,
    max_retries: int = 2,
    peer_data: list[dict[str, Any]] | None = None,
) -> FinancialAnalysisState:
    """Tạo initial state với các giá trị mặc định hợp lý.

    Args:
        query:          Câu hỏi phân tích của user.
        company_ticker: Mã chứng khoán (nếu để trống, RouterAgent sẽ tự trích xuất).
        fiscal_years:   Danh sách năm tài chính (nếu để trống, RouterAgent sẽ tự trích xuất).
        query_type:     Nếu None → để router_node tự phân loại.
                        Nếu cung cấp → bypass router.
        run_id:         UUID tùy chỉnh. Nếu None → tự sinh UUID.
        max_retries:    Số retry tối đa (default: 2).
        peer_data:      Dữ liệu công ty cùng ngành cho peer comparison (tuỳ chọn).

    Returns:
        FinancialAnalysisState với required fields đã được điền.
    """
    ticker = company_ticker.strip().upper() if company_ticker else ""
    years = sorted(set(fiscal_years)) if fiscal_years else []
    generated_run_id = run_id or str(uuid.uuid4())

    state = FinancialAnalysisState(
        query=query.strip(),
        company_ticker=ticker,
        fiscal_years=years,
        run_id=generated_run_id,
        retry_count=0,
        max_retries=max_retries,
        provenance=[],
        errors=[],
    )

    # Optional fields — chỉ thêm nếu được cung cấp
    if query_type is not None:
        state["query_type"] = query_type  # type: ignore[typeddict-unknown-key]

    if peer_data is not None:
        state["peer_data"] = peer_data  # type: ignore[typeddict-unknown-key]

    logger.info(
        "create_initial_state: state created",
        extra={
            "event": "initial_state_created",
            "run_id": generated_run_id,
            "ticker": ticker,
            "fiscal_years": fiscal_years,
            "query_type": query_type or "to_be_classified_by_router",
        },
    )
    return state
