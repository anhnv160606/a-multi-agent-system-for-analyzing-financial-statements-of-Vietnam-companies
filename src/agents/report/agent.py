"""Report Agent — Sinh báo cáo phân tích tài chính Markdown từ SynthesisResult.

Pipeline position:
    SynthesisAgent → **ReportAgent** → END

Chiến lược:
    - 1 LLM call duy nhất để fill nội dung prose vào template có sẵn.
    - Bảng key_metrics và bullet lists render bằng Python (deterministic, không LLM).
    - LLM dùng placeholder {{CONTENT_X}} trong output → Python thay thế bằng nội dung thực.

Nhận:
    state["synthesis_results"]  — SynthesisResult JSON (từ SynthesisAgent)
    state["query"]              — Câu hỏi gốc
    state["company_ticker"]     — Mã CK
    state["fiscal_years"]       — Danh sách năm

Xuất ra:
    state["final_report"]       — Báo cáo Markdown hoàn chỉnh
    state["provenance"]         — Provenance entry
    state["errors"]             — Lỗi (nếu có)

Task: 4.9, 4.10 (feature_list.md)
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from src.agents.base_agent import BaseAgent, track_tokens
from src.utils.logger import get_logger

logger = get_logger("src.agents.reportagent")

# Thứ tự cột hiển thị trong bảng key_metrics
_METRIC_COLUMNS = [
    ("roe",          "ROE",           ".1%"),
    ("roa",          "ROA",           ".1%"),
    ("net_margin",   "Bien LN rong",  ".1%"),
    ("gross_margin", "Bien LN gop",   ".1%"),
    ("revenue",      "Doanh thu (ty)", ",.0f"),
    ("net_income",   "LN sau thue (ty)", ",.0f"),
    ("total_assets", "Tong tai san (ty)", ",.0f"),
    ("equity",       "Von CSH (ty)",   ",.0f"),
]

# Lỗi dữ liệu — footer tiêu chuẩn cho section 6
_DISCLAIMER_TEMPLATE = """*Báo cáo này được tạo tự động bởi hệ thống phân tích AI và chỉ mang tính tham khảo.*
*Mọi quyết định đầu tư cần được xem xét kỹ lưỡng và tham khảo ý kiến chuyên gia tài chính.*

