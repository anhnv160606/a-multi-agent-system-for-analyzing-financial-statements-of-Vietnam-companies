"""
Interactive Command-Line Interface (CLI) for Financial Multi-Agent System (Task 6.1).
Supports one-shot CLI arguments or interactive conversational loop.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import yaml
from src.database.vector_store import VectorStore
from src.orchestrator.graph import build_graph, create_initial_state
from src.utils.llm_client import _load_env_file, get_default_llm
from src.utils.logger import get_logger

logger = get_logger("src.ui.cli")


# ANSI Color Codes
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
MAGENTA = "\033[95m"
BLUE = "\033[94m"
BOLD = "\033[1m"
RESET = "\033[0m"


def print_banner():
    banner = f"""
{CYAN}{BOLD}╔══════════════════════════════════════════════════════════════════════════════╗
║     HỆ THỐNG MULTI-AGENT PHÂN TÍCH BÁO CÁO TÀI CHÍNH DOANH NGHIỆP VIỆT NAM   ║
║     (Phase 6.1 — Interactive CLI Terminal Console)                          ║
╚══════════════════════════════════════════════════════════════════════════════╝{RESET}
{YELLOW}💡 Gõ câu hỏi tài chính (ví dụ: 'Phân tích FPT 2023', 'Hòa Phát Dung Quất 2')
   Gõ 'exit' hoặc 'quit' để thoát.{RESET}
