"""LangGraph State Definition cho hệ thống phân tích tài chính.

File này định nghĩa duy nhất một class: ``FinancialAnalysisState`` — "hợp đồng
dữ liệu" giữa tất cả nodes trong graph. Mọi agent đều đọc và ghi vào object này.

Quy ước thiết kế:
    - Field bắt buộc (required): phải có trong initial_state trước khi graph chạy.
    - Field tuỳ chọn (NotRequired): được agent điền vào trong quá trình chạy.
    - Field RESERVED: dành cho advanced agents (đồng đội implement sau).

Contract với các agent:
    RetrieverAgent  → ghi: retrieved_chunks, table_data, retriever_filters,
                           confidence_score, provenance, errors
    CalculatorAgent → ghi: calculator_results (dict metrics), calculator_raw,
                           confidence_score, provenance, errors
    AnalysisAgent   → ghi: analysis_results, confidence_score, provenance, errors
    RouterAgent     → ghi: query_type  (đồng đội implement trong router.py)

Task: 5.1 (feature_list.md)
"""

from __future__ import annotations

from typing import Any, Literal

from typing_extensions import NotRequired, TypedDict


class FinancialAnalysisState(TypedDict):
    """State object dùng chung cho toàn bộ LangGraph graph.

    Được truyền qua từng node theo thứ tự:
        router_node → retriever_node → calculator_node → analysis_node → END
    """

    # =========================================================================
    # INPUT — bắt buộc, do caller cung cấp qua create_initial_state()
    # =========================================================================

    query: str
    """Câu hỏi gốc của user.
    Ví dụ: "Phân tích ROE của VNM giai đoạn 2021-2023"
    """

    company_ticker: str
    """Mã chứng khoán viết hoa.
    Ví dụ: "VNM", "FPT", "HPG"
    Được dùng để filter metadata khi retrieve và làm context cho LLM.
    """

    fiscal_years: list[int]
    """Danh sách năm tài chính cần phân tích.
    Ví dụ: [2021, 2022, 2023]
    """

    # =========================================================================
    # PIPELINE CONTROL — bắt buộc
    # =========================================================================

    run_id: str
    """UUID định danh duy nhất cho lần chạy này.
    Dùng cho logging, provenance tracking và tracing (LangSmith).
    """

    retry_count: int
    """Số lần đã retry hiện tại. Bắt đầu = 0."""

    max_retries: int
    """Số retry tối đa được phép. Default: 2."""

    # =========================================================================
    # ROUTER OUTPUT — do router_node ghi (đồng đội implement router.py sau)
    # =========================================================================

    query_type: NotRequired[Literal["simple", "calculate", "analysis", "valuation"]]
    """Phân loại độ phức tạp của câu hỏi, được RouterAgent phân loại tự động.

    Ý nghĩa các tier:
        "simple"    → Chỉ cần tra cứu thông tin. Chạy RetrieverAgent rồi dừng.
        "calculate" → Cần tính toán số liệu. Chạy Retriever + Calculator.
        "analysis"  → Phân tích đầy đủ. Chạy cả 3 agents (MVP hiện tại).
        "valuation" → Định giá cổ phiếu. Reserved cho advanced agents.

    Nếu router_node chưa chạy → mặc định coi là "analysis" (chạy full pipeline).
    """

    trace_id: NotRequired[str]
    """Trace ID nếu tích hợp LangSmith hoặc hệ thống observability ngoài."""

    # =========================================================================
    # RETRIEVER OUTPUT — do RetrieverAgent.invoke() ghi
    # =========================================================================

    retrieved_chunks: NotRequired[list[dict[str, Any]]]
    """Chunks văn bản từ Vector DB sau khi hybrid search + rerank.

    Mỗi phần tử có cấu trúc:
        {
            "chunk_id":      str,
            "content":       str,
            "metadata":      dict,     # ticker, year, report_type, page, ...
            "vector_score":  float,
            "keyword_score": float,
            "hybrid_score":  float,
            "rerank_score":  float,
            "rerank_reason": str,
        }
    """

    table_data: NotRequired[list[dict[str, Any]]]
    """Dữ liệu bảng số liệu từ MySQL hoặc table chunks trong Vector DB.

    Mỗi phần tử có thể có 2 format:
        - MySQL row:    {"source": "mysql",        "row": {line_item, value, ...}}
        - Vector chunk: {"source": "vector_store", "content": str, "metadata": dict}
    """

    retriever_filters: NotRequired[dict[str, Any]]
    """Bộ filter metadata đã được áp dụng khi retrieve.
    Ví dụ: {"ticker": "VNM", "year": 2023, "report_type": "income_statement"}
    Dùng để debug và provenance.
    """

    market_data: NotRequired[dict[str, Any]]
    """Dữ liệu giá cổ phiếu và giao dịch thời gian thực từ VNStock API."""

    market_ratios: NotRequired[dict[str, Any]]
    """Chỉ số định giá thị trường P/E, P/B, EPS từ VNStock API."""

    # =========================================================================
    # CALCULATOR OUTPUT — do CalculatorAgent.invoke() ghi
    # =========================================================================

    calculator_results: NotRequired[dict[str, Any]]
    """Metrics tài chính đã tính toán từ CalculatorAgent (Program of Thought).

    Cấu trúc thực tế (theo CalculatorAgent.invoke() contract):
        {
            "revenue":        float,
            "gross_profit":   float,
            "net_income":     float,
            "total_assets":   float,
            "equity":         float,
            "total_liabilities": float,
            "roe":            float,
            "roa":            float,
            "net_margin":     float,
            "gross_margin":   float,
            "dupont":         dict,
            ...  # Các metrics khác tuỳ theo query
        }

    Lưu ý: AnalysisAgent đọc trực tiếp từ key này để lấy metrics đã tính sẵn.
    """

    calculator_raw: NotRequired[dict[str, Any]]
    """Raw output đầy đủ từ CalculatorAgent.compute(), bao gồm:
        {
            "success":          bool,
            "metrics":          dict,   # = calculator_results
            "validation":       dict,
            "execution_time_ms": float,
            "code":             str,    # Python code đã sinh (PoT)
            "error":            str,    # Nếu thất bại
        }
    Dùng cho audit, debug và provenance.
    """

    sql_data: NotRequired[list[dict[str, Any]]]
    """SQL records được SQLAgent truy vấn trong CalculatorAgent.
    Một số node có thể cần đọc raw SQL data này.
    """

    # =========================================================================
    # ANALYSIS OUTPUT — do AnalysisAgent.invoke() ghi
    # =========================================================================

    analysis_results: NotRequired[dict[str, Any]]
    """Kết quả phân tích đầy đủ từ AnalysisAgent (structured JSON).

    Cấu trúc:
        {
            "ticker":        str,
            "fiscal_years":  list[int],
            "dupont": {
                "dupont_3step": {year: {net_profit_margin, asset_turnover,
                                        equity_multiplier, roe}},
                "dupont_5step": {year: {tax_burden, interest_burden, ...}},
                "interpretation": str,
            },
            "trend": {
                "years_covered": list[int],
                "metrics":       {"yoy_growth": {...}, "margins": {...}},
                "cagr":          {"revenue": float, "net_income": float, ...},
                "trend_direction": {"gross_margin": str, ...},
                "interpretation": str,
            },
            "common_size": {
                "income_statement": {year: {metric_pct: float}},
                "balance_sheet":    {year: {metric_pct: float}},
                "interpretation": str,
            },
            "peer_comparison": {
                "has_peer_data":    bool,
                "company_metrics":  dict,
                "comparison_table": list,
                "company_position": dict,
                "interpretation": str,
            },
            "confidence":  float,
            "data_gaps":   list[str],
        }
    """

    peer_data: NotRequired[list[dict[str, Any]]]
    """Dữ liệu tài chính của công ty cùng ngành để peer comparison.
    Mỗi phần tử: {"ticker": str, "income_statement": dict, "balance_sheet": dict}
    Nếu không có → AnalysisAgent sẽ chỉ nhận xét định tính.
    """

    # =========================================================================
    # RESERVED — Advanced agents (đồng đội implement sau)
    # =========================================================================

    modeling_results: NotRequired[dict[str, Any]]
    """Output của ModelingAgent (DCF, DDM, WACC, ...). RESERVED."""

    synthesis_results: NotRequired[dict[str, Any]]
    """Output của SynthesisAgent (structured summary). RESERVED."""

    bull_thesis: NotRequired[str]
    """Luận điểm lạc quan từ BullAgent. RESERVED."""

    bear_thesis: NotRequired[str]
    """Luận điểm bi quan từ BearAgent. RESERVED."""

    judge_verdict: NotRequired[dict[str, Any]]
    """Phán quyết của JudgeAgent với rubric scoring. RESERVED."""

    final_report: NotRequired[str]
    """Báo cáo Markdown hoàn chỉnh từ ReportAgent. RESERVED."""

    # =========================================================================
    # CROSS-CUTTING CONCERNS — ghi bởi nhiều agents
    # =========================================================================

    confidence_score: NotRequired[float]
    """Điểm tin cậy [0.0, 1.0] từ agent cuối cùng đã chạy.
    Được ghi đè mỗi lần một agent mới hoàn thành.
    """

    provenance: NotRequired[list[dict[str, Any]]]
    """Danh sách provenance entries tích lũy qua pipeline.
    Mỗi entry là dict chứa: agent, step info, source chunks, confidence, ...
    Mỗi agent append vào list này thay vì ghi đè.
    """

    errors: NotRequired[list[str]]
    """Danh sách lỗi tích lũy qua pipeline.
    Agent gặp lỗi sẽ append message vào đây thay vì raise exception.
    Pipeline tiếp tục chạy dù có lỗi ở bước trước.
    """
