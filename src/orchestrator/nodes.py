"""Node functions cho LangGraph graph — mỗi node là thin wrapper quanh một agent.

Thiết kế:
    - Node function KHÔNG chứa business logic — logic nằm trong agent.
    - Node function chỉ làm: nhận state, gọi agent.invoke(state), return state.
    - Mọi exception đều được bắt và ghi vào state["errors"] thay vì crash graph.
    - Dùng factory function build_nodes() để khởi tạo agents 1 lần khi startup.

Thứ tự node trong graph (MVP):
    router_node → retriever_node → calculator_node → analysis_node → END

Task: 5.4, 5.5 (feature_list.md)
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from src.orchestrator.state import FinancialAnalysisState
from src.utils.logger import get_logger

logger = get_logger("src.orchestrator.nodes")


# ---------------------------------------------------------------------------
# Node functions
# ---------------------------------------------------------------------------

def router_node(state: FinancialAnalysisState) -> FinancialAnalysisState:
    """Node placeholder cho RouterAgent.

    Trong MVP này, nếu query_type chưa được set (router.py chưa implement),
    mặc định coi là "analysis" để chạy full pipeline 3 agents.

    Khi đồng đội implement router.py, node này sẽ được thay thế bằng
    logic phân loại thực sự (LLM hoặc rule-based classifier).

    Đọc:  state["query"], state["query_type"] (nếu có)
    Ghi:  state["query_type"] (nếu chưa có)
    """
    if not state.get("query_type"):
        # Fallback: không có router → chạy full analysis pipeline
        state["query_type"] = "analysis"  # type: ignore[typeddict-unknown-key]
        logger.info(
            "router_node: query_type not set, defaulting to 'analysis'",
            extra={
                "event": "router_fallback",
                "run_id": state.get("run_id"),
                "query_preview": str(state.get("query", ""))[:100],
            },
        )
    else:
        logger.info(
            "router_node: query_type already set",
            extra={
                "event": "router_passthrough",
                "run_id": state.get("run_id"),
                "query_type": state.get("query_type"),
            },
        )
    return state


def retriever_node(
    state: FinancialAnalysisState,
    agent: Any,
) -> FinancialAnalysisState:
    """Node wrapping RetrieverAgent.

    Đọc:  state["query"], state["company_ticker"], state["fiscal_years"]
    Ghi:  state["retrieved_chunks"], state["table_data"],
          state["retriever_filters"], state["confidence_score"],
          state["provenance"], state["errors"]
    """
    run_id = state.get("run_id", "")
    logger.info(
        "retriever_node: start",
        extra={
            "event": "node_start",
            "node": "retriever",
            "run_id": run_id,
            "ticker": state.get("company_ticker"),
        },
    )
    try:
        state = agent.invoke(state)
        logger.info(
            "retriever_node: done",
            extra={
                "event": "node_done",
                "node": "retriever",
                "run_id": run_id,
                "chunks_retrieved": len(state.get("retrieved_chunks") or []),
                "table_records": len(state.get("table_data") or []),
            },
        )
    except Exception as exc:
        _append_node_error(state, node_name="retriever_node", exc=exc)
    return state


def calculator_node(
    state: FinancialAnalysisState,
    agent: Any,
) -> FinancialAnalysisState:
    """Node wrapping CalculatorAgent.

    Guard: Nếu cả retrieved_chunks và table_data đều rỗng sau retriever
    → skip calculator để tránh sinh code sai trên dữ liệu trống.

    Đọc:  state["retrieved_chunks"], state["table_data"], state["query"],
          state["company_ticker"], state["fiscal_years"]
    Ghi:  state["calculator_results"], state["calculator_raw"],
          state["confidence_score"], state["provenance"], state["errors"]
    """
    run_id = state.get("run_id", "")

    # Guard: skip nếu không có dữ liệu đầu vào
    has_chunks = bool(state.get("retrieved_chunks"))
    has_tables = bool(state.get("table_data"))
    if not has_chunks and not has_tables:
        logger.warning(
            "calculator_node: skipped — no retrieved_chunks or table_data",
            extra={"event": "node_skipped", "node": "calculator", "run_id": run_id},
        )
        _append_state_error(
            state,
            "calculator_node: skipped — RetrieverAgent returned no data. "
            "Calculator cannot run without input data.",
        )
        return state

    logger.info(
        "calculator_node: start",
        extra={
            "event": "node_start",
            "node": "calculator",
            "run_id": run_id,
            "ticker": state.get("company_ticker"),
        },
    )
    try:
        state = agent.invoke(state)
        calc_ok = (
            isinstance(state.get("calculator_results"), dict)
            and bool(state.get("calculator_results"))
        )
        logger.info(
            "calculator_node: done",
            extra={
                "event": "node_done",
                "node": "calculator",
                "run_id": run_id,
                "success": calc_ok,
                "metrics_count": len(state.get("calculator_results") or {}),
            },
        )
    except Exception as exc:
        _append_node_error(state, node_name="calculator_node", exc=exc)
    return state


def analysis_node(
    state: FinancialAnalysisState,
    agent: Any,
) -> FinancialAnalysisState:
    """Node wrapping AnalysisAgent.

    Guard: Nếu cả retrieved_chunks, table_data và calculator_results đều rỗng
    → skip để tránh gọi LLM với context trống.

    Đọc:  state["retrieved_chunks"], state["table_data"],
          state["calculator_results"], state["query"],
          state["company_ticker"], state["fiscal_years"]
    Ghi:  state["analysis_results"], state["confidence_score"],
          state["provenance"], state["errors"]
    """
    run_id = state.get("run_id", "")

    # Guard: cần ít nhất 1 trong 3 nguồn dữ liệu
    has_chunks = bool(state.get("retrieved_chunks"))
    has_tables = bool(state.get("table_data"))
    has_calc = bool(state.get("calculator_results"))

    if not has_chunks and not has_tables and not has_calc:
        logger.warning(
            "analysis_node: skipped — no data sources available",
            extra={"event": "node_skipped", "node": "analysis", "run_id": run_id},
        )
        _append_state_error(
            state,
            "analysis_node: skipped — no retrieved_chunks, table_data, "
            "or calculator_results available. Analysis cannot run.",
        )
        return state

    logger.info(
        "analysis_node: start",
        extra={
            "event": "node_start",
            "node": "analysis",
            "run_id": run_id,
            "ticker": state.get("company_ticker"),
            "has_chunks": has_chunks,
            "has_tables": has_tables,
            "has_calc": has_calc,
        },
    )
    try:
        state = agent.invoke(state)
        analysis_ok = isinstance(state.get("analysis_results"), dict)
        logger.info(
            "analysis_node: done",
            extra={
                "event": "node_done",
                "node": "analysis",
                "run_id": run_id,
                "success": analysis_ok,
                "confidence": state.get("confidence_score"),
                "data_gaps": len(
                    (state.get("analysis_results") or {}).get("data_gaps", [])
                ),
            },
        )
    except Exception as exc:
        _append_node_error(state, node_name="analysis_node", exc=exc)
    return state


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------

def build_nodes(
    config: dict[str, Any],
    llm: Any,
    *,
    vector_store: Any = None,
    mysql_loader: Any = None,
) -> dict[str, Callable[[FinancialAnalysisState], FinancialAnalysisState]]:
    """Khởi tạo tất cả agents và trả về dict mapping node_name → callable.

    Graph.py gọi hàm này **1 lần khi startup** để tránh khởi tạo lại agents
    mỗi lần graph được invoke.

    Args:
        config:       Dict cấu hình, có thể có sub-keys "retriever", "calculator",
                      "analysis" để truyền config riêng cho từng agent.
        llm:          LLM instance được chia sẻ giữa các agents.
                      Truyền None để chạy offline/test mode.
        vector_store: VectorStore instance cho RetrieverAgent (tuỳ chọn).
        mysql_loader: MySQLLoader instance cho RetrieverAgent (tuỳ chọn).

    Returns:
        Dict với keys: "router", "retriever", "calculator", "analysis"
        Mỗi value là callable nhận FinancialAnalysisState và trả về FinancialAnalysisState.
    """
    # Import lazy để tránh circular import và cho phép test dễ hơn
    from src.agents.retriever.agent import RetrieverAgent
    from src.agents.calculator.agent import CalculatorAgent
    from src.agents.analysis.agent import AnalysisAgent

    retriever_cfg = config.get("retriever") or {}
    calculator_cfg = config.get("calculator") or {}
    analysis_cfg = config.get("analysis") or {}

    retriever_agent = RetrieverAgent(
        config=retriever_cfg,
        llm=llm,
        vector_store=vector_store,
        mysql_loader=mysql_loader,
    )
    calculator_agent = CalculatorAgent(
        config=calculator_cfg,
        llm=llm,
    )
    analysis_agent = AnalysisAgent(
        config=analysis_cfg,
        llm=llm,
    )

    logger.info(
        "build_nodes: agents initialized",
        extra={
            "event": "nodes_built",
            "agents": ["RetrieverAgent", "CalculatorAgent", "AnalysisAgent"],
            "llm_available": llm is not None,
        },
    )

    return {
        # router_node không cần agent — dùng placeholder logic
        "router": router_node,
        # Các node khác bind agent qua closure
        "retriever": lambda state: retriever_node(state, retriever_agent),
        "calculator": lambda state: calculator_node(state, calculator_agent),
        "analysis": lambda state: analysis_node(state, analysis_agent),
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _append_node_error(
    state: FinancialAnalysisState,
    node_name: str,
    exc: Exception,
) -> None:
    """Ghi lỗi unexpected exception từ node vào state và log ở mức ERROR."""
    message = f"[{node_name}] Unexpected error: {type(exc).__name__}: {exc}"
    _append_state_error(state, message)
    logger.error(
        message,
        exc_info=True,
        extra={"event": "node_error", "node": node_name, "run_id": state.get("run_id")},
    )


def _append_state_error(state: FinancialAnalysisState, message: str) -> None:
    """Append error message vào state["errors"] một cách an toàn."""
    state.setdefault("errors", [])  # type: ignore[typeddict-item]
    errors = state.get("errors")
    if isinstance(errors, list):
        errors.append(message)
