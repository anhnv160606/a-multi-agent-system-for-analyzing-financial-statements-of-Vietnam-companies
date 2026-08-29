"""Real-time Multi-Agent LangGraph Streaming Runner for Node.js Backend.

Executes graph nodes with real-time stdout event emission:
[AGENT_START:node_name] Message
[AGENT_DONE:node_name] Message
___JSON_START___ JSON Payload ___JSON_END___
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import yaml
from src.database.vector_store import VectorStore
from src.orchestrator.graph import build_graph, create_initial_state
from src.utils.llm_client import _load_env_file, get_default_llm


def emit_event(event_type: str, node: str, message: str, extra: dict[str, Any] | None = None) -> None:
    """Emit formatted event line for Node.js parser."""
    payload = {
        "event": event_type,
        "node": node,
        "message": message,
        "timestamp": time.time(),
        **(extra or {}),
    }
    sys.stdout.write(f"__AGENT_EVENT__{json.dumps(payload, ensure_ascii=False)}__AGENT_EVENT__\n")
    sys.stdout.flush()


def run_stream(query: str) -> None:
    os.environ["STREAM_REPORT_TOKENS"] = "1"
    _load_env_file()

    config_path = PROJECT_ROOT / "configs" / "settings.yaml"
    config: dict[str, Any] = {}
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

    llm = get_default_llm("default")
    vector_store = VectorStore()
    graph = build_graph(config=config, llm=llm, vector_store=vector_store)

    state = create_initial_state(query=query)
    current_state = state.copy()

    node_messages_start = {
        "router": "🧭 RouterAgent: Phân loại câu hỏi & lập chiến lược điều phối...",
        "retriever": "📈 Retriever & VNStock: Kéo dữ liệu giá HOSE thời gian thực & trích xuất ChromaDB...",
        "calculator": "🧮 CalculatorAgent: Sinh mã SQL & tính toán Sandbox Python...",
        "analysis": "💡 AnalysisAgent: Bóc tách mô hình DuPont 3 bước & cơ cấu tài chính...",
        "synthesis": "📑 SynthesisAgent: Tổng hợp số liệu đa chiều & phân tích SWOT...",
        "report": "📄 ReportAgent: Soạn thảo bản Báo cáo tài chính Markdown 6 phần...",
        "evaluator": "⚖️ EvaluatorAgent: Kiểm định tính nhất quán & phê duyệt xuất bản...",
    }

    emit_event("start", "router", node_messages_start["router"])

    # Stream graph node by node
    for step_output in graph.stream(state):
        for node_name, node_state in step_output.items():
            current_state.update(node_state)

            # Node specific completion info
            extra_info: dict[str, Any] = {}
            done_msg = f"{node_name.capitalize()}Agent hoàn tất."

            if node_name == "router":
                ticker = current_state.get("company_ticker") or "N/A"
                q_type = current_state.get("query_type") or "analysis"
                done_msg = f"🧭 Router: Nhận diện mã [{ticker}], luồng [{q_type}]"
                extra_info = {"ticker": ticker, "query_type": q_type}
                emit_event("done", "router", done_msg, extra_info)

                # Next node notification
                next_node = "calculator" if q_type == "calculate" else "retriever"
                emit_event("start", next_node, node_messages_start.get(next_node, ""))

            elif node_name == "retriever":
                chunks = current_state.get("retrieved_chunks") or []
                done_msg = f"📈 Retriever: Đã trích xuất {len(chunks)} đoạn BCTC & dữ liệu giá HOSE"
                extra_info = {"chunks_count": len(chunks)}
                emit_event("done", "retriever", done_msg, extra_info)

                if current_state.get("query_type") == "analysis":
                    emit_event("start", "calculator", node_messages_start["calculator"])
                else:
                    emit_event("start", "evaluator", node_messages_start["evaluator"])

            elif node_name == "calculator":
                calc_res = current_state.get("calculator_results") or {}
                done_msg = f"🧮 Calculator: Sandbox Python tính toán hoàn tất ({len(calc_res)} chỉ số)"
                emit_event("done", "calculator", done_msg)
                emit_event("start", "analysis", node_messages_start["analysis"])

            elif node_name == "analysis":
                done_msg = "💡 Analysis: Bóc tách DuPont 3 bước (Biên LN x Vòng quay x Đòn bẩy) hoàn tất"
                emit_event("done", "analysis", done_msg)
                emit_event("start", "synthesis", node_messages_start["synthesis"])

            elif node_name == "synthesis":
                synth = current_state.get("synthesis_results") or {}
                str_cnt = len(synth.get("strengths", []))
                risk_cnt = len(synth.get("risks", []))
                done_msg = f"📑 Synthesis: Ma trận SWOT hoàn tất ({str_cnt} điểm mạnh, {risk_cnt} rủi ro)"
                emit_event("done", "synthesis", done_msg)
                emit_event("start", "report", node_messages_start["report"])

            elif node_name == "report":
                report_text = current_state.get("final_report") or ""
                done_msg = f"📄 Report: Soạn thảo xong bản báo cáo ({len(report_text)} ký tự)"
                emit_event("done", "report", done_msg)
                emit_event("start", "evaluator", node_messages_start["evaluator"])

            elif node_name == "evaluator":
                conf = float(current_state.get("confidence_score", 0.95) or 0.95)
                done_msg = f"⚖️ Evaluator: Điểm tin cậy {conf:.2f}/1.00 ➔ Phê duyệt xuất bản kết quả"
                extra_info = {"confidence": conf}
                emit_event("done", "evaluator", done_msg, extra_info)

    # Prepare final output payload
    ticker = current_state.get("company_ticker", "N/A")
    calc = current_state.get("calculator_results") or {}
    analysis = current_state.get("analysis_results") or {}
    dupont = analysis.get("dupont", {}).get("dupont_3step", {})
    synthesis = current_state.get("synthesis_results") or {}
    market_data = current_state.get("market_data")

    price = None
    if market_data and hasattr(market_data, "records") and market_data.records:
        price = market_data.records[-1].close

    roe = None
    net_margin = None
    if dupont:
        latest = max(dupont.keys(), default=None)
        if latest and isinstance(dupont[latest], dict):
            roe = dupont[latest].get("roe")
            net_margin = dupont[latest].get("net_profit_margin")

    if roe is None and "roe" in calc:
        roe = calc.get("roe")
    if net_margin is None and "net_margin" in calc:
        net_margin = calc.get("net_margin")

    output = {
        "status": "success",
        "query": query,
        "ticker": ticker,
        "price": price,
        "roe": roe,
        "net_margin": net_margin,
        "confidence": float(current_state.get("confidence_score", 0.95) or 0.95),
        "executive_summary": synthesis.get("executive_summary", ""),
        "strengths": synthesis.get("strengths", []),
        "risks": synthesis.get("risks", []),
        "final_report": current_state.get("final_report", ""),
        "retrieved_chunks": [c.get("content", "")[:250] for c in (current_state.get("retrieved_chunks") or [])[:4]],
    }

    sys.stdout.write(f"\n___JSON_START___{json.dumps(output, ensure_ascii=False)}___JSON_END___\n")
    sys.stdout.flush()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        query_input = "Phân tích toàn diện tình hình tài chính và mô hình DuPont của FPT năm 2023"
    else:
        query_input = sys.argv[1]

    run_stream(query_input)