"""
    print(banner)


def render_result(final_state: Dict[str, Any], query: str):
    ticker = final_state.get("company_ticker", "N/A")
    years = final_state.get("fiscal_years", [])
    confidence = float(final_state.get("confidence_score", 0.0) or 0.0)
    query_type = str(final_state.get("query_type", "analysis")).upper()

    print(f"\n{BOLD}{'=' * 80}{RESET}")
    print(f"{GREEN}🧭 1. CHIẾN LƯỢC ĐIỀU PHỐI (Router Agent):{RESET}")
    print(f"   • Hướng xử lý : {YELLOW}'{query_type}'{RESET}")
    print(f"   • Mã cổ phiếu : {BOLD}{ticker}{RESET}")
    print(f"   • Năm tài chính: {years}")

    # 2. Dữ liệu thị trường thời gian thực (VNStock)
    market_data = final_state.get("market_data")
    market_ratios = final_state.get("market_ratios")
    if market_data and hasattr(market_data, "records") and market_data.records:
        rec = market_data.records[-1]
        print(f"\n{CYAN}📈 2. DỮ LIỆU THỊ TRƯỜNG THỜI GIAN THỰC (VNStock API):{RESET}")
        print(f"   • Giá khớp lệnh gần nhất: {BOLD}{rec.close:,.0f} VND{RESET} (Mở: {rec.open:,.0f}, Cao: {rec.high:,.0f}, Thấp: {rec.low:,.0f})")
        print(f"   • Khối lượng giao dịch  : {rec.volume:,.0f} cổ phiếu")

    if market_ratios and hasattr(market_ratios, "pe"):
        pe_str = f"{market_ratios.pe:.1f}x" if market_ratios.pe is not None else "N/A"
        pb_str = f"{market_ratios.pb:.1f}x" if market_ratios.pb is not None else "N/A"
        eps_str = f"{market_ratios.eps:,.0f} VND" if market_ratios.eps is not None else "N/A"
        print(f"   • Định giá thị trường   : P/E: {pe_str} | P/B: {pb_str} | EPS: {eps_str}")

    # 3. Kết quả tính toán Sandbox (Calculator Agent)
    calc_res = final_state.get("calculator_results", {})
    if calc_res:
        print(f"\n{MAGENTA}🧮 3. SỐ LIỆU TÍNH TOÁN BCTC (Calculator Agent):{RESET}")
        for k, v in calc_res.items():
            if k in ("parsed_financial_data", "dupont") or not isinstance(v, (int, float)):
                continue
            if abs(v) > 1e6:
                print(f"   • {k:<22}: {v:,.0f} VND")
            elif "margin" in k or "roe" in k or "roa" in k:
                print(f"   • {k:<22}: {v:.2%}")
            else:
                print(f"   • {k:<22}: {v:.4f}")

    # 4. Bóc tách DuPont (Analysis Agent)
    analysis_res = final_state.get("analysis_results", {})
    dupont = analysis_res.get("dupont", {})
    if dupont and dupont.get("dupont_3step"):
        print(f"\n{BLUE}🔬 4. BÓC TÁCH MÔ HÌNH DUPONT 3 BƯỚC (Analysis Agent):{RESET}")
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
            print(f"     ➔ {BOLD}ROE Tổng hợp                      : {roe_str}{RESET}")

    # 5. Tóm tắt điều hành & SWOT (Synthesis Agent)
    synthesis_res = final_state.get("synthesis_results")
    if isinstance(synthesis_res, dict):
        exec_sum = synthesis_res.get("executive_summary")
        if exec_sum:
            print(f"\n{YELLOW}📑 5. TÓM TẮT ĐIỀU HÀNH (Synthesis Agent):{RESET}")
            print(f"   {exec_sum}")

        strengths = synthesis_res.get("strengths") or []
        if strengths:
            print(f"\n   💪 {GREEN}Điểm mạnh cốt lõi:{RESET}")
            for s in strengths[:3]:
                print(f"      + {s}")

        risks = synthesis_res.get("risks") or []
        if risks:
            print(f"\n   ⚠️ {RED}Rủi ro & Thách thức:{RESET}")
            for r in risks[:3]:
                print(f"      + {r}")

    # 6. Báo cáo hoàn chỉnh (Report Agent)
    final_report = final_state.get("final_report")
    if final_report and isinstance(final_report, str) and len(final_report.strip()) > 50:
        print(f"\n{BOLD}📄 6. BÁO CÁO PHÂN TÍCH TỔNG HỢP (Report Agent):{RESET}")
        print("   " + "-" * 76)
        for line in final_report.strip().split("\n"):
            print(f"   {line}")
        print("   " + "-" * 76)

    print(f"\n{BOLD}{'=' * 80}{RESET}")
    print(f"{GREEN}✅ ĐÁNH GIÁ CHẤT LƯỢNG (Evaluator Agent): Điểm tin cậy = {confidence:.2f}/1.00{RESET}")
    print(f"{BOLD}{'=' * 80}{RESET}\n")


def run_cli_loop():
    _load_env_file()
    print_banner()

    config_path = PROJECT_ROOT / "configs" / "settings.yaml"
    config: Dict[str, Any] = {}
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

    llm = get_default_llm("default")
    vector_store = VectorStore()
    graph = build_graph(config=config, llm=llm, vector_store=vector_store)

    while True:
        try:
            user_input = input(f"{BOLD}💬 Nhập câu hỏi > {RESET}").strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "q"):
                print(f"{YELLOW}Tạm biệt! Cảm ơn bạn đã sử dụng hệ thống.{RESET}")
                break

            print(f"\n{CYAN}⏳ Đang điều phối 7 tác tử AI xử lý yêu cầu...{RESET}")
            initial_state = create_initial_state(query=user_input)
            final_state = graph.invoke(initial_state)
            render_result(final_state, user_input)

        except KeyboardInterrupt:
            print(f"\n{YELLOW}Đã hủy lệnh.{RESET}")
            break
        except Exception as err:
            print(f"\n{RED}❌ Lỗi xử lý: {err}{RESET}\n")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        q = " ".join(sys.argv[1:])
        _load_env_file()
        config_path = PROJECT_ROOT / "configs" / "settings.yaml"
        config = {}
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
        llm = get_default_llm("default")
        vector_store = VectorStore()
        graph = build_graph(config=config, llm=llm, vector_store=vector_store)
        initial_state = create_initial_state(query=q)
        final_state = graph.invoke(initial_state)
        render_result(final_state, q)
    else:
        run_cli_loop()
