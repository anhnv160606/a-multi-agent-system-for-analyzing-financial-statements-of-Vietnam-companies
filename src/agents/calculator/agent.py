"""Calculator Agent: Program of Thought Financial Code Generation & Execution (Task 3.7).

Pipeline position:
    RetrieverAgent → **CalculatorAgent** → AnalysisAgent → ModelingAgent → SynthesisAgent

Receives:
    state["query"]              — User's natural language financial query
    state["company_ticker"]     — Target stock ticker (e.g. "FPT")
    state["fiscal_years"]       — Optional list of fiscal years (e.g. [2023, 2024])
    state["fiscal_quarter"]     — Optional fiscal quarter (e.g. 1, 2, 3, 4, or 0)
    state["table_data"]         — Extracted/retrieved table data (optional)
    state["sql_data"]           — Queried SQL financial data records (optional)

Produces:
    state["calculator_results"] — Structured dictionary of calculated financial metrics
    state["confidence_score"]   — Reliability score [0.0, 1.0]
    state["provenance"]         — Provenance & audit trail records
    state["errors"]             — Recorded errors, if any
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from src.agents.base_agent import BaseAgent, track_tokens
from src.agents.calculator.sandbox import PythonSandbox, SandboxResult
from src.agents.calculator.sql_agent import SQLAgent
from src.agents.calculator.validator import CalculationValidator, ValidationResult
from src.utils.llm_client import get_default_llm
from src.utils.logger import get_logger

logger = get_logger("src.agents.calculator.agent")


_SENTINEL = object()


class CalculatorAgent(BaseAgent):
    """Program of Thought (PoT) agent for deterministic, zero-hallucination financial math."""

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        llm: Any = _SENTINEL,
        prompt_template: str = "calculator",
        sandbox: Optional[PythonSandbox] = None,
        validator: Optional[CalculationValidator] = None,
        sql_agent: Optional[SQLAgent] = None,
    ):
        resolved_llm = get_default_llm("calculator") if llm is _SENTINEL else llm
        super().__init__(
            config=config,
            llm=resolved_llm,
            prompt_template=prompt_template,
        )
        self.sandbox = sandbox or PythonSandbox(
            timeout_seconds=float(self.config.get("sandbox_timeout", 5.0))
        )
        self.validator = validator or CalculationValidator(
            tolerance_ratio=float(self.config.get("validation_tolerance", 0.005))
        )
        self.sql_agent = sql_agent or SQLAgent(config=config, llm=llm)

    def extract_code_from_text(self, text: str) -> str:
        """Extracts Python code block from LLM response."""
        code_match = re.search(r"```(?:python)?\s*([\s\S]*?)```", text, re.IGNORECASE)
        if code_match:
            return code_match.group(1).strip()
        return text.strip()

    def format_prompt(self, query: str, ticker: str, context: str) -> str:
        """Renders the user prompt from the loaded YAML template."""
        user_tmpl = self.prompt_template.get("user_template", "")
        return user_tmpl.format(
            query=query,
            ticker=ticker,
            context=context,
        )

    @track_tokens
    def generate_code(
        self,
        query: str,
        ticker: str,
        context_data: Any,
    ) -> str:
        """Generates Python calculation code via LLM or rule-based fallback."""
        context_str = json.dumps(context_data, ensure_ascii=False, indent=2) if isinstance(context_data, (dict, list)) else str(context_data)

        if self.llm is not None:
            try:
                formatted_prompt = self.format_prompt(
                    query=query,
                    ticker=ticker,
                    context=context_str,
                )
                response = self.llm.invoke(formatted_prompt)
                raw_text = response.content if hasattr(response, "content") else str(response)
                return self.extract_code_from_text(raw_text)
            except Exception as e:
                logger.warning(f"LLM Python code generation error ({e}). Falling back to deterministic code engine.")

        # Offline heuristic fallback
        return self._generate_heuristic_code(query, context_data)

    def _generate_heuristic_code(self, query: str, context_data: Any) -> str:
        """Generates deterministic Python calculation code for common financial queries."""
        return f"""
# Dữ liệu đầu vào từ SQL
raw_records = {repr(context_data)}

# Trích xuất số liệu cơ bản
revenue = 0.0
gross_profit = 0.0
net_income = 0.0
total_assets = 0.0
equity = 0.0
total_liabilities = 0.0