**Giới hạn dữ liệu:**
{data_gaps_section}
- Độ tin cậy tổng hợp: **{confidence:.0%}**
- Mức độ đầy đủ dữ liệu: **{completeness:.0%}**"""


class ReportAgent(BaseAgent):
    """Sinh báo cáo phân tích tài chính Markdown từ SynthesisResult."""

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        llm: Any = None,
        prompt_template: str | dict = "report",
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
        """Entrypoint chính của ReportAgent.

        Flow:
            1. Validate: synthesis_results phải có trong state
            2. _render_metrics_table() → Markdown table (Python)
            3. _render_bullet_list() → strengths/risks bullets (Python)
            4. _generate_report_llm() → prose sections (1 LLM call)
            5. _assemble_report() → inject table + bullets vào LLM output
            6. Ghi state["final_report"], provenance
        """
        ticker = state.get("company_ticker", "N/A")
        query = state.get("query", "")
        run_id = state.get("run_id", "")
        synthesis = state.get("synthesis_results")

        if not isinstance(synthesis, dict):
            msg = (
                "ReportAgent: synthesis_results khong co trong state hoac co dinh dang sai — "
                "khong the sinh bao cao."
            )
            self._append_error(state, msg)
            self.logger.warning(msg, extra={"event": "report_skip", "run_id": run_id})
            return state

        self.logger.info(
            "ReportAgent: start",
            extra={"event": "agent_start", "run_id": run_id, "ticker": ticker},
        )

        # 1. Render deterministic parts (Python, no LLM)
        metrics_table = self._render_metrics_table(synthesis.get("key_metrics", {}))
        strengths_md = self._render_bullet_list(synthesis.get("strengths", []))
        risks_md = self._render_bullet_list(synthesis.get("risks", []))
        disclaimer = self._render_disclaimer(synthesis)

        # 2. Gọi LLM (1 lần) để viết prose
        llm_markdown = self._generate_report_llm(synthesis, query)

        # 3. Lắp ráp report cuối
        final_report = self._assemble_report(
            llm_markdown=llm_markdown,
            metrics_table=metrics_table,
            strengths_md=strengths_md,
            risks_md=risks_md,
            disclaimer=disclaimer,
            synthesis=synthesis,
        )

        state["final_report"] = final_report
        state.setdefault("provenance", []).append({
            "agent": "ReportAgent",
            "ticker": ticker,
            "report_length_chars": len(final_report),
            "llm_used": self.llm is not None,
        })

        self._log_step(
            input={"ticker": ticker, "synthesis_keys": list(synthesis.keys())},
            output={"report_length": len(final_report)},
            confidence=float(synthesis.get("data_quality", {}).get("confidence", 0.5)),
        )
        self.logger.info(
            "ReportAgent: done",
            extra={
                "event": "agent_done",
                "run_id": run_id,
                "ticker": ticker,
                "report_chars": len(final_report),
            },
        )
        return state

    # =========================================================================
    # Deterministic rendering (Python only, NO LLM)
    # =========================================================================

    def _render_metrics_table(self, key_metrics: dict[str, Any]) -> str:
        """Render bảng Markdown từ key_metrics dict. Pure Python, không dùng LLM.

        Args:
            key_metrics: {year_str: {metric_name: float|None}}

        Returns:
            Markdown table string với header và data rows.
        """
        if not key_metrics:
            return "*Khong co du lieu chi so tai chinh.*"

        years = sorted(key_metrics.keys())

        # Build header
        header_cells = ["Chỉ số"] + [str(y) for y in years]
        separator = ["---"] + ["---:"] * len(years)
        header_row = "| " + " | ".join(header_cells) + " |"
        sep_row = "| " + " | ".join(separator) + " |"

        rows = [header_row, sep_row]
        for metric_key, metric_label, fmt in _METRIC_COLUMNS:
            cells = [metric_label]
            has_any_value = False
            for year in years:
                val = (key_metrics.get(year) or {}).get(metric_key)
                if val is not None:
                    has_any_value = True
                    try:
                        formatted = format(float(val), fmt)
                    except (ValueError, TypeError):
                        formatted = str(val)
                    cells.append(formatted)
                else:
                    cells.append("N/A")
            if has_any_value:
                rows.append("| " + " | ".join(cells) + " |")

        return "\n".join(rows)

    def _render_bullet_list(self, items: list[str], prefix: str = "-") -> str:
        """Render bullet list Markdown. Pure Python.

        Args:
            items: Danh sách chuỗi string.
            prefix: Ký tự đầu bullet (mặc định "-").

        Returns:
            Markdown bullet list hoặc placeholder nếu danh sách rỗng.
        """
        if not items:
            return "*Chua co du lieu.*"
        return "\n".join(f"{prefix} {item.strip()}" for item in items if item.strip())

    def _render_disclaimer(self, synthesis: dict[str, Any]) -> str:
        """Render section 6 (Lưu ý) từ data_quality. Pure Python."""
        dq = synthesis.get("data_quality", {})
        gaps = dq.get("data_gaps", [])
        confidence = float(dq.get("confidence", 0.5))
        completeness = float(dq.get("completeness_score", 0.5))

        if gaps:
            gaps_section = "\n".join(f"- {g}" for g in gaps)
        else:
            gaps_section = "- Khong phat hien gap du lieu dang ke."

        return _DISCLAIMER_TEMPLATE.format(
            data_gaps_section=gaps_section,
            confidence=confidence,
            completeness=completeness,
        )

    # =========================================================================
    # LLM call
    # =========================================================================

    @track_tokens
    def _generate_report_llm(
        self,
        synthesis: dict[str, Any],
        query: str,
    ) -> str:
        """Gọi LLM 1 lần để fill nội dung prose vào template.

        Trả về Markdown string với các placeholder {{CONTENT_X}} đã được fill.
        Placeholder {{METRICS_TABLE}}, {{STRENGTHS_LIST}}, {{RISKS_LIST}}
        được giữ nguyên để Python thay thế sau.

        Nếu llm=None → trả về fallback Markdown template với nội dung từ synthesis.
        """
        if self.llm is None:
            return self._build_fallback_markdown(synthesis)

        ticker = synthesis.get("ticker", "N/A")
        years = synthesis.get("fiscal_years", [])
        generated_at = synthesis.get("generated_at", datetime.now(timezone.utc).isoformat())

        # Chuẩn bị synthesis JSON gửi LLM (bỏ key_metrics để không trùng với bảng)
        synthesis_for_llm = {
            k: v for k, v in synthesis.items()
            if k != "key_metrics"
        }

        system_prompt = self.prompt_template.get("system_prompt", "")
        user_tmpl = self.prompt_template.get("user_template", "")
        user_prompt = user_tmpl.format(
            synthesis_json=json.dumps(synthesis_for_llm, ensure_ascii=False, indent=2),
            ticker=ticker,
            years=", ".join(str(y) for y in years),
            generated_at=generated_at[:10],
        )

        from langchain_core.messages import HumanMessage, SystemMessage  # type: ignore
        import os, sys
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        try:
            if os.environ.get("STREAM_REPORT_TOKENS") == "1" and hasattr(self.llm, "stream"):
                collected = []
                for chunk in self.llm.stream(messages):
                    collected.append(chunk)
                    sys.stdout.write(f"__TOKEN_CHUNK__{json.dumps({'chunk': chunk}, ensure_ascii=False)}__TOKEN_CHUNK__\n")
                    sys.stdout.flush()
                return "".join(collected)

            response = self.llm.invoke(messages)
            content = response.content if hasattr(response, "content") else str(response)
            
            # BỔ SUNG ĐOẠN NÀY: Xử lý trường hợp content là list do LangChain trả về
            if isinstance(content, list):
                text_parts = []
                for item in content:
                    if isinstance(item, str):
                        text_parts.append(item)
                    elif isinstance(item, dict) and "text" in item:
                        text_parts.append(item["text"])
                    elif hasattr(item, "text"):  # Đề phòng object có thuộc tính text
                        text_parts.append(item.text)
                return "".join(text_parts)
                
            return str(content)
            
        except Exception as exc:
            self.logger.warning(
                f"ReportAgent LLM call failed: {exc}",
                extra={"event": "llm_error"},
            )
            return 'Lỗi LLM: không thể sinh nội dung báo cáo. Vui lòng thử lại sau hoặc liên hệ bộ phận hỗ trợ.'
    def _build_fallback_markdown(self, synthesis: dict[str, Any]) -> str:
        """Fallback khi không có LLM — dùng trực tiếp các string từ synthesis_results."""
        ticker = synthesis.get("ticker", "N/A")
        years = synthesis.get("fiscal_years", [])
        generated_at = synthesis.get("generated_at", datetime.now(timezone.utc).isoformat())
        highlights = synthesis.get("analysis_highlights", {})

        return (
            f"# Bao cao Phan tich Tai chinh — {ticker} ({', '.join(str(y) for y in years)})\n\n"
            f"*Ngay tao: {generated_at[:10]}*\n\n"
            "---\n\n"
            "## 1. Tom tat Dieu hanh\n\n"
            f"{{{{CONTENT_1}}}}\n\n"
            "---\n\n"
            "## 2. Thong tin Doanh nghiep\n\n"
            f"{{{{CONTENT_2}}}}\n\n"
            "---\n\n"
            "## 3. Phan tich Tai chinh\n\n"
            "### 3.1. Bang Chi so Tai chinh Chinh\n\n"
            "{{METRICS_TABLE}}\n\n"
            "### 3.2. Phan tich DuPont\n\n"
            f"{highlights.get('dupont_summary', 'Chua co du lieu.')}\n\n"
            "### 3.3. Phan tich Xu huong\n\n"
            f"{highlights.get('trend_summary', 'Chua co du lieu.')}\n\n"
            "### 3.4. Co cau Tai chinh (Common-size)\n\n"
            f"{highlights.get('common_size_summary', 'Chua co du lieu.')}\n\n"
            "### 3.5. So sanh cung nganh\n\n"
            f"{highlights.get('peer_summary', 'Khong co du lieu so sanh nganh.')}\n\n"
            "---\n\n"
            "## 4. Diem manh va Rui ro\n\n"
            "### Diem manh\n\n"
            "{{STRENGTHS_LIST}}\n\n"
            "### Rui ro\n\n"
            "{{RISKS_LIST}}\n\n"
            "---\n\n"
            "## 5. Nhan dinh Tong quat\n\n"
            f"{{{{CONTENT_5}}}}\n\n"
            "---\n\n"
            "## 6. Luu y va Gioi han Bao cao\n\n"
            "{{DISCLAIMER}}\n"
        )

    # =========================================================================
    # Assembly
    # =========================================================================

    def _assemble_report(
        self,
        llm_markdown: str,
        metrics_table: str,
        strengths_md: str,
        risks_md: str,
        disclaimer: str,
        synthesis: dict[str, Any],
    ) -> str:
        """Lắp ráp báo cáo cuối cùng bằng cách thay thế các placeholders.

        Placeholders Python thay thế (không phải LLM):
            {{METRICS_TABLE}}    → bảng Markdown key_metrics
            {{STRENGTHS_LIST}}   → bullet list strengths
            {{RISKS_LIST}}       → bullet list risks
            {{DISCLAIMER}}       → section 6 static
            {{CONTENT_1}}        → executive_summary (nếu LLM chưa fill)
            {{CONTENT_2}}        → company overview fallback
            {{CONTENT_5}}        → overall_assessment fallback
        """
        report = llm_markdown

        # Thay thế deterministic placeholders (hỗ trợ cả {{PLACEHOLDER}} và {PLACEHOLDER})
        for ph, val in [
            ("METRICS_TABLE", metrics_table),
            ("STRENGTHS_LIST", strengths_md),
            ("RISKS_LIST", risks_md),
            ("DISCLAIMER", disclaimer),
        ]:
            report = report.replace(f"{{{{{ph}}}}}", val).replace(f"{{{ph}}}", val)

        # Fallback cho các CONTENT_ placeholders (nếu LLM quên fill)
        exec_summary = synthesis.get("executive_summary", "")
        company_name = synthesis.get("company_name", synthesis.get("ticker", ""))
        ticker = synthesis.get("ticker", "")
        overall = synthesis.get("overall_assessment", "")

        report = report.replace(
            "{{CONTENT_1}}",
            exec_summary or f"Bao cao phan tich tai chinh cho {ticker}.",
        )
        report = report.replace(
            "{{CONTENT_2}}",
            f"{company_name} ({ticker}) la doanh nghiep niem yet tren thi truong chung khoan Viet Nam."
            if not exec_summary else company_name,
        )
        report = report.replace(
            "{{CONTENT_5}}",
            overall or "Vui long tham khao chuyen gia truoc khi dua ra quyet dinh dau tu.",
        )
        report = report.replace("{{CONTENT_6}}", disclaimer)

        # Xoá placeholder còn sót lại
        report = re.sub(r"\{\{CONTENT_[^}]+\}\}", "*[Noi dung chua co]*", report)

        return report.strip()

    # =========================================================================
    # Error helper
    # =========================================================================

    def _append_error(self, state: dict[str, Any], message: str) -> None:
        """Ghi lỗi vào state["errors"]."""
        state.setdefault("errors", [])
        if isinstance(state["errors"], list):
            state["errors"].append(message)
        self.logger.error(message, extra={"event": "report_error"})
