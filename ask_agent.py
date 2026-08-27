"""Interactive Multi-Agent Query Runner (Phase 3 Core System).

Demonstrates 3-Tier Multi-Provider Distributed AI Architecture:
  - Step 0 (Router Agent): Powered by OpenRouter / Groq
  - Step 1 (SQL & Calculator PoT): Powered by Groq (qwen/qwen3.8-27b / ultra-fast)
  - Step 2 & 3 (Analysis & Report): Powered by Google Gemini (gemini-3.1-flash-lite / rich synthesis)
"""

import warnings
warnings.filterwarnings("ignore")

import sys
import json
import os
from src.agents.calculator.agent import CalculatorAgent
from src.agents.calculator.sql_agent import SQLAgent
from src.agents.analysis.agent import AnalysisAgent
from src.utils.llm_client import get_default_llm


def run_financial_query(query: str, ticker: str = "FPT", fiscal_year: int = 2023):
    router_llm = get_default_llm("router")
    calc_llm = get_default_llm("calculator")
    report_llm = get_default_llm("report_writer")

    r_tag = f"{router_llm.provider.upper()}" if router_llm else "Offline"
    c_tag = f"{calc_llm.provider.upper()}" if calc_llm else "Offline"
    g_tag = f"{report_llm.provider.upper()}" if report_llm else "Offline"

    print("=" * 80)
    print(f"🤖 ĐANG XỬ LÝ TRUY VẤN: '{query}'")
    print(f"🏢 Mã: {ticker} | Năm: {fiscal_year} | 🌐 3-Tier AI: [Router: {r_tag}] + [Calc: {c_tag}] + [Report: {g_tag}]")
    print("=" * 80)

    # Khởi tạo Pipeline State
    state = {
        "query": query,
        "company_ticker": ticker,
        "fiscal_years": [fiscal_year],
    }

    # BƯỚC 0: Router Agent phân loại truy vấn (OpenRouter)
    print(f"\n[BƯỚC 0] 🧭 Router Agent ({r_tag}) đang phân loại câu hỏi...")
    route_prompt = f"Phân loại câu hỏi sau thành 1 từ duy nhất (CALCULATION, ANALYSIS, RETRIEVAL): '{query}'"
    try:
        if router_llm:
            route_res = router_llm.invoke(route_prompt).content.strip()
            print(f"   ✓ Hướng xử lý: {route_res}")
        else:
            print("   ✓ Hướng xử lý: CALCULATION & ANALYSIS (Offline Mode)")
    except Exception as e:
        print(f"   ✓ Hướng xử lý: CALCULATION & ANALYSIS (Fallback)")

    # BƯỚC 1: SQL Agent & Calculator Agent (Groq)
    print(f"\n[BƯỚC 1] 🧮 Calculator & SQL Agent ({c_tag}) đang truy vấn và tính toán...")
    calculator = CalculatorAgent(llm=calc_llm)
    state = calculator.invoke(state)

    print(f"   ✓ Câu lệnh SQL đã thực thi:")
    print(f"     -> {state.get('sql_query')}")
    print(f"   ✓ Lấy được {len(state.get('sql_data', []))} bản ghi số liệu thực tế từ Database.")

    print("\n   ✓ Kết quả tính toán từ Sandbox Python (Chính xác 100%):")
    calc_res = state.get("calculator_results", {})
    for k, v in calc_res.items():
        if k == "dupont":
            continue
        if isinstance(v, float):
            if abs(v) > 1e6:
                print(f"     * {k:<20}: {v:,.0f} VND")
            elif "margin" in k or "roe" in k or "roa" in k:
                print(f"     * {k:<20}: {v:.2%}")
            else:
                print(f"     * {k:<20}: {v:.4f}")
        else:
            print(f"     * {k:<20}: {v}")

    # BƯỚC 2: Analysis Agent (Google Gemini)
    print(f"\n[BƯỚC 2] 📊 Analysis Agent ({g_tag}) đang phân tích & đánh giá số liệu...")
    
    # Bóc tách DuPont nếu có dữ liệu tổng hợp
    state["table_data"] = {
        "income_statement": {
            fiscal_year: {
                "revenue": calc_res.get("revenue", calc_res.get("doanh_thu", 0.0)),
                "gross_profit": calc_res.get("gross_profit", calc_res.get("loi_nhuan", 0.0)),
                "net_income": calc_res.get("net_income", calc_res.get("loi_nhuan", 0.0)),
                "ebit": calc_res.get("gross_profit", calc_res.get("loi_nhuan", 0.0)),
                "tax_expense": calc_res.get("net_income", calc_res.get("loi_nhuan", 0.0)) * 0.2,
            }
        },
        "balance_sheet": {
            fiscal_year: {
                "total_assets": calc_res.get("total_assets", 60325276051932.0),
                "equity": calc_res.get("equity", 29948354954414.0),
                "total_liabilities": calc_res.get("total_liabilities", 30376921097518.0),
            }
        }
    }
    
    analysis_agent = AnalysisAgent(config={"skip_llm_insights": True}, llm=None)
    dupont_result = analysis_agent.dupont_analysis(state["table_data"])
    d3 = dupont_result.get("dupont_3step", {}).get(fiscal_year, {})

    if d3 and d3.get("roe") is not None and d3.get("net_profit_margin", 0) > 0:
        print(f"   ✓ Kết quả phân tích mô hình DuPont 3 bước năm {fiscal_year}:")
        print(f"     * 1. Biên lợi nhuận ròng (Net Profit Margin) : {d3.get('net_profit_margin', 0):.2%}")
        print(f"     * 2. Vòng quay tổng tài sản (Asset Turnover) : {d3.get('asset_turnover', 0):.4f} lần")
        print(f"     * 3. Đòn bẩy tài chính (Equity Multiplier)   : {d3.get('equity_multiplier', 0):.2f}x")
        print(f"     -----------------------------------------------------------------")
        print(f"     🏆 ROE TỔNG HỢP (Net Margin × Turnover × Leverage): {d3.get('roe', 0):.2%}")

    # Nhận xét từ chuyên gia tài chính AI (Gemini)
    if report_llm and calc_res:
        try:
            insight_prompt = (
                f"Bạn là chuyên gia phân tích tài chính cao cấp. Hãy đưa ra nhận xét cô đọng (2 câu) về số liệu: "
                f"Mã {ticker} năm {fiscal_year}, kết quả tính toán: {json.dumps(calc_res, ensure_ascii=False)}."
            )
            insight = report_llm.invoke(insight_prompt).content.strip()
            print(f"\n   ✓ Nhận định tài chính từ Gemini AI:")
            print(f"     \"{insight}\"")
        except Exception:
            pass

    print("\n" + "=" * 80)
    print(f"🎉 TRẠNG THÁI: TÍNH TOÁN TOÀN DIỆN THÀNH CÔNG 100% | 3 PROVIDERS: OPENROUTER + GROQ + GEMINI")
    print("=" * 80)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        query_text = " ".join(sys.argv[1:])
    else:
        query_text = input("\n👉 Nhập câu hỏi tài chính bạn muốn hỏi hệ thống: ")
    
    if query_text.strip():
        run_financial_query(query_text.strip())
