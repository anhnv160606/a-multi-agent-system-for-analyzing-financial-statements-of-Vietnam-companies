"""Router Agent: Adaptive Strategy Classification & Routing (Task 5.3).

Pipeline position:
    **RouterAgent** → (retriever_node | calculator_node | full_pipeline)

Classifies user query complexity and intent into 4 strategy categories:
    1. "simple"     — Qualitative search / Text RAG pass (e.g. "Chiến lược AI của FPT", "Ban lãnh đạo")
    2. "calculate"  — Pure quantitative SQL & Python Sandbox computation (e.g. "Tính doanh thu FPT 2023")
    3. "analysis"   — Full multi-agent financial analysis (DuPont, Trend, Common-size)
    4. "valuation"  — Valuation multiples & financial modeling

Features:
    - LLM-powered semantic intent classification with structured JSON output.
    - Automatic Ticker & Fiscal Year entity extraction.
    - Deterministic Regex & Keyword Rule-based Fallback for 100% offline robustness.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, MutableMapping
from typing import Any, Dict, List, Literal, Optional

from src.agents.base_agent import BaseAgent, track_tokens
from src.utils.logger import get_logger

logger = get_logger("src.orchestrator.router")

QueryType = Literal["simple", "calculate", "analysis", "valuation"]

# Danh sách mã chứng khoán phổ biến trên thị trường Việt Nam
_COMMON_TICKERS = {
    "FPT", "VNM", "HPG", "VIC", "VHM", "VRE", "MWG", "MSN", "GAS", "SAB",
    "TCB", "VCB", "MBB", "BID", "CTG", "ACB", "VPB", "HDB", "STB", "TPB",
    "SSI", "VND", "HCM", "VCI", "DGC", "DCM", "DPM", "PVD", "PVS", "PLX",
    "KDH", "NLG", "DXG", "DIG", "PDR", "GMD", "HAH", "VHC", "ANV", "REE"
}


class RouterAgent(BaseAgent):
    """Phân loại độ phức tạp và hướng xử lý của câu hỏi người dùng."""

    def __init__(
        self,
        config: Mapping[str, Any] | None = None,
        llm: Any = None,
        prompt_template: str | Mapping[str, Any] = "router",
    ) -> None:
        super().__init__(config=config, llm=llm, prompt_template=prompt_template)
        self.default_query_type: QueryType = str(self.config.get("default_query_type", "analysis"))  # type: ignore

    def classify(
        self,
        query: str,
        ticker: Optional[str] = None,
        fiscal_years: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """Phân loại câu hỏi thành strategy phù hợp và bóc tách metadata.

        Returns:
            Dict chứa 'query_type', 'ticker', 'fiscal_years', 'confidence'.
        """
        clean_query = query.strip()
        if not clean_query:
            return {
                "query_type": "simple",
                "ticker": ticker or "FPT",
                "fiscal_years": fiscal_years or [2023],
                "confidence": 1.0,
            }

        # 1. Thử phân loại bằng LLM nếu có
        if self.llm is not None:
            try:
                system_prompt = self.prompt_template.get("system_prompt", "")
                user_template = self.prompt_template.get("user_template", "")
                user_prompt = user_template.format(
                    query=clean_query,
                    ticker=ticker or "",
                    fiscal_years=fiscal_years or [],
                )
                full_prompt = f"{system_prompt}\n\n{user_prompt}"
                response = self.llm.invoke(full_prompt)
                raw_content = response.content if hasattr(response, "content") else str(response)
                parsed = self._parse_llm_json(raw_content)
                if parsed and parsed.get("query_type") in ("simple", "calculate", "analysis", "valuation"):
                    # Hợp nhất ticker và fiscal_years
                    final_ticker = (parsed.get("ticker") or ticker or self._extract_ticker_regex(clean_query)).strip().upper()
                    final_years = parsed.get("fiscal_years") or fiscal_years or self._extract_years_regex(clean_query)
                    return {
                        "query_type": parsed["query_type"],
                        "ticker": final_ticker or "FPT",
                        "fiscal_years": sorted(list(set(final_years))) if final_years else [2023],
                        "confidence": float(parsed.get("confidence", 0.9)),
                    }
            except Exception as e:
                logger.warning(f"RouterAgent: LLM classification error ({e}). Using deterministic heuristic fallback.")

        # 2. Heuristic Rule-Based Fallback (Chạy offline, cực nhanh và chính xác)
        return self._heuristic_classify(clean_query, ticker, fiscal_years)

    def invoke(self, state: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
        """LangGraph Node entrypoint cho Router.

        Đọc:  state["query"], state["company_ticker"], state["fiscal_years"]
        Ghi:  state["query_type"], state["company_ticker"], state["fiscal_years"], state["confidence_score"]
        """
        query = str(state.get("query") or "").strip()
        current_ticker = state.get("company_ticker")
        current_years = state.get("fiscal_years")

        # Phân loại
        classification = self.classify(
            query=query,
            ticker=current_ticker,
            fiscal_years=current_years,
        )

        query_type: QueryType = classification["query_type"]
        state["query_type"] = query_type

        # Bổ sung ticker & fiscal_years nếu ban đầu state chưa có hoặc rỗng
        if not current_ticker and classification.get("ticker"):
            state["company_ticker"] = classification["ticker"]

        if (not current_years or len(current_years) == 0) and classification.get("fiscal_years"):
            state["fiscal_years"] = classification["fiscal_years"]

        state.setdefault("provenance", []).append({
            "agent": "RouterAgent",
            "query_type": query_type,
            "confidence": classification.get("confidence", 0.9),
        })

        self._log_step(
            input={"query": query, "ticker": current_ticker, "fiscal_years": current_years},
            output={
                "query_type": query_type,
                "ticker": state.get("company_ticker"),
                "fiscal_years": state.get("fiscal_years"),
            },
            confidence=classification.get("confidence", 0.9),
        )

        logger.info(
            f"RouterAgent: classified query into '{query_type}' "
            f"(ticker={state.get('company_ticker')}, years={state.get('fiscal_years')})"
        )
        return state

    # -----------------------------------------------------------------------
    # Helper & Fallback Methods
    # -----------------------------------------------------------------------

    def _parse_llm_json(self, raw_text: str) -> Optional[Dict[str, Any]]:
        """Bóc tách JSON từ phản hồi thô của LLM."""
        try:
            # Tìm khối JSON giữa dấu ngoặc nhọn
            match = re.search(r"\{.*\}", raw_text, re.DOTALL)
            if match:
                return json.loads(match.group(0))
        except Exception:
            pass
        return None

    def _heuristic_classify(
        self,
        query: str,
        ticker: Optional[str] = None,
        fiscal_years: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """Phân loại dựa trên tập quy tắc từ khóa (Heuristic Rule-Based)."""
        q_lower = query.lower()

        extracted_ticker = ticker or self._extract_ticker_regex(query) or "FPT"
        extracted_years = fiscal_years or self._extract_years_regex(query) or [2023]

        # 1. Valuation, Stock Price & Market Data (Định giá & Giá cổ phiếu thị trường)
        valuation_keywords = [
            "định giá", "valuation", "p/e", "p/b", "ev/ebitda", "dcf", "chiết khấu dòng tiền",
            "giá trị nội tại", "giá cổ phiếu", "thị giá", "khối lượng giao dịch", "thanh khoản",
            "thị trường", "phiên giao dịch", "cổ phiếu"
        ]
        if any(kw in q_lower for kw in valuation_keywords):
            return {
                "query_type": "valuation",
                "ticker": extracted_ticker,
                "fiscal_years": extracted_years,
                "confidence": 0.95,
            }

        # 2. Comprehensive Analysis (DuPont, Trend, Common-size, Sức khỏe)
        analysis_keywords = [
            "dupont", "du pont", "phân tích", "đánh giá", "sức khỏe tài chính",
            "khả năng sinh lời", "cơ cấu", "xu hướng", "trend", "common-size",
            "toàn diện", "so sánh", "hiệu quả", "vòng quay"
        ]
        if any(kw in q_lower for kw in analysis_keywords):
            return {
                "query_type": "analysis",
                "ticker": extracted_ticker,
                "fiscal_years": extracted_years,
                "confidence": 0.95,
            }

        # 3. Calculation & Arithmetic (Tính toán số liệu cụ thể)
        calculate_keywords = [
            "tính", "tính toán", "doanh thu", "lợi nhuận", "tổng tài sản",
            "vốn chủ", "nợ", "roe", "roa", "biên lợi nhuận", "lãi",
            "bao nhiêu", "calculate", "tăng trưởng", "tỷ suất"
        ]
        if any(kw in q_lower for kw in calculate_keywords):
            return {
                "query_type": "calculate",
                "ticker": extracted_ticker,
                "fiscal_years": extracted_years,
                "confidence": 0.90,
            }

        # 4. Simple qualitative search (Chiến lược, đối tác, lãnh đạo, văn bản)
        return {
            "query_type": "simple",
            "ticker": extracted_ticker,
            "fiscal_years": extracted_years,
            "confidence": 0.85,
        }

    def _extract_ticker_regex(self, text: str) -> Optional[str]:
        """Trích xuất mã chứng khoán từ tên công ty tiếng Việt hoặc mã viết hoa."""
        # 1. Tra cứu tên thương hiệu tiếng Việt phổ biến
        name_map = {
            "hòa phát": "HPG", "hoa phat": "HPG",
            "vinamilk": "VNM", "sữa việt nam": "VNM",
            "fpt": "FPT",
            "masan": "MSN", "ma san": "MSN",
            "vingroup": "VIC", "vin group": "VIC",
            "vinhomes": "VHM",
            "vincom": "VRE",
            "thế giới di động": "MWG", "the gioi di dong": "MWG", "bách hóa xanh": "MWG",
            "viettel": "CTR", "viettel post": "VTP",
            "techcombank": "TCB", "techcom": "TCB",
            "vietcombank": "VCB", "vietcom": "VCB",
            "vietinbank": "CTG", "vietin": "CTG",
            "bidv": "BID",
            "vpbank": "VPB", "vp bank": "VPB", "việt nam thịnh vượng": "VPB",
            "mbbank": "MBB", "mb bank": "MBB", "quân đội": "MBB",
            "acb": "ACB", "á châu": "ACB",
            "hdbank": "HDB", "hd bank": "HDB",
            "sacombank": "STB",
            "tpbank": "TPB", "tp bank": "TPB", "tiên phong": "TPB",
            "sabeco": "SAB", "bia sài gòn": "SAB",
            "gas": "GAS", "khí việt nam": "GAS",
            "petrolimex": "PLX",
        }
        text_lower = text.lower()
        for name, tk in name_map.items():
            if name in text_lower:
                return tk

        # 2. Tìm mã viết hoa trong câu hỏi
        words = re.findall(r"\b[A-Z]{3,4}\b", text)
        for w in words:
            if w in _COMMON_TICKERS:
                return w
        # Nếu có từ viết hoa 3 chữ cái bất kỳ
        if words:
            return words[0]
        return None

    def _extract_years_regex(self, text: str) -> List[int]:
        """Trích xuất các năm 20xx trong câu hỏi."""
        years = re.findall(r"\b(20\d{2})\b", text)
        if years:
            return sorted(list(set(int(y) for y in years)))
        return []
