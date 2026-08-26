"""Analysis agent: thực hiện các framework phân tích tài chính chuẩn.

Pipeline vị trí:
    RetrieverAgent → CalculatorAgent → **AnalysisAgent** → ModelingAgent → SynthesisAgent

Nhận:
    state["retrieved_chunks"]    — chunks văn bản từ Vector DB
    state["table_data"]          — bảng số liệu từ MySQL / table chunks
    state["query"]               — câu hỏi gốc từ người dùng
    state["company_ticker"]      — mã chứng khoán (ví dụ: "VNM")
    state["fiscal_years"]        — danh sách năm tài chính (ví dụ: [2021, 2022, 2023])
    state["calculator_results"]  — kết quả từ CalculatorAgent (tuỳ chọn)
    state["peer_data"]           — dữ liệu công ty cùng ngành (tuỳ chọn)

Ghi:
    state["analysis_results"]    — kết quả phân tích dạng structured JSON
    state["confidence_score"]    — điểm tin cậy tổng thể [0.0, 1.0]
    state["provenance"]          — danh sách nguồn truy vết bổ sung
    state["errors"]              — danh sách lỗi nếu có
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, MutableMapping
from typing import Any

from src.agents.base_agent import BaseAgent, track_tokens


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

FinancialData = dict[str, Any]
AnalysisResult = dict[str, Any]

# Tên các chỉ tiêu tài chính thường gặp trong BCTC Việt Nam
_INCOME_KEYWORDS: tuple[str, ...] = (
    "doanh thu",
    "revenue",
    "net revenue",
    "doanh thu thuần",
    "lợi nhuận gộp",
    "gross profit",
    "lợi nhuận thuần",
    "lợi nhuận sau thuế",
    "net income",
    "net profit",
    "ebit",
    "ebitda",
    "chi phí",
    "cost",
    "expense",
    "lãi vay",
    "interest",
    "thuế",
    "tax",
)
_BALANCE_KEYWORDS: tuple[str, ...] = (
    "tổng tài sản",
    "total assets",
    "tài sản",
    "asset",
    "vốn chủ sở hữu",
    "equity",
    "nợ",
    "liability",
    "debt",
    "tiền",
    "cash",
    "hàng tồn kho",
    "inventory",
    "phải thu",
    "receivable",
)
_CASHFLOW_KEYWORDS: tuple[str, ...] = (
    "lưu chuyển tiền",
    "cash flow",
    "operating",
    "investing",
    "financing",
)


class AnalysisAgent(BaseAgent):
    """Thực hiện phân tích tài chính theo các framework chuẩn.

    Các phân tích được hỗ trợ:
    - DuPont Analysis (3 bước và 5 bước)
    - Trend Analysis (xu hướng qua các năm + CAGR)
    - Common-size Analysis (phân tích tỷ trọng)
    - Peer Comparison (so sánh cùng ngành)
    """

    def __init__(
        self,
        config: Mapping[str, Any] | None,
        llm: Any,
        prompt_template: str | Mapping[str, Any] = "analysis",
    ) -> None:
        super().__init__(config=config, llm=llm, prompt_template=prompt_template)
        # Ngưỡng dữ liệu tối thiểu để chạy phân tích có ý nghĩa
        self._min_data_fields = int(self.config.get("min_data_fields", 3))
        # Số năm tối thiểu để tính trend analysis
        self._min_years_for_trend = int(self.config.get("min_years_for_trend", 2))

    # -----------------------------------------------------------------------
    # Public entrypoint
    # -----------------------------------------------------------------------

    def invoke(self, state: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
        """Entrypoint chính của AnalysisAgent.

        Orchestrate toàn bộ quy trình:
        1. Validate dữ liệu đầu vào
        2. Parse dữ liệu tài chính từ state
        3. Chạy 4 frameworks phân tích
        4. Tổng hợp kết quả → state["analysis_results"]
        5. Cập nhật confidence, provenance, log
        """
        query = str(state.get("query") or "").strip()
        ticker = str(state.get("company_ticker") or "").strip().upper()
        fiscal_years: list[int] = state.get("fiscal_years") or []

        # --- Validate đầu vào ---
        has_chunks = bool(state.get("retrieved_chunks"))
        has_tables = bool(state.get("table_data"))
        has_calculator = bool(state.get("calculator_results"))

        if not has_chunks and not has_tables and not has_calculator:
            self._append_error(
                state,
                "AnalysisAgent: không có dữ liệu tài chính nào trong state "
                "(retrieved_chunks, table_data hoặc calculator_results đều rỗng).",
            )
            return state

        # --- Parse dữ liệu tài chính ---
        financial_data = self._parse_financial_data(state)

        # --- Chạy các frameworks phân tích ---
        analysis_results: AnalysisResult = {
            "ticker": ticker,
            "fiscal_years": fiscal_years,
            "query": query,
            "dupont": {},
            "trend": {},
            "common_size": {},
            "peer_comparison": {},
            "data_gaps": [],
        }

        # DuPont Analysis
        dupont_result = self.dupont_analysis(financial_data)
        analysis_results["dupont"] = dupont_result

        # Trend Analysis — chỉ chạy nếu đủ số năm
        if len(fiscal_years) >= self._min_years_for_trend or len(
            financial_data.get("income_statement", {})
        ) >= self._min_years_for_trend:
            trend_result = self.trend_analysis(financial_data)
            analysis_results["trend"] = trend_result
        else:
            analysis_results["trend"] = {
                "skipped": True,
                "reason": f"Cần ít nhất {self._min_years_for_trend} năm để phân tích xu hướng.",
            }

        # Common-size Analysis
        common_size_result = self.common_size_analysis(financial_data)
        analysis_results["common_size"] = common_size_result

        # Peer Comparison — chỉ chạy khi có peer_data hoặc LLM có thể nhận xét định tính
        peer_data = state.get("peer_data")
        peer_result = self.peer_comparison(
            company_data=financial_data,
            peer_data=peer_data,
        )
        analysis_results["peer_comparison"] = peer_result

        # Gom tất cả data_gaps
        all_gaps: list[str] = []
        for key in ("dupont", "trend", "common_size", "peer_comparison"):
            section = analysis_results.get(key, {})
            if isinstance(section, dict):
                all_gaps.extend(section.pop("data_gaps", []))
        analysis_results["data_gaps"] = list(dict.fromkeys(all_gaps))  # deduplicate

        # --- Confidence ---
        confidence = self._estimate_confidence(financial_data, analysis_results)
        analysis_results["confidence"] = confidence

        # --- Ghi state ---
        state["analysis_results"] = analysis_results
        state["confidence_score"] = confidence

        # Provenance
        provenance_entry = {
            "agent": self.__class__.__name__,
            "ticker": ticker,
            "fiscal_years": fiscal_years,
            "analyses_run": [
                k
                for k in ("dupont", "trend", "common_size", "peer_comparison")
                if analysis_results.get(k) and not analysis_results[k].get("skipped")
            ],
            "data_gaps": analysis_results["data_gaps"],
            "confidence": confidence,
        }
        state.setdefault("provenance", [])
        if isinstance(state["provenance"], list):
            state["provenance"].append(provenance_entry)

        # Log
        self._log_step(
            input={
                "query": query,
                "ticker": ticker,
                "fiscal_years": fiscal_years,
                "has_chunks": has_chunks,
                "has_tables": has_tables,
            },
            output={
                "run_id": state.get("run_id"),
                "trace_id": state.get("trace_id"),
                "ticker": ticker,
                "analyses_run": provenance_entry["analyses_run"],
                "data_gaps_count": len(analysis_results["data_gaps"]),
            },
            confidence=confidence,
        )
        return state

    # -----------------------------------------------------------------------
    # Core analysis methods
    # -----------------------------------------------------------------------

    def dupont_analysis(self, data: FinancialData) -> AnalysisResult:
        """Phân tích DuPont 3 bước và 5 bước.

        DuPont 3-step:
            ROE = Net Profit Margin × Asset Turnover × Equity Multiplier
                = (Net Income / Revenue) × (Revenue / Total Assets) × (Total Assets / Equity)

        DuPont 5-step:
            ROE = Tax Burden × Interest Burden × EBIT Margin × Asset Turnover × Equity Multiplier
        """
        income = data.get("income_statement", {})
        balance = data.get("balance_sheet", {})
        gaps: list[str] = []

        result: AnalysisResult = {
            "dupont_3step": {},
            "dupont_5step": {},
            "interpretation": "",
            "data_gaps": [],
        }

        # Tìm tất cả các năm có dữ liệu
        years = sorted(set(income.keys()) | set(balance.keys()))
        if not years:
            gaps.append("income_statement và balance_sheet đều rỗng")
            result["data_gaps"] = gaps
            result["interpretation"] = "Không đủ dữ liệu để thực hiện phân tích DuPont."
            return result

        for year in years:
            inc = income.get(year, {})
            bal = balance.get(year, {})

            net_income = _get_metric(inc, ("net_income", "lợi nhuận sau thuế", "profit_after_tax"))
            revenue = _get_metric(inc, ("revenue", "net_revenue", "doanh thu thuần", "doanh_thu_thuan"))
            total_assets = _get_metric(bal, ("total_assets", "tổng tài sản", "tong_tai_san"))
            equity = _get_metric(bal, ("equity", "vốn chủ sở hữu", "von_chu_so_huu", "shareholders_equity"))
            ebit = _get_metric(inc, ("ebit", "lợi nhuận từ hoạt động kinh doanh"))
            interest_expense = _get_metric(inc, ("interest_expense", "lãi vay", "chi phí lãi vay"))
            tax_expense = _get_metric(inc, ("tax_expense", "thuế tndn", "income_tax", "chi phí thuế"))
            ebt = _get_metric(inc, ("ebt", "lợi nhuận trước thuế", "profit_before_tax"))

            # --- DuPont 3 bước ---
            d3: dict[str, Any] = {}
            if _all_valid(net_income, revenue):
                d3["net_profit_margin"] = round(net_income / revenue, 6) if revenue != 0 else None  # type: ignore[operator]
            else:
                d3["net_profit_margin"] = None
                gaps.append(f"[{year}] thiếu net_income hoặc revenue để tính net_profit_margin")

            if _all_valid(revenue, total_assets):
                d3["asset_turnover"] = round(revenue / total_assets, 6) if total_assets != 0 else None  # type: ignore[operator]
            else:
                d3["asset_turnover"] = None
                gaps.append(f"[{year}] thiếu revenue hoặc total_assets để tính asset_turnover")

            if _all_valid(total_assets, equity):
                d3["equity_multiplier"] = round(total_assets / equity, 6) if equity != 0 else None  # type: ignore[operator]
            else:
                d3["equity_multiplier"] = None
                gaps.append(f"[{year}] thiếu total_assets hoặc equity để tính equity_multiplier")

            if _all_valid(d3["net_profit_margin"], d3["asset_turnover"], d3["equity_multiplier"]):
                d3["roe"] = round(
                    d3["net_profit_margin"] * d3["asset_turnover"] * d3["equity_multiplier"], 6
                )
            else:
                d3["roe"] = None

            result["dupont_3step"][year] = d3

            # --- DuPont 5 bước ---
            d5: dict[str, Any] = {}

            # Tax Burden = Net Income / EBT
            if ebt is None and _all_valid(net_income, tax_expense):
                ebt = net_income + tax_expense  # type: ignore[operator]

            if _all_valid(net_income, ebt) and ebt != 0:
                d5["tax_burden"] = round(net_income / ebt, 6)  # type: ignore[operator]
            else:
                d5["tax_burden"] = None
                gaps.append(f"[{year}] thiếu net_income hoặc ebt để tính tax_burden")

            # Interest Burden = EBT / EBIT
            if ebit is None and _all_valid(ebt, interest_expense):
                ebit = ebt + interest_expense  # type: ignore[operator]

            if _all_valid(ebt, ebit) and ebit != 0:
                d5["interest_burden"] = round(ebt / ebit, 6)  # type: ignore[operator]
            else:
                d5["interest_burden"] = None
                gaps.append(f"[{year}] thiếu ebt hoặc ebit để tính interest_burden")

            # EBIT Margin = EBIT / Revenue
            if _all_valid(ebit, revenue) and revenue != 0:
                d5["ebit_margin"] = round(ebit / revenue, 6)  # type: ignore[operator]
            else:
                d5["ebit_margin"] = None

            d5["asset_turnover"] = d3.get("asset_turnover")
            d5["equity_multiplier"] = d3.get("equity_multiplier")

            components = [
                d5["tax_burden"],
                d5["interest_burden"],
                d5["ebit_margin"],
                d5["asset_turnover"],
                d5["equity_multiplier"],
            ]
            if _all_valid(*components):
                d5["roe"] = round(
                    d5["tax_burden"]
                    * d5["interest_burden"]
                    * d5["ebit_margin"]
                    * d5["asset_turnover"]
                    * d5["equity_multiplier"],
                    6,
                )
            else:
                d5["roe"] = None

            result["dupont_5step"][year] = d5

        # --- Interpretation từ LLM ---
        interpretation = self._get_llm_interpretation(
            financial_data=data,
            analysis_type="DuPont Analysis (3-step & 5-step)",
            computed_result=result,
        )
        result["interpretation"] = interpretation
        result["data_gaps"] = list(dict.fromkeys(gaps))
        return result

    def trend_analysis(self, data: FinancialData) -> AnalysisResult:
        """Phân tích xu hướng qua các năm: YoY growth, CAGR, margin trends.

        Các chỉ số theo dõi:
        - Revenue growth (YoY%)
        - Gross margin, EBIT margin, Net margin
        - ROE, ROA trends
        - Debt/Equity ratio trend
        - Operating cash flow trend
        """
        income = data.get("income_statement", {})
        balance = data.get("balance_sheet", {})
        cash_flow = data.get("cash_flow", {})
        gaps: list[str] = []

        years = sorted(set(income.keys()) | set(balance.keys()))
        result: AnalysisResult = {
            "years_covered": years,
            "metrics": {},
            "cagr": {},
            "trend_direction": {},
            "interpretation": "",
            "data_gaps": [],
        }

        if len(years) < 2:
            gaps.append("Cần ít nhất 2 năm dữ liệu để phân tích xu hướng")
            result["data_gaps"] = gaps
            result["interpretation"] = "Không đủ dữ liệu đa năm để phân tích xu hướng."
            return result

        # --- Thu thập time series cho từng chỉ số ---
        metrics_ts: dict[str, dict[int, float | None]] = {
            "revenue": {},
            "gross_profit": {},
            "net_income": {},
            "ebit": {},
            "total_assets": {},
            "equity": {},
            "total_debt": {},
            "operating_cash_flow": {},
        }

        for year in years:
            inc = income.get(year, {})
            bal = balance.get(year, {})
            cf = cash_flow.get(year, {})

            metrics_ts["revenue"][year] = _get_metric(
                inc, ("revenue", "net_revenue", "doanh thu thuần", "doanh_thu_thuan")
            )
            metrics_ts["gross_profit"][year] = _get_metric(
                inc, ("gross_profit", "lợi nhuận gộp")
            )
            metrics_ts["net_income"][year] = _get_metric(
                inc, ("net_income", "lợi nhuận sau thuế", "profit_after_tax")
            )
            metrics_ts["ebit"][year] = _get_metric(inc, ("ebit",))
            metrics_ts["total_assets"][year] = _get_metric(
                bal, ("total_assets", "tổng tài sản", "tong_tai_san")
            )
            metrics_ts["equity"][year] = _get_metric(
                bal, ("equity", "vốn chủ sở hữu", "von_chu_so_huu")
            )
            metrics_ts["total_debt"][year] = _get_metric(
                bal, ("total_debt", "tổng nợ", "total_liabilities", "nợ phải trả")
            )
            metrics_ts["operating_cash_flow"][year] = _get_metric(
                cf, ("operating_cash_flow", "tiền từ hoạt động kinh doanh", "cfo")
            )

        # --- YoY Growth ---
        yoy: dict[str, dict[int, float | None]] = {}
        for metric, ts in metrics_ts.items():
            yoy[metric] = {}
            sorted_years = sorted(ts.keys())
            for i in range(1, len(sorted_years)):
                y_curr = sorted_years[i]
                y_prev = sorted_years[i - 1]
                v_curr = ts.get(y_curr)
                v_prev = ts.get(y_prev)
                if _all_valid(v_curr, v_prev) and v_prev != 0:
                    yoy[metric][y_curr] = round((v_curr - v_prev) / abs(v_prev), 6)  # type: ignore[operator]
                else:
                    yoy[metric][y_curr] = None
        result["metrics"]["yoy_growth"] = yoy

        # --- Margin Ratios ---
        margins: dict[str, dict[int, float | None]] = {
            "gross_margin": {},
            "ebit_margin": {},
            "net_margin": {},
            "roe": {},
            "roa": {},
            "debt_to_equity": {},
        }
        for year in years:
            rev = metrics_ts["revenue"].get(year)
            gp = metrics_ts["gross_profit"].get(year)
            ebit = metrics_ts["ebit"].get(year)
            ni = metrics_ts["net_income"].get(year)
            ta = metrics_ts["total_assets"].get(year)
            eq = metrics_ts["equity"].get(year)
            td = metrics_ts["total_debt"].get(year)

            margins["gross_margin"][year] = round(gp / rev, 6) if _all_valid(gp, rev) and rev != 0 else None  # type: ignore[operator]
            margins["ebit_margin"][year] = round(ebit / rev, 6) if _all_valid(ebit, rev) and rev != 0 else None  # type: ignore[operator]
            margins["net_margin"][year] = round(ni / rev, 6) if _all_valid(ni, rev) and rev != 0 else None  # type: ignore[operator]
            margins["roe"][year] = round(ni / eq, 6) if _all_valid(ni, eq) and eq != 0 else None  # type: ignore[operator]
            margins["roa"][year] = round(ni / ta, 6) if _all_valid(ni, ta) and ta != 0 else None  # type: ignore[operator]
            margins["debt_to_equity"][year] = round(td / eq, 6) if _all_valid(td, eq) and eq != 0 else None  # type: ignore[operator]

        result["metrics"]["margins"] = margins

        # --- CAGR ---
        first_year = years[0]
        last_year = years[-1]
        n_years = last_year - first_year
        if n_years > 0:
            for metric in ("revenue", "net_income", "total_assets", "equity"):
                v_start = metrics_ts[metric].get(first_year)
                v_end = metrics_ts[metric].get(last_year)
                if _all_valid(v_start, v_end) and v_start > 0 and v_end > 0:  # type: ignore[operator]
                    cagr = (v_end / v_start) ** (1 / n_years) - 1  # type: ignore[operator]
                    result["cagr"][metric] = round(cagr, 6)
                else:
                    result["cagr"][metric] = None
                    gaps.append(f"Không đủ dữ liệu tính CAGR {metric} ({first_year}–{last_year})")

        # --- Trend direction (simple heuristic) ---
        for margin_name, margin_ts in margins.items():
            valid_vals = [v for v in margin_ts.values() if v is not None]
            if len(valid_vals) >= 2:
                direction = _assess_trend(valid_vals)
                result["trend_direction"][margin_name] = direction

        # --- Interpretation từ LLM ---
        result["interpretation"] = self._get_llm_interpretation(
            financial_data=data,
            analysis_type="Trend Analysis (YoY growth, CAGR, margin trends)",
            computed_result=result,
        )
        result["data_gaps"] = list(dict.fromkeys(gaps))
        return result

    def common_size_analysis(self, data: FinancialData) -> AnalysisResult:
        """Phân tích tỷ trọng (Common-size).

        - Income Statement: mỗi chỉ tiêu / Doanh thu thuần (%)
        - Balance Sheet: mỗi chỉ tiêu / Tổng tài sản (%)
        """
        income = data.get("income_statement", {})
        balance = data.get("balance_sheet", {})
        gaps: list[str] = []

        result: AnalysisResult = {
            "income_statement": {},
            "balance_sheet": {},
            "interpretation": "",
            "data_gaps": [],
        }

        years = sorted(set(income.keys()) | set(balance.keys()))
        if not years:
            result["data_gaps"] = ["Không có dữ liệu income_statement và balance_sheet"]
            result["interpretation"] = "Không đủ dữ liệu để thực hiện Common-size Analysis."
            return result

        # --- Income Statement Common-size ---
        for year in years:
            inc = income.get(year, {})
            base = _get_metric(inc, ("revenue", "net_revenue", "doanh thu thuần", "doanh_thu_thuan"))
            if base is None or base == 0:
                gaps.append(f"[{year}] thiếu revenue để tính common-size income statement")
                result["income_statement"][year] = {"base_missing": True}
                continue

            year_cs: dict[str, Any] = {"base_revenue": base}
            for field, value in inc.items():
                if isinstance(value, (int, float)) and value is not None:
                    year_cs[f"{field}_pct"] = round(value / base, 6)
            result["income_statement"][year] = year_cs

        # --- Balance Sheet Common-size ---
        for year in years:
            bal = balance.get(year, {})
            base = _get_metric(bal, ("total_assets", "tổng tài sản", "tong_tai_san"))
            if base is None or base == 0:
                gaps.append(f"[{year}] thiếu total_assets để tính common-size balance sheet")
                result["balance_sheet"][year] = {"base_missing": True}
                continue

            year_cs_bal: dict[str, Any] = {"base_total_assets": base}
            for field, value in bal.items():
                if isinstance(value, (int, float)) and value is not None:
                    year_cs_bal[f"{field}_pct"] = round(value / base, 6)
            result["balance_sheet"][year] = year_cs_bal

        # --- Interpretation từ LLM ---
        result["interpretation"] = self._get_llm_interpretation(
            financial_data=data,
            analysis_type="Common-size Analysis (Income Statement & Balance Sheet)",
            computed_result=result,
        )
        result["data_gaps"] = list(dict.fromkeys(gaps))
        return result

    def peer_comparison(
        self,
        company_data: FinancialData,
        peer_data: list[dict[str, Any]] | None = None,
    ) -> AnalysisResult:
        """So sánh chỉ số tài chính với công ty cùng ngành.

        Nếu peer_data được cung cấp → tính % deviation from peer average.
        Nếu không có peer_data → dùng LLM nhận xét định tính.
        """
        income = company_data.get("income_statement", {})
        balance = company_data.get("balance_sheet", {})
        gaps: list[str] = []

        result: AnalysisResult = {
            "has_peer_data": bool(peer_data),
            "company_metrics": {},
            "comparison_table": [],
            "company_position": {},
            "interpretation": "",
            "data_gaps": [],
        }

        # --- Tính key metrics của công ty hiện tại ---
        all_years = sorted(set(income.keys()) | set(balance.keys()))
        if not all_years:
            gaps.append("Không có dữ liệu để tính metrics của công ty")
            result["data_gaps"] = gaps
            result["interpretation"] = "Không đủ dữ liệu để thực hiện Peer Comparison."
            return result

        # Dùng năm gần nhất để so sánh
        latest_year = all_years[-1]
        inc = income.get(latest_year, {})
        bal = balance.get(latest_year, {})

        rev = _get_metric(inc, ("revenue", "net_revenue", "doanh thu thuần", "doanh_thu_thuan"))
        ni = _get_metric(inc, ("net_income", "lợi nhuận sau thuế", "profit_after_tax"))
        gp = _get_metric(inc, ("gross_profit", "lợi nhuận gộp"))
        ta = _get_metric(bal, ("total_assets", "tổng tài sản", "tong_tai_san"))
        eq = _get_metric(bal, ("equity", "vốn chủ sở hữu", "von_chu_so_huu"))
        td = _get_metric(bal, ("total_debt", "tổng nợ", "total_liabilities", "nợ phải trả"))

        company_kpis: dict[str, float | None] = {
            "gross_margin": round(gp / rev, 6) if _all_valid(gp, rev) and rev != 0 else None,  # type: ignore[operator]
            "net_margin": round(ni / rev, 6) if _all_valid(ni, rev) and rev != 0 else None,  # type: ignore[operator]
            "roe": round(ni / eq, 6) if _all_valid(ni, eq) and eq != 0 else None,  # type: ignore[operator]
            "roa": round(ni / ta, 6) if _all_valid(ni, ta) and ta != 0 else None,  # type: ignore[operator]
            "debt_to_equity": round(td / eq, 6) if _all_valid(td, eq) and eq != 0 else None,  # type: ignore[operator]
            "equity_ratio": round(eq / ta, 6) if _all_valid(eq, ta) and ta != 0 else None,  # type: ignore[operator]
        }
        result["company_metrics"] = {
            "year": latest_year,
            "kpis": company_kpis,
        }

        # --- Nếu có peer_data → tính quantitative comparison ---
        if peer_data:
            comparison_table: list[dict[str, Any]] = []
            peer_averages: dict[str, list[float]] = {k: [] for k in company_kpis}

            for peer in peer_data:
                peer_row: dict[str, Any] = {
                    "ticker": peer.get("ticker", "UNKNOWN"),
                    "year": peer.get("year", latest_year),
                }
                peer_inc = peer.get("income_statement", {})
                peer_bal = peer.get("balance_sheet", {})

                p_rev = _get_metric(peer_inc, ("revenue", "net_revenue", "doanh thu thuần"))
                p_ni = _get_metric(peer_inc, ("net_income", "lợi nhuận sau thuế"))
                p_gp = _get_metric(peer_inc, ("gross_profit", "lợi nhuận gộp"))
                p_ta = _get_metric(peer_bal, ("total_assets", "tổng tài sản"))
                p_eq = _get_metric(peer_bal, ("equity", "vốn chủ sở hữu"))
                p_td = _get_metric(peer_bal, ("total_debt", "tổng nợ", "total_liabilities"))

                peer_kpis: dict[str, float | None] = {
                    "gross_margin": round(p_gp / p_rev, 6) if _all_valid(p_gp, p_rev) and p_rev != 0 else None,  # type: ignore[operator]
                    "net_margin": round(p_ni / p_rev, 6) if _all_valid(p_ni, p_rev) and p_rev != 0 else None,  # type: ignore[operator]
                    "roe": round(p_ni / p_eq, 6) if _all_valid(p_ni, p_eq) and p_eq != 0 else None,  # type: ignore[operator]
                    "roa": round(p_ni / p_ta, 6) if _all_valid(p_ni, p_ta) and p_ta != 0 else None,  # type: ignore[operator]
                    "debt_to_equity": round(p_td / p_eq, 6) if _all_valid(p_td, p_eq) and p_eq != 0 else None,  # type: ignore[operator]
                    "equity_ratio": round(p_eq / p_ta, 6) if _all_valid(p_eq, p_ta) and p_ta != 0 else None,  # type: ignore[operator]
                }
                peer_row["kpis"] = peer_kpis
                comparison_table.append(peer_row)

                for kpi_name, kpi_val in peer_kpis.items():
                    if kpi_val is not None:
                        peer_averages[kpi_name].append(kpi_val)

            # Tính peer average và vị trí tương đối của công ty
            peer_avg: dict[str, float | None] = {}
            company_position: dict[str, str] = {}
            for kpi_name, vals in peer_averages.items():
                if vals:
                    avg = sum(vals) / len(vals)
                    peer_avg[kpi_name] = round(avg, 6)
                    company_val = company_kpis.get(kpi_name)
                    if company_val is not None:
                        # Với debt_to_equity thì thấp hơn là tốt hơn
                        if kpi_name == "debt_to_equity":
                            company_position[kpi_name] = (
                                "better" if company_val < avg else "worse"
                            )
                        else:
                            company_position[kpi_name] = (
                                "above_average" if company_val > avg else "below_average"
                            )
                    else:
                        company_position[kpi_name] = "data_unavailable"
                else:
                    peer_avg[kpi_name] = None

            result["comparison_table"] = comparison_table
            result["peer_average"] = peer_avg
            result["company_position"] = company_position

        else:
            # Không có peer_data → để LLM nhận xét định tính
            result["comparison_table"] = []
            result["company_position"] = {"note": "qualitative_only"}
            gaps.append("Không có peer_data — chỉ nhận xét định tính từ LLM")

        # --- Interpretation từ LLM ---
        result["interpretation"] = self._get_llm_interpretation(
            financial_data=company_data,
            analysis_type=f"Peer Comparison ({'quantitative' if peer_data else 'qualitative only — no peer data'})",
            computed_result=result,
        )
        result["data_gaps"] = list(dict.fromkeys(gaps))
        return result

    # -----------------------------------------------------------------------
    # Data parsing
    # -----------------------------------------------------------------------

    def _parse_financial_data(self, state: Mapping[str, Any]) -> FinancialData:
        """Parse chunks và table_data từ state thành structured financial dict.

        Returns:
            {
                "income_statement": {year: {metric: value, ...}, ...},
                "balance_sheet":    {year: {metric: value, ...}, ...},
                "cash_flow":        {year: {metric: value, ...}, ...},
                "metadata": {"ticker": ..., "years": [...], "sources": [...]}
            }
        """
        income: dict[int, dict[str, Any]] = {}
        balance: dict[int, dict[str, Any]] = {}
        cash_flow: dict[int, dict[str, Any]] = {}
        sources: list[str] = []

        ticker = str(state.get("company_ticker") or "").upper()
        fiscal_years: list[int] = state.get("fiscal_years") or []

        # --- 1. Ưu tiên dữ liệu từ CalculatorAgent (đã tính toán sẵn) ---
        calculator_results = state.get("calculator_results")
        if calculator_results and isinstance(calculator_results, dict):
            parsed = calculator_results.get("parsed_financial_data")
            if parsed and isinstance(parsed, dict):
                income.update(parsed.get("income_statement", {}))
                balance.update(parsed.get("balance_sheet", {}))
                cash_flow.update(parsed.get("cash_flow", {}))
                sources.append("calculator_results")

        # --- 2. Parse table_data (MySQL rows / table chunks) ---
        table_data: list[dict[str, Any]] = state.get("table_data") or []
        for record in table_data:
            if not isinstance(record, dict):
                continue

            # MySQL row format: {"source": "mysql", "row": {...}}
            if record.get("source") == "mysql":
                row = record.get("row", {})
                if not isinstance(row, dict):
                    continue
                self._merge_financial_row(
                    row=row,
                    income=income,
                    balance=balance,
                    cash_flow=cash_flow,
                )
                sources.append("mysql")

            # Vector store table chunk format: {"chunk_id": ..., "content": ..., "metadata": {...}}
            elif record.get("content"):
                parsed_chunk = self._parse_table_chunk(record)
                if parsed_chunk:
                    year = parsed_chunk.get("year")
                    report_type = parsed_chunk.get("report_type", "")
                    metrics = parsed_chunk.get("metrics", {})
                    if year and metrics:
                        target = _select_report_dict(report_type, income, balance, cash_flow)
                        target.setdefault(year, {}).update(metrics)
                    sources.append("vector_store_table")

        # --- 3. Parse retrieved_chunks (văn bản) qua LLM nếu cần ---
        retrieved_chunks: list[dict[str, Any]] = state.get("retrieved_chunks") or []
        # Chỉ gọi LLM để extract số liệu nếu chưa có đủ dữ liệu cấu trúc
        if not income and not balance and retrieved_chunks:
            extracted = self._extract_metrics_from_chunks(retrieved_chunks, fiscal_years)
            income.update(extracted.get("income_statement", {}))
            balance.update(extracted.get("balance_sheet", {}))
            cash_flow.update(extracted.get("cash_flow", {}))
            if extracted:
                sources.append("llm_extraction_from_chunks")

        # --- Normalise year keys thành int ---
        income = _normalize_year_keys(income)
        balance = _normalize_year_keys(balance)
        cash_flow = _normalize_year_keys(cash_flow)

        return {
            "income_statement": income,
            "balance_sheet": balance,
            "cash_flow": cash_flow,
            "metadata": {
                "ticker": ticker,
                "years": sorted(set(income.keys()) | set(balance.keys()) | set(cash_flow.keys())),
                "sources": list(dict.fromkeys(sources)),
            },
        }

    def _merge_financial_row(
        self,
        row: dict[str, Any],
        income: dict[int, dict[str, Any]],
        balance: dict[int, dict[str, Any]],
        cash_flow: dict[int, dict[str, Any]],
    ) -> None:
        """Merge một MySQL row vào các dict income/balance/cash_flow."""
        year_raw = row.get("fiscal_year") or row.get("year")
        try:
            year = int(year_raw)
        except (TypeError, ValueError):
            return

        report_type = str(row.get("report_type") or "").lower()
        line_item = str(row.get("line_item") or row.get("metric_name") or "").strip()
        value_raw = row.get("value") or row.get("amount")
        try:
            value = float(value_raw)
        except (TypeError, ValueError):
            return

        if not line_item:
            return

        target = _select_report_dict(report_type, income, balance, cash_flow)
        # Nếu chưa phân loại được → thử đoán theo keyword
        if target is income and not report_type:
            lower_item = line_item.lower()
            if any(kw in lower_item for kw in _BALANCE_KEYWORDS):
                target = balance
            elif any(kw in lower_item for kw in _CASHFLOW_KEYWORDS):
                target = cash_flow

        target.setdefault(year, {})[line_item] = value

    def _parse_table_chunk(self, chunk: dict[str, Any]) -> dict[str, Any] | None:
        """Cố gắng parse nội dung table chunk thành structured metrics.

        Table chunk có thể là Markdown table hoặc HTML. Trả về:
        {"year": int, "report_type": str, "metrics": dict}
        hoặc None nếu không parse được.
        """
        content = str(chunk.get("content") or "")
        metadata = chunk.get("metadata") or {}
        if not content:
            return None

        year_raw = metadata.get("year") or metadata.get("fiscal_year")
        try:
            year = int(year_raw)
        except (TypeError, ValueError):
            # Cố gắng tìm year trong content
            year_match = re.search(r"\b(20\d{2})\b", content)
            year = int(year_match.group(1)) if year_match else None

        report_type = str(metadata.get("report_type") or metadata.get("section") or "").lower()

        # Parse Markdown table rows đơn giản
        metrics: dict[str, float] = {}
        for line in content.split("\n"):
            line = line.strip()
            if not line or line.startswith("|---") or line.startswith("| ---"):
                continue
            if "|" in line:
                cells = [c.strip() for c in line.strip("|").split("|")]
                if len(cells) >= 2:
                    label = cells[0].strip()
                    for cell in cells[1:]:
                        # Lấy ô đầu tiên có thể parse thành số
                        val_str = re.sub(r"[,\s]", "", cell)
                        try:
                            val = float(val_str)
                            if label:
                                metrics[label] = val
                            break
                        except ValueError:
                            continue

        if not metrics:
            return None

        return {"year": year, "report_type": report_type, "metrics": metrics}

    def _extract_metrics_from_chunks(
        self,
        chunks: list[dict[str, Any]],
        fiscal_years: list[int],
    ) -> FinancialData:
        """Dùng LLM để trích xuất số liệu từ văn bản thuần khi không có dữ liệu bảng.

        Chỉ được gọi khi không có table_data cấu trúc.
        """
        if self.llm is None or not chunks:
            return {}

        context_text = "\n\n---\n\n".join(
            str(c.get("content") or "") for c in chunks[:5]  # Giới hạn 5 chunks để tiết kiệm token
        )
        years_str = ", ".join(str(y) for y in fiscal_years) if fiscal_years else "các năm trong dữ liệu"

        prompt = (
            f"Trích xuất số liệu tài chính từ nội dung sau cho các năm: {years_str}.\n"
            "Trả về JSON với cấu trúc:\n"
            '{"income_statement": {year: {"revenue": value, "net_income": value, ...}}, '
            '"balance_sheet": {year: {"total_assets": value, "equity": value, ...}}, '
            '"cash_flow": {year: {"operating_cash_flow": value, ...}}}\n'
            "Chỉ trả về JSON thuần, không có markdown fence.\n\n"
            f"Nội dung:\n{context_text}"
        )

        try:
            response = self._call_extraction_llm(prompt)
            text = self._extract_text_response(response)
            extracted = self._extract_json_from_response(text)
            # Normalise keys thành lowercase không dấu nếu cần
            return extracted if isinstance(extracted, dict) else {}
        except Exception as exc:
            self.logger.warning(
                "llm_extraction_failed",
                extra={"agent": self.__class__.__name__, "error": str(exc)},
            )
            return {}

    # -----------------------------------------------------------------------
    # LLM interaction helpers
    # -----------------------------------------------------------------------

    def _get_llm_interpretation(
        self,
        financial_data: FinancialData,
        analysis_type: str,
        computed_result: dict[str, Any],
    ) -> str:
        """Gọi LLM để sinh diễn giải ý nghĩa kinh tế của kết quả phân tích."""
        if self.llm is None:
            return "(LLM không khả dụng — diễn giải thủ công cần thiết)"

        query = financial_data.get("metadata", {}).get("query", "")
        ticker = financial_data.get("metadata", {}).get("ticker", "")

        # Tóm gọn computed_result để tránh prompt quá dài
        result_summary = json.dumps(
            _truncate_nested(computed_result, max_chars=1500),
            ensure_ascii=False,
            indent=2,
        )

        context = (
            f"Ticker: {ticker}\n"
            f"Loại phân tích: {analysis_type}\n"
            f"Kết quả tính toán:\n{result_summary}"
        )

        system_prompt = str(self.prompt_template.get("system_prompt", ""))
        user_template = str(self.prompt_template.get("user_template", ""))
        user_msg = user_template.format(
            query=query or "Phân tích tài chính doanh nghiệp",
            financial_data=context,
            analysis_type=analysis_type,
        )

        full_prompt = f"{system_prompt}\n\n{user_msg}"

        try:
            response = self._call_analysis_llm(full_prompt)
            text = self._extract_text_response(response).strip()
            # Nếu LLM trả về JSON thay vì text → extract interpretation field
            if text.startswith("{"):
                parsed = self._extract_json_from_response(text)
                if isinstance(parsed, dict):
                    return str(parsed.get("interpretation", text))
            return text
        except Exception as exc:
            self.logger.warning(
                "llm_interpretation_failed",
                extra={"agent": self.__class__.__name__, "analysis_type": analysis_type, "error": str(exc)},
            )
            return f"(Lỗi khi sinh diễn giải: {exc})"

    @track_tokens
    def _call_analysis_llm(self, prompt: str) -> Any:
        """Gọi LLM để sinh diễn giải phân tích. Decorated bởi @track_tokens."""
        return self._invoke_llm(prompt)

    @track_tokens
    def _call_extraction_llm(self, prompt: str) -> Any:
        """Gọi LLM để trích xuất số liệu từ văn bản. Decorated bởi @track_tokens."""
        return self._invoke_llm(prompt)

    def _invoke_llm(self, prompt: str) -> Any:
        """Adapter layer — hỗ trợ nhiều interface LLM khác nhau."""
        if hasattr(self.llm, "invoke"):
            return self.llm.invoke(prompt)
        if hasattr(self.llm, "generate_content"):
            return self.llm.generate_content(prompt)
        if callable(self.llm):
            return self.llm(prompt)
        raise ValueError(
            "Provided llm object does not expose a supported call interface "
            "(invoke / generate_content / callable)."
        )

    def _extract_text_response(self, response: Any) -> str:
        """Trích xuất text từ các response format phổ biến của LLM."""
        if response is None:
            return ""
        if isinstance(response, str):
            return response
        if isinstance(response, Mapping):
            return str(
                response.get("text")
                or response.get("content")
                or response.get("output")
                or ""
            )
        return str(
            getattr(response, "text", None)
            or getattr(response, "content", None)
            or response
        )

    def _extract_json_from_response(self, text: str) -> dict[str, Any]:
        """Extract JSON dict từ response text của LLM.

        Hỗ trợ các trường hợp:
        - JSON thuần
        - JSON trong markdown code fence (```json ... ```)
        - JSON lẫn lộn với text xung quanh
        """
        if not text:
            return {}

        # Strip markdown fence nếu có
        fence_match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
        if fence_match:
            text = fence_match.group(1)

        # Tìm JSON object đầu tiên trong text
        brace_match = re.search(r"\{[\s\S]*\}", text)
        if brace_match:
            text = brace_match.group(0)

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            self.logger.warning(
                "json_extraction_failed",
                extra={"agent": self.__class__.__name__, "text_preview": text[:200]},
            )
            return {}

    # -----------------------------------------------------------------------
    # Confidence & error helpers
    # -----------------------------------------------------------------------

    def _estimate_confidence(
        self,
        financial_data: FinancialData,
        analysis_results: AnalysisResult,
    ) -> float:
        """Ước tính điểm tin cậy tổng thể [0.0, 1.0].

        Dựa trên:
        - Số lượng metric có dữ liệu (không null)
        - Số năm có dữ liệu
        - Số data_gaps
        """
        score = 0.0
        total_weight = 0.0

        # --- Trọng số từ số năm có dữ liệu ---
        years = financial_data.get("metadata", {}).get("years", [])
        year_score = min(len(years) / 3.0, 1.0)  # Tối đa 3 năm → điểm tối đa
        score += year_score * 0.3
        total_weight += 0.3

        # --- Trọng số từ DuPont completeness ---
        dupont_data = analysis_results.get("dupont", {})
        dupont_3step = dupont_data.get("dupont_3step", {})
        roe_values = [v.get("roe") for v in dupont_3step.values() if isinstance(v, dict)]
        dupont_score = sum(1 for r in roe_values if r is not None) / max(len(roe_values), 1)
        score += dupont_score * 0.3
        total_weight += 0.3

        # --- Trọng số từ số data_gaps ---
        gaps = analysis_results.get("data_gaps", [])
        gap_penalty = min(len(gaps) * 0.05, 0.4)  # Tối đa giảm 0.4
        gap_score = max(0.0, 1.0 - gap_penalty)
        score += gap_score * 0.2
        total_weight += 0.2

        # --- Trọng số từ số nguồn dữ liệu ---
        sources = financial_data.get("metadata", {}).get("sources", [])
        source_score = min(len(sources) / 2.0, 1.0)  # 2+ nguồn → điểm tối đa
        score += source_score * 0.2
        total_weight += 0.2

        if total_weight == 0:
            return 0.0
        return round(max(0.0, min(1.0, score / total_weight)), 4)

    def _append_error(self, state: MutableMapping[str, Any], message: str) -> None:
        """Thêm error message vào state["errors"] và log ở mức ERROR."""
        state.setdefault("errors", [])
        if isinstance(state["errors"], list):
            state["errors"].append(message)
        self.logger.error(message)


# ---------------------------------------------------------------------------
# Module-level helpers (không phụ thuộc vào instance)
# ---------------------------------------------------------------------------

def _get_metric(
    data: dict[str, Any],
    keys: tuple[str, ...],
) -> float | None:
    """Tìm giá trị float đầu tiên khớp với một trong các key (case-insensitive).

    Args:
        data: Dict chứa các metric tài chính.
        keys: Tuple các tên key cần tìm (ưu tiên theo thứ tự).

    Returns:
        Giá trị float đầu tiên tìm được, hoặc None nếu không tìm thấy.
    """
    if not data:
        return None

    # Tạo mapping lowercase → original key để tra cứu nhanh
    lower_map: dict[str, Any] = {k.lower().strip(): v for k, v in data.items()}

    for key in keys:
        key_lower = key.lower().strip()
        # Exact match trước
        val = lower_map.get(key_lower)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                pass

        # Partial match nếu không exact
        for data_key_lower, data_val in lower_map.items():
            if key_lower in data_key_lower or data_key_lower in key_lower:
                try:
                    return float(data_val)
                except (TypeError, ValueError):
                    pass

    return None


def _all_valid(*values: Any) -> bool:
    """Kiểm tra tất cả giá trị đều không None và là số hữu hạn."""
    import math
    for v in values:
        if v is None:
            return False
        try:
            f = float(v)
            if not math.isfinite(f):
                return False
        except (TypeError, ValueError):
            return False
    return True


def _select_report_dict(
    report_type: str,
    income: dict[int, dict[str, Any]],
    balance: dict[int, dict[str, Any]],
    cash_flow: dict[int, dict[str, Any]],
) -> dict[int, dict[str, Any]]:
    """Chọn dict đúng loại báo cáo dựa trên report_type string."""
    rt = report_type.lower()
    if any(kw in rt for kw in ("income", "p&l", "pl", "kqkd", "kết quả kinh doanh")):
        return income
    if any(kw in rt for kw in ("balance", "cdkt", "cân đối", "balance_sheet")):
        return balance
    if any(kw in rt for kw in ("cash", "lctt", "lưu chuyển", "cash_flow")):
        return cash_flow
    # Default → income statement
    return income


def _normalize_year_keys(d: dict[Any, Any]) -> dict[int, dict[str, Any]]:
    """Chuyển tất cả key của dict thành int (năm tài chính)."""
    result: dict[int, dict[str, Any]] = {}
    for k, v in d.items():
        try:
            year = int(k)
            result[year] = v
        except (TypeError, ValueError):
            pass
    return result


def _assess_trend(values: list[float]) -> str:
    """Đánh giá hướng xu hướng đơn giản từ list giá trị theo thời gian.

    Returns:
        "improving", "deteriorating", hoặc "stable"
    """
    if len(values) < 2:
        return "stable"

    # So sánh nửa đầu và nửa sau
    mid = len(values) // 2
    first_half_avg = sum(values[:mid]) / mid
    second_half_avg = sum(values[mid:]) / (len(values) - mid)

    change_pct = (second_half_avg - first_half_avg) / abs(first_half_avg) if first_half_avg != 0 else 0

    if change_pct > 0.03:
        return "improving"
    elif change_pct < -0.03:
        return "deteriorating"
    else:
        return "stable"


def _truncate_nested(obj: Any, max_chars: int = 1500) -> Any:
    """Rút gọn nested dict/list để tránh prompt quá dài khi gọi LLM."""
    serialized = json.dumps(obj, ensure_ascii=False, default=str)
    if len(serialized) <= max_chars:
        return obj

    # Nếu là dict → giữ lại structure nhưng rút gọn value
    if isinstance(obj, dict):
        result = {}
        remaining = max_chars
        for k, v in obj.items():
            v_str = json.dumps(v, ensure_ascii=False, default=str)
            if remaining > 50:
                result[k] = _truncate_nested(v, min(remaining - 10, 300))
                remaining -= len(json.dumps(result[k], default=str))
            else:
                result[k] = "...(truncated)"
        return result

    if isinstance(obj, list):
        return obj[: max(1, max_chars // 100)]

    # Scalar
    s = str(obj)
    return s[:max_chars] + "..." if len(s) > max_chars else s
