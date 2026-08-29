"""Interactive Multi-Agent Query Runner (Phase 5 LangGraph Full Pipeline).

Demonstrates the Complete Distributed Multi-Agent System:
  - 🧭 Router Agent: Adaptive classification ('simple', 'calculate', 'analysis', 'valuation')
  - 🔍 Retriever Agent: Jina AI v3 (770 chunks from 232-page PDF) + VNStock Real-time Market Data
  - 🧮 Calculator Agent: PoT Python Sandbox + SQL Generation
  - 📊 Analysis Agent: DuPont 3/5-step + Trend Analysis + Google Gemini commentary
  - ⚖️ Evaluator Agent: Quality Gate & Confidence Scoring
"""

import sys
import yaml
import warnings
warnings.filterwarnings("ignore")

from src.utils.llm_client import _load_env_file, get_default_llm
from src.orchestrator.graph import build_graph, create_initial_state


def run_query(user_query: str):
    _load_env_file()
    try:
        with open("configs/models.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
    except Exception:
        cfg = {}

    llm = get_default_llm("default")
    graph = build_graph(config=cfg, llm=llm)

    print("=" * 80)
    print(f"❓ CÂU HỎI: '{user_query}'")
    print("=" * 80)

    state = create_initial_state(query=user_query)
    final_state = graph.invoke(state)

    query_type = final_state.get("query_type", "analysis")
    ticker = final_state.get("company_ticker", "FPT")
    confidence = final_state.get("confidence_score", 1.0)
    provenance = [p.get("agent") for p in final_state.get("provenance", [])]

    print(f"\n🧭 1. PHÂN LOẠI CHIẾN LƯỢC (Router Agent):")
    print(f"   - Hướng xử lý : '{query_type.upper()}'")
    print(f"   - Mã cổ phiếu : {ticker}")
    print(f"   - Năm tài chính: {final_state.get('fiscal_years', [])}")
    print(f"   - Chuỗi tác tử : {' ➔ '.join(dict.fromkeys(provenance))}")

    # 1. Hiển thị Dữ liệu Thị trường (nếu có từ VNStock)
    market_data = final_state.get("market_data")
    market_ratios = final_state.get("market_ratios")
    if market_data or market_ratios:
        print(f"\n📈 2. DỮ LIỆU THỊ TRƯỜNG THỜI GIAN THỰC (VNStock API):")
        if market_data and market_data.get("records"):
            latest = market_data["records"][-1]
            print(f"   - Giá đóng cửa gần nhất ({latest.get('date')}): {latest.get('close', 0):,.0f} VND (Mở cửa: {latest.get('open', 0):,.0f}, Cao nhất: {latest.get('high', 0):,.0f}, Thấp nhất: {latest.get('low', 0):,.0f})")
            print(f"   - Khối lượng giao dịch: {latest.get('volume', 0):,.0f} cổ phiếu")
        if market_ratios:
            pe_str = f"{market_ratios.get('pe')}x" if market_ratios.get('pe') is not None else "N/A"
            pb_str = f"{market_ratios.get('pb')}x" if market_ratios.get('pb') is not None else "N/A"
            eps_val = market_ratios.get('eps')
            eps_str = f"{eps_val:,.0f} VND" if eps_val is not None else "N/A"
            print(f"   - Định giá P/E: {pe_str} | P/B: {pb_str} | EPS: {eps_str}")

    # 2. Hiển thị Đoạn trích xuất từ PDF (Retriever)
    retrieved = final_state.get("retrieved_chunks", [])
    pdf_chunks = [c for c in retrieved if c.get("metadata", {}).get("source") != "vnstock_api"]
    if pdf_chunks:
        print(f"\n📄 3. TÀI LIỆU TRÍCH XUẤT TỪ PDF (Jina AI v3):")
        for idx, c in enumerate(pdf_chunks[:2], 1):
            page = c.get("metadata", {}).get("page", "N/A")
            content = c.get("content", "").strip().replace("\n", " ")
            print(f"   [{idx}] (Trang {page}): \"{content[:200]}...\"")

    # 3. Hiển thị Kết quả tính toán Sandbox (Calculator)
    calc_res = final_state.get("calculator_results", {})
    if calc_res:
        print(f"\n🧮 4. KẾT QUẢ TÍNH TOÁN (Python Sandbox & SQL):")
        for k, v in calc_res.items():
            if k in ("parsed_financial_data", "dupont") or not isinstance(v, (int, float)):
                continue
            if abs(v) > 1e6:
                print(f"   - {k:<22}: {v:,.0f} VND")
            elif "margin" in k or "roe" in k or "roa" in k:
                print(f"   - {k:<22}: {v:.2%}")
            else:
                print(f"   - {k:<22}: {v:.4f}")

    # 4. Hiển thị Phân tích DuPont & Nhận định (Analysis Agent)
    analysis_res = final_state.get("analysis_results", {})
    dupont = analysis_res.get("dupont", {})
    if dupont and dupont.get("dupont_3step"):
        print(f"\n🔬 5. BÓC TÁCH MÔ HÌNH DUPONT 3 BƯỚC:")
        for yr, d in dupont["dupont_3step"].items():
            net_margin = d.get("net_profit_margin")
            asset_turn = d.get("asset_turnover")
            eq_mult = d.get("equity_multiplier")
            roe_val = d.get("roe")

            nm_str = f"{net_margin:.2%}" if net_margin is not None else "N/A"
            at_str = f"{asset_turn:.4f} lần" if asset_turn is not None else "N/A"
            eq_str = f"{eq_mult:.4f}x" if eq_mult is not None else "N/A"
            roe_str = f"{roe_val:.2%}" if roe_val is not None else "N/A"

            print(f"   * Năm {yr}:")
            print(f"     + Biên lợi nhuận ròng (Net Margin) : {nm_str}")
            print(f"     + Vòng quay tổng tài sản (Turnover) : {at_str}")
            print(f"     + Đòn bẩy tài chính (Multiplier)   : {eq_str}")
            print(f"     ➔ ROE Tổng hợp                      : {roe_str}")

    # 5. Hiển thị Tổng hợp Đa chiều (Synthesis Agent)
    synthesis_res = final_state.get("synthesis_results")
    if isinstance(synthesis_res, dict):
        exec_sum = synthesis_res.get("executive_summary")
        if exec_sum:
            print(f"\n📑 6. TÓM TẮT ĐIỀU HÀNH (Synthesis Agent):")
            print(f"   {exec_sum}")

        strengths = synthesis_res.get("strengths") or []
        if strengths:
            print(f"\n   💪 Điểm mạnh (Strengths):")
            for s in strengths[:3]:
                print(f"      + {s}")

        risks = synthesis_res.get("risks") or []
        if risks:
            print(f"\n   ⚠️ Rủi ro & Thách thức (Risks):")
            for r in risks[:3]:
                print(f"      + {r}")

    # 6. Hiển thị Báo cáo Tài chính Hoàn chỉnh (Report Agent)
    final_report = final_state.get("final_report")
    if final_report and isinstance(final_report, str) and len(final_report.strip()) > 50:
        print(f"\n📄 7. BÁO CÁO PHÂN TÍCH TÀI CHÍNH TỔNG HỢP (Report Agent):")
        print("   " + "-" * 76)
        for line in final_report.strip().split("\n"):
            print(f"   {line}")
        print("   " + "-" * 76)
    else:
        interp = analysis_res.get("interpretation") or dupont.get("interpretation")
        if not interp or "Không đủ dữ liệu" in interp:
            try:
                summary_llm = get_default_llm("analysis") or llm
                if summary_llm:
                    prompt = (
                        f"Bạn là Chuyên gia Phân tích Tài chính và Chứng khoán Việt Nam.\n"
                        f"Người dùng hỏi: '{user_query}'\n"
                        f"Thông tin thu thập được từ hệ thống:\n"
                        f"- Mã cổ phiếu: {ticker}\n"
                        f"- Dữ liệu thị trường (VNStock): {market_data}\n"
                        f"- Chỉ số định giá & tài chính: {market_ratios}\n"
                        f"- Dữ liệu tính toán BCTC: {calc_res}\n"
                        f"- Trích xuất PDF: {[c.get('content', '')[:200] for c in pdf_chunks[:2]]}\n\n"
                        f"Hãy trả lời câu hỏi của người dùng một cách rõ ràng, chuyên nghiệp, phân tích tình hình kinh doanh, doanh thu, lợi nhuận, hiệu quả sinh lời và nhận định cổ phiếu bằng tiếng Việt."
                    )
                    interp = summary_llm.invoke(prompt).content
            except Exception:
                pass

        if interp:
            print(f"\n💡 7. CÂU TRẢ LỜI TỔNG HỢP TỪ AI (Google Gemini):")
            print(f"   {interp.strip()}")

    print("\n" + "=" * 80)
    print(f"✅ ĐÁNH GIÁ CHẤT LƯỢNG (Evaluator Agent): Điểm tin cậy = {confidence:.2f}/1.00")
    print("=" * 80)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        q = " ".join(sys.argv[1:])
        run_query(q)
    else:
        print("\n👉 CHẾ ĐỘ THỬ NGHIỆM HỆ THỐNG MULTI-AGENT TÀI CHÍNH (PHASE 5)")
        user_q = input("Nhập câu hỏi tài chính của bạn (hoặc nhấn Enter để dùng câu mẫu): ")
        if not user_q.strip():
            user_q = "Phân tích doanh thu, lợi nhuận, bóc tách DuPont và giá cổ phiếu FPT năm 2023"
        run_query(user_q)