if isinstance(raw_records, list):
    for r in raw_records:
        item = str(r.get("line_item", "")).strip()
        val = float(r.get("value", 0.0) or 0.0)
        item_lower = item.lower()

        if item == "Doanh số thuần" or (revenue == 0 and "doanh số" in item_lower):
            revenue = val
        elif item == "Lãi gộp" or "lợi nhuận gộp" in item_lower:
            gross_profit = val
        elif item in ("Lãi/(lỗ) thuần sau thuế", "Lợi nhuận của Cổ đông của Công ty mẹ") or ("sau thuế" in item_lower and net_income == 0):
            net_income = val
        elif item == "TỔNG TÀI SẢN" or "tổng tài sản" in item_lower:
            total_assets = val
        elif item == "VỐN CHỦ SỞ HỮU" or "vốn chủ sở hữu" in item_lower:
            equity = val
        elif item in ("NỢ PHẢI TRẢ", "Nợ ngắn hạn") or "nợ phải trả" in item_lower:
            total_liabilities = val

if total_liabilities == 0 and total_assets > 0 and equity > 0:
    total_liabilities = total_assets - equity

# Tính toán các chỉ số
computed_roe = roe(net_income, equity) if equity > 0 else 0.0
computed_roa = roa(net_income, total_assets) if total_assets > 0 else 0.0
computed_net_margin = net_margin(net_income, revenue) if revenue > 0 else 0.0
computed_gross_margin = gross_margin(gross_profit, revenue) if revenue > 0 else 0.0
dupont_info = dupont_3step(net_income, revenue, total_assets, equity) if (revenue > 0 and total_assets > 0 and equity > 0) else {{}}

result = {{
    "revenue": revenue,
    "gross_profit": gross_profit,
    "net_income": net_income,
    "total_assets": total_assets,
    "equity": equity,
    "total_liabilities": total_liabilities,
    "roe": computed_roe,
    "roa": computed_roa,
    "net_margin": computed_net_margin,
    "gross_margin": computed_gross_margin,
    "dupont": dupont_info,
}}
"""

    def compute(
        self,
        query: str,
        ticker: str,
        data: Any,
    ) -> Dict[str, Any]:
        """
        Full PoT computation pipeline: Code Generation -> Sandbox Execution -> Validation.
        """
        code = self.generate_code(query=query, ticker=ticker, context_data=data)
        sandbox_res: SandboxResult = self.sandbox.execute(code, context={"data": data})

        if not sandbox_res.success:
            logger.error(f"Calculator sandbox error: {sandbox_res.error}")
            return {
                "success": False,
                "error": sandbox_res.error,
                "code": code,
                "metrics": {},
                "validation": None,
            }

        computed_metrics = sandbox_res.result if isinstance(sandbox_res.result, dict) else {"result": sandbox_res.result}

        # Validate results
        validation_res = self.validator.validate_financial_ratios(computed_metrics)

        return {
            "success": True,
            "metrics": computed_metrics,
            "validation": validation_res.model_dump(),
            "execution_time_ms": sandbox_res.execution_time_ms,
            "code": code,
        }

    def invoke(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main execution workflow compliant with Multi-Agent state orchestration.
        """
        query = state.get("query", "")
        ticker = state.get("company_ticker", "FPT")
        years = state.get("fiscal_years")
        quarter = state.get("fiscal_quarter")

        # 1. Fetch data from SQL if not already present
        sql_data = state.get("sql_data") or state.get("table_data")
        if not sql_data:
            logger.info("CalculatorAgent: No table data in state, invoking SQLAgent...")
            state = self.sql_agent.invoke(state)
            sql_data = state.get("sql_data", [])

        # 2. Run computation
        calc_output = self.compute(query=query, ticker=ticker, data=sql_data)

        # 3. Update State
        state["calculator_results"] = calc_output.get("metrics", {})
        state["calculator_raw"] = calc_output
        state["confidence_score"] = 0.95 if calc_output["success"] else 0.4

        # Provenance tracking
        state.setdefault("provenance", []).append({
            "agent": "CalculatorAgent",
            "sql_records_used": len(sql_data) if isinstance(sql_data, list) else 1,
            "execution_time_ms": calc_output.get("execution_time_ms", 0.0),
            "valid": calc_output.get("validation", {}).get("is_valid", True) if calc_output.get("validation") else True,
        })

        if not calc_output["success"]:
            state.setdefault("errors", []).append(f"Calculator error: {calc_output.get('error')}")

        return state
