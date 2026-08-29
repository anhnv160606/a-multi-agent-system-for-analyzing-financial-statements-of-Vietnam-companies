"""Synthesis Agent — Tổng hợp kết quả từ 3 agents thành SynthesisResult JSON.

Pipeline position:
    RetrieverAgent → CalculatorAgent → AnalysisAgent → **SynthesisAgent** → ReportAgent

Nhận:
    state["query"]              — Câu hỏi gốc
    state["company_ticker"]     — Mã CK
    state["fiscal_years"]       — Danh sách năm
    state["retrieved_chunks"]   — Context văn bản từ retriever
    state["calculator_results"] — Metrics đã tính (ROE, ROA, ...)
    state["analysis_results"]   — DuPont, Trend, Common-size, Peer comparison

Xuất ra:
    state["synthesis_results"]  — SynthesisResult (structured JSON)
    state["confidence_score"]   — Điểm tin cậy tổng hợp
    state["provenance"]         — Provenance entry
    state["errors"]             — Lỗi (nếu có)

Lưu ý: KHÔNG nhận dữ liệu từ ModelingAgent (bỏ qua trong MVP).

Task: 4.8 (feature_list.md)
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from src.agents.base_agent import BaseAgent, track_tokens
from src.utils.logger import get_logger

logger = get_logger("src.agents.synthesisagent")

# ---------------------------------------------------------------------------
# Schema JSON gửi cho LLM — dùng làm prompt context
# ---------------------------------------------------------------------------
_OUTPUT_SCHEMA = """{
  "ticker": "<mã CK>",
  "company_name": "<tên công ty đầy đủ>",
  "fiscal_years": [<danh sách năm>],
  "generated_at": "<ISO timestamp>",
  "executive_summary": "<3-5 câu tóm tắt toàn bộ kết quả, có số liệu cụ thể>",
  "key_metrics": {
    "<năm>": {
      "roe": <float hoặc null>,
      "roa": <float hoặc null>,
      "net_margin": <float hoặc null>,
      "gross_margin": <float hoặc null>,
      "revenue": <float hoặc null>,
      "net_income": <float hoặc null>,
      "total_assets": <float hoặc null>,
      "equity": <float hoặc null>
    }
  },
  "analysis_highlights": {
    "dupont_summary": "<2-4 câu tóm tắt DuPont, ý nghĩa kinh tế>",
    "trend_summary": "<2-4 câu tóm tắt xu hướng qua các năm>",
    "common_size_summary": "<2-4 câu tóm tắt cơ cấu tài chính>",
    "peer_summary": "<2-4 câu so sánh ngành hoặc 'Không có dữ liệu so sánh ngành'>"
  },
  "strengths": ["<điểm mạnh 1 kèm số liệu>", "<điểm mạnh 2>", "..."],
  "risks": ["<rủi ro 1 kèm số liệu hoặc căn cứ>", "<rủi ro 2>", "..."],
  "key_findings": ["<phát hiện quan trọng 1>", "<phát hiện 2>", "..."],
  "overall_assessment": "<1 đoạn 4-6 câu nhận định tổng thể và hàm ý đầu tư>",
  "data_quality": {
    "completeness_score": <float 0.0-1.0>,
    "data_gaps": ["<gap 1>", "..."],
    "confidence": <float 0.0-1.0>
  }
}"""

# Số tokens tối đa cho context gửi LLM (ước lượng ký tự)
_MAX_CONTEXT_CHARS = 8000
# Số retrieved_chunks tối đa dùng làm context
_MAX_CHUNKS = 3


class SynthesisAgent(BaseAgent):
    """Tổng hợp kết quả phân tích từ 3 agents thành SynthesisResult JSON nhất quán."""

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        llm: Any = None,
        prompt_template: str | dict = "synthesis",
    ) -> None:
        super().__init__(
            config=config or {},
            llm=llm,
            prompt_template=prompt_template,
        )

    # =========================================================================
    # Public entrypoint
    # =========================================================================

    def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
        """Entrypoint chính của SynthesisAgent.

        Flow:
            1. Validate: cần ít nhất analysis_results hoặc calculator_results
            2. _build_synthesis_context() → context dict
            3. _call_synthesis_llm() → raw JSON string
            4. _parse_synthesis_response() → SynthesisResult dict
            5. Ghi state["synthesis_results"], confidence_score, provenance
        """
        ticker = state.get("company_ticker", "N/A")
        query = state.get("query", "")
        fiscal_years = state.get("fiscal_years", [])
        run_id = state.get("run_id", "")

        # --- Validate đầu vào ---
        has_analysis = bool(state.get("analysis_results"))
        has_calc = bool(state.get("calculator_results"))
        has_chunks = bool(state.get("retrieved_chunks"))
        has_market = bool(state.get("market_data")) or bool(state.get("market_ratios"))
        if not has_analysis and not has_calc and not has_chunks and not has_market:
            msg = (
                "SynthesisAgent: không có dữ liệu phân tích, tính toán hoặc tra cứu "
                "trong state — không thể tổng hợp."
            )
            self._append_error(state, msg)
            self.logger.warning(
                msg,
                extra={"event": "synthesis_skip", "run_id": run_id, "ticker": ticker},
            )
            return state

        self.logger.info(
            "SynthesisAgent: start",
            extra={
                "event": "agent_start",
                "run_id": run_id,
                "ticker": ticker,
                "has_analysis": has_analysis,
                "has_calc": has_calc,
            },
        )

        # --- Build context ---
        context = self._build_synthesis_context(state)

        # --- Gọi LLM ---
        raw_response = self._call_synthesis_llm(
            context_json=json.dumps(context, ensure_ascii=False, indent=2),
            query=query,
            ticker=ticker,
            fiscal_years=str(fiscal_years),
        )

        # --- Parse kết quả ---
        synthesis = self._parse_synthesis_response(raw_response, context, state)

        # --- Cập nhật state ---
        state["synthesis_results"] = synthesis
        confidence = float(synthesis.get("data_quality", {}).get("confidence", 0.5))
        state["confidence_score"] = confidence

        state.setdefault("provenance", []).append({
            "agent": "SynthesisAgent",
            "ticker": ticker,
            "fiscal_years": fiscal_years,
            "has_analysis_input": has_analysis,
            "has_calc_input": has_calc,
            "completeness_score": synthesis.get("data_quality", {}).get("completeness_score", 0.0),
            "confidence": confidence,
            "llm_used": self.llm is not None,
        })

        self._log_step(
            input={"ticker": ticker, "fiscal_years": fiscal_years},
            output=synthesis,
            confidence=confidence,
        )
        self.logger.info(
            "SynthesisAgent: done",
            extra={
                "event": "agent_done",
                "run_id": run_id,
                "ticker": ticker,
                "confidence": confidence,
                "strengths_count": len(synthesis.get("strengths", [])),
                "risks_count": len(synthesis.get("risks", [])),
            },
        )
        return state

    # =========================================================================
    # Internal helpers
    # =========================================================================

    def _build_synthesis_context(self, state: dict[str, Any]) -> dict[str, Any]:
        """Chuẩn bị context rút gọn từ state để truyền vào LLM.

        Giới hạn kích thước để tránh vượt context window:
        - calculator_results: lấy toàn bộ (thường nhỏ)
        - analysis_results: lấy dupont + trend + common_size (bỏ raw data)
        - retrieved_chunks: lấy tối đa _MAX_CHUNKS, chỉ lấy "content"
        """
        ticker = state.get("company_ticker", "N/A")
        calc = state.get("calculator_results") or {}
        analysis = state.get("analysis_results") or {}
        chunks = state.get("retrieved_chunks") or []

        # Key metrics từ calculator
        key_metrics_from_calc: dict = {}
        if calc:
            key_metrics_from_calc = {
                k: v for k, v in calc.items()
                if isinstance(v, (int, float)) and not isinstance(v, bool)
            }

        # Key metrics từ analysis (nếu có year-keyed data)
        key_metrics_by_year: dict = {}
        analysis_income = analysis.get("financial_data", {}).get("income_statement", {})
        analysis_balance = analysis.get("financial_data", {}).get("balance_sheet", {})
        for year in (state.get("fiscal_years") or []):
            income_row = analysis_income.get(year) or analysis_income.get(str(year)) or {}
            balance_row = analysis_balance.get(year) or analysis_balance.get(str(year)) or {}
            merged = {**income_row, **balance_row}
            if merged:
                key_metrics_by_year[str(year)] = merged

        # DuPont summary (chỉ lấy dupont_3step, bỏ 5step để tiết kiệm token)
        dupont_data = analysis.get("dupont", {})
        dupont_3step = dupont_data.get("dupont_3step", {})
        dupont_interp = dupont_data.get("interpretation", "")

        # Trend summary
        trend_data = analysis.get("trend", {})
        trend_direction = trend_data.get("trend_direction", {})
        trend_cagr = trend_data.get("cagr", {})
        trend_interp = trend_data.get("interpretation", "")

        # Common-size summary
        cs_data = analysis.get("common_size", {})
        cs_interp = cs_data.get("interpretation", "")

        # Peer comparison summary
        peer_data = analysis.get("peer_comparison", {})
        peer_interp = peer_data.get("interpretation", "")
        peer_position = peer_data.get("company_position", {})

        # Data gaps
        data_gaps = analysis.get("data_gaps", [])

        # Text excerpts (top _MAX_CHUNKS)
        text_excerpts = []
        sorted_chunks = sorted(
            chunks,
            key=lambda c: float(c.get("hybrid_score") or c.get("vector_score") or 0.0),
            reverse=True,
        )[:_MAX_CHUNKS]
        for chunk in sorted_chunks:
            content = str(chunk.get("content", ""))[:500]  # tối đa 500 ký tự / chunk
            if content:
                text_excerpts.append(content)

        # Realtime market data from VNStock
        market_data_info = {}
        m_data = state.get("market_data")
        if m_data and hasattr(m_data, "records") and m_data.records:
            latest = m_data.records[-1]
            market_data_info = {
                "latest_price": getattr(latest, "close", None),
                "open": getattr(latest, "open", None),
                "high": getattr(latest, "high", None),
                "low": getattr(latest, "low", None),
                "volume": getattr(latest, "volume", None),
                "date": str(getattr(latest, "time", "")),
            }

        context = {
            "ticker": ticker,
            "company_name": self._extract_company_name(state),
            "market_data": market_data_info,
            "fiscal_years": state.get("fiscal_years", []),
            "key_metrics_from_calculator": key_metrics_from_calc,
            "key_metrics_by_year": key_metrics_by_year,
            "dupont": {
                "dupont_3step": {
                    str(k): v for k, v in dupont_3step.items()
                } if dupont_3step else {},
                "interpretation": dupont_interp,
            },
            "trend": {
                "direction": trend_direction,
                "cagr": trend_cagr,
                "interpretation": trend_interp,
            },
            "common_size": {
                "interpretation": cs_interp,
            },
            "peer_comparison": {
                "company_position": peer_position,
                "interpretation": peer_interp,
                "has_peer_data": bool(peer_data.get("has_peer_data")),
            },
            "data_gaps": data_gaps,
            "text_excerpts": text_excerpts,
        }

        # Giới hạn kích thước tổng
        context_str = json.dumps(context, ensure_ascii=False)
        if len(context_str) > _MAX_CONTEXT_CHARS:
            # Cắt bớt text_excerpts trước
            while len(json.dumps(context, ensure_ascii=False)) > _MAX_CONTEXT_CHARS and context["text_excerpts"]:
                context["text_excerpts"].pop()

        return context

    def _extract_company_name(self, state: dict[str, Any]) -> str:
        """Lấy tên công ty từ retrieved_chunks metadata hoặc fallback về ticker."""
        ticker = state.get("company_ticker", "N/A")
        chunks = state.get("retrieved_chunks") or []
        for chunk in chunks:
            meta = chunk.get("metadata", {})
            name = meta.get("company_name") or meta.get("organ_name")
            if name and isinstance(name, str) and len(name) > 2:
                return name.strip()
        return f"Cong ty {ticker}"

    def _estimate_completeness(self, state: dict[str, Any]) -> float:
        """Tính điểm completeness [0.0, 1.0] dựa trên số nguồn dữ liệu có sẵn."""
        score = 0.0
        total = 4.0
        if state.get("retrieved_chunks"):
            score += 1.0
        if state.get("table_data"):
            score += 1.0
        if state.get("calculator_results"):
            score += 1.0
        if state.get("analysis_results"):
            score += 1.0
        # Bonus: nếu analysis có đủ 3 phân tích
        analysis = state.get("analysis_results") or {}
        bonus_sections = sum(
            1 for k in ["dupont", "trend", "common_size"]
            if isinstance(analysis.get(k), dict) and analysis.get(k)
        )
        score += bonus_sections * 0.1
        return min(round(score / total, 2), 1.0)

    @track_tokens
    def _call_synthesis_llm(
        self,
        context_json: str,
        query: str,
        ticker: str,
        fiscal_years: str,
    ) -> str:
        """Gọi LLM tổng hợp kết quả. Trả về raw text (JSON string từ LLM)."""
        if self.llm is None:
            return ""

        system_prompt = self.prompt_template.get("system_prompt", "")
        user_tmpl = self.prompt_template.get("user_template", "")
        user_prompt = user_tmpl.format(
            ticker=ticker,
            query=query,
            fiscal_years=fiscal_years,
            analysis_context=context_json,
            output_schema=_OUTPUT_SCHEMA,
        )

        from langchain_core.messages import HumanMessage, SystemMessage  # type: ignore
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        try:
            response = self.llm.invoke(messages)
            return response.content if hasattr(response, "content") else str(response)
        except Exception as exc:
            self.logger.warning(
                f"SynthesisAgent LLM call failed: {exc}",
                extra={"event": "llm_error"},
            )
            return ""

    def _parse_synthesis_response(
        self,
        raw: str,
        context: dict[str, Any],
        state: dict[str, Any],
    ) -> dict[str, Any]:
        """Parse JSON từ LLM response. Fallback về placeholder nếu parse fail."""
        ticker = context.get("ticker", "N/A")
        fiscal_years = context.get("fiscal_years", [])
        now_iso = datetime.now(timezone.utc).isoformat()
        completeness = self._estimate_completeness(state)
        analysis_data_gaps = (state.get("analysis_results") or {}).get("data_gaps", [])
        analysis_confidence = (state.get("analysis_results") or {}).get("confidence", 0.5)
        calc_confidence = 0.95 if state.get("calculator_results") else 0.0

        # Thử parse JSON từ LLM
        if raw:
            # Xử lý trường hợp LLM bọc JSON trong markdown code fence
            cleaned = re.sub(r"```(?:json)?\s*", "", raw).replace("```", "").strip()
            try:
                parsed = json.loads(cleaned)
                if isinstance(parsed, dict):
                    # Đảm bảo các field bắt buộc có mặt
                    parsed.setdefault("ticker", ticker)
                    parsed.setdefault("fiscal_years", fiscal_years)
                    parsed.setdefault("generated_at", now_iso)
                    if "data_quality" not in parsed:
                        parsed["data_quality"] = {
                            "completeness_score": completeness,
                            "data_gaps": analysis_data_gaps,
                            "confidence": round(
                                (completeness + float(analysis_confidence)) / 2, 2
                            ),
                        }
                    return parsed
            except (json.JSONDecodeError, ValueError):
                self.logger.warning(
                    "SynthesisAgent: LLM response is not valid JSON — using fallback",
                    extra={"event": "json_parse_fail", "raw_preview": raw[:200]},
                )

        # --- Fallback placeholder (không có LLM hoặc parse fail) ---
        calc = state.get("calculator_results") or {}
        analysis = state.get("analysis_results") or {}

        # Lấy key_metrics từ calculator + analysis
        key_metrics: dict = {}
        for year in fiscal_years:
            year_str = str(year)
            # Từ calculator (flat metrics)
            row: dict = {}
            for field in ["roe", "roa", "net_margin", "gross_margin",
                           "revenue", "net_income", "total_assets", "equity"]:
                val = calc.get(field)
                row[field] = float(val) if isinstance(val, (int, float)) else None

            # Ghi đè/bổ sung từ DuPont nếu có
            dupont_year = (analysis.get("dupont", {}).get("dupont_3step") or {}).get(year) \
                or (analysis.get("dupont", {}).get("dupont_3step") or {}).get(year_str)
            if dupont_year:
                if row["roe"] is None:
                    row["roe"] = dupont_year.get("roe")

            key_metrics[year_str] = row

        dupont_interp = (analysis.get("dupont") or {}).get("interpretation", "Chua co du lieu.")
        trend_interp = (analysis.get("trend") or {}).get("interpretation", "Chua co du lieu.")
        cs_interp = (analysis.get("common_size") or {}).get("interpretation", "Chua co du lieu.")
        peer_interp = (analysis.get("peer_comparison") or {}).get(
            "interpretation", "Khong co du lieu so sanh nganh."
        )

        overall_confidence = round(
            (completeness * 0.4 + float(analysis_confidence) * 0.4 + calc_confidence * 0.2), 2
        )

        return {
            "ticker": ticker,
            "company_name": self._extract_company_name(state),
            "fiscal_years": fiscal_years,
            "generated_at": now_iso,
            "executive_summary": (
                f"Bao cao tong hop cho {ticker} giai doan {fiscal_years}. "
                f"He thong da thu thap va xu ly du lieu tai chinh tu {len(state.get('retrieved_chunks') or [])} doan van ban "
                f"va {len(state.get('table_data') or [])} ban ghi SQL. "
                f"Ket qua duoi day dua tren du lieu co san voi do tin cay {overall_confidence:.0%}."
            ),
            "key_metrics": key_metrics,
            "analysis_highlights": {
                "dupont_summary": dupont_interp,
                "trend_summary": trend_interp,
                "common_size_summary": cs_interp,
                "peer_summary": peer_interp,
            },
            "strengths": [],
            "risks": [],
            "key_findings": [],
            "overall_assessment": (
                "Phan tich duoc tao tu du lieu co san. "
                "Vui long kiem tra lai voi chuyen gia truoc khi dua ra quyet dinh dau tu."
            ),
            "data_quality": {
                "completeness_score": completeness,
                "data_gaps": analysis_data_gaps,
                "confidence": overall_confidence,
            },
        }

    # =========================================================================
    # Error helper
    # =========================================================================

    def _append_error(self, state: dict[str, Any], message: str) -> None:
        """Ghi lỗi vào state["errors"]."""
        state.setdefault("errors", [])
        if isinstance(state["errors"], list):
            state["errors"].append(message)
        self.logger.error(message, extra={"event": "synthesis_error"})
