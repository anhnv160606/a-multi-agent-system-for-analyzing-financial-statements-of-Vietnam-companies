"""LangGraph Graph Definition cho hệ thống phân tích tài chính (MVP).

Topology MVP (3 agents):
    START --> router_node --> retriever_node --> calculator_node --> analysis_node --> END

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

from src.orchestrator.nodes import build_nodes
from src.orchestrator.state import FinancialAnalysisState
from src.utils.logger import get_logger

logger = get_logger("src.orchestrator.graph")


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_graph(
    config: dict[str, Any],
    llm: Any,
    *,
    vector_store: Any = None,
    mysql_loader: Any = None,
    checkpointer: Any = None,
) -> Any:
    """Xây dựng và compile LangGraph graph cho MVP (router + 3 agents).

    Args:
        config:       Dict cấu hình tổng. Các sub-keys được forward xuống từng agent:
                          config["retriever"]  → RetrieverAgent
                          config["calculator"] → CalculatorAgent
                          config["analysis"]   → AnalysisAgent
        llm:          LLM instance dùng chung cho tất cả agents.
                      Truyền None để chạy offline/test mode (agents dùng fallback heuristic).
        vector_store: VectorStore instance cho RetrieverAgent (tuỳ chọn).
                      Nếu None, RetrieverAgent sẽ tự khởi tạo.
        mysql_loader: MySQLLoader instance cho RetrieverAgent (tuỳ chọn).
                      Nếu None, RetrieverAgent sẽ tự khởi tạo.
        checkpointer: LangGraph checkpointer cho persistence (tuỳ chọn).
                      None = không persist state giữa các lần chạy (đủ cho MVP).
                      Ví dụ để bật: from langgraph.checkpoint.memory import MemorySaver
                                    checkpointer=MemorySaver()

    Returns:
        CompiledGraph — sẵn sàng gọi bằng graph.invoke(initial_state) hoặc
        graph.stream(initial_state) để streaming từng bước.
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

    # 4. Entry point: bắt đầu bằng router_node
    graph.set_entry_point("router")

    # 5. Edges — tuyến tính trong MVP
    #    Khi đồng đội implement router.py, có thể thêm conditional_edges ở đây:
    #
    #    graph.add_conditional_edges(
    #        "router",
    #        route_by_query_type,   # function trả về node name tiếp theo
    #        {
    #            "simple":    "retriever_only",   # path ngắn
    #            "analysis":  "retriever",         # path đầy đủ
    #        }
    #    )
    graph.add_edge("router",     "retriever")
    graph.add_edge("retriever",  "calculator")
    graph.add_edge("calculator", "analysis")
    graph.add_edge("analysis",   END)

    # 6. Compile
    compiled = graph.compile(checkpointer=checkpointer)

    logger.info(
        "build_graph: graph compiled successfully",
        extra={
            "event": "graph_compiled",
            "nodes": ["router", "retriever", "calculator", "analysis"],
            "checkpointer": type(checkpointer).__name__ if checkpointer else "None",
        },
    )
    return compiled


# ---------------------------------------------------------------------------
# Initial state helper
# ---------------------------------------------------------------------------

def create_initial_state(
    query: str,
    company_ticker: str,
    fiscal_years: list[int],
    *,
    query_type: Literal["simple", "calculate", "analysis", "valuation"] | None = None,
    run_id: str | None = None,
    max_retries: int = 2,
    peer_data: list[dict[str, Any]] | None = None,
) -> FinancialAnalysisState:
    """Tạo initial state với các giá trị mặc định hợp lý.

    Caller chỉ cần cung cấp 3 tham số bắt buộc; các field khác sẽ được
    điền bởi các agent trong quá trình graph chạy.

    Args:
        query:          Câu hỏi phân tích của user.
        company_ticker: Mã chứng khoán (sẽ được upper-case tự động).
        fiscal_years:   Danh sách năm tài chính cần phân tích.
        query_type:     Nếu None → để router_node tự phân loại.
                        Nếu cung cấp → bypass router.
        run_id:         UUID tùy chỉnh. Nếu None → tự sinh UUID.
        max_retries:    Số retry tối đa (default: 2).
        peer_data:      Dữ liệu công ty cùng ngành cho peer comparison (tuỳ chọn).

    Returns:
        FinancialAnalysisState với required fields đã được điền.
    """
    ticker = company_ticker.strip().upper()
    generated_run_id = run_id or str(uuid.uuid4())

    state = FinancialAnalysisState(
        query=query.strip(),
        company_ticker=ticker,
        fiscal_years=sorted(set(fiscal_years)),  # dedup và sort
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
