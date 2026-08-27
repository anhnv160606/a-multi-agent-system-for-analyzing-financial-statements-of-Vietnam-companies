"""Financial Functions Library (Task 3.9).

Provides pure, deterministic financial calculation functions for:
  - Profitability (ROE, ROA, ROIC, Gross Margin, Net Margin, Operating Margin, EBITDA Margin)
  - Liquidity & Solvency (Current Ratio, Quick Ratio, Cash Ratio, Debt-to-Equity, Debt-to-Assets, Interest Coverage)
  - Efficiency (Asset Turnover, Inventory Turnover, Receivables Turnover, Days Sales Outstanding)
  - Growth (YoY Growth, QoQ Growth, CAGR)
  - Valuation & Market Multiples (P/E, P/B, P/S, EV/EBITDA, Dividend Yield, EPS, BVPS)
  - DuPont Analysis Frameworks (3-step and 5-step DuPont decomposition)
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Union


# ==============================================================================
# 1. PROFITABILITY RATIOS (Tỷ số sinh lời)
# ==============================================================================

def gross_margin(gross_profit: float, revenue: float) -> float:
    """Biên lợi nhuận gộp = Lợi nhuận gộp / Doanh thu thuần."""
    if revenue == 0:
        return 0.0
    return gross_profit / revenue


def operating_margin(operating_profit: float, revenue: float) -> float:
    """Biên lợi nhuận hoạt động (EBIT Margin) = Lợi nhuận hoạt động / Doanh thu thuần."""
    if revenue == 0:
        return 0.0
    return operating_profit / revenue


def net_margin(net_income: float, revenue: float) -> float:
    """Biên lợi nhuận ròng = Lợi nhuận sau thuế / Doanh thu thuần."""
    if revenue == 0:
        return 0.0
    return net_income / revenue


def ebitda_margin(ebitda: float, revenue: float) -> float:
    """Biên EBITDA = EBITDA / Doanh thu thuần."""
    if revenue == 0:
        return 0.0
    return ebitda / revenue


def roe(net_income: float, equity: float) -> float:
    """Tỷ suất sinh lời trên vốn chủ sở hữu (ROE) = Lợi nhuận sau thuế / Vốn CSH."""
    if equity <= 0:
        return 0.0
    return net_income / equity


def roa(net_income: float, total_assets: float) -> float:
    """Tỷ suất sinh lời trên tổng tài sản (ROA) = Lợi nhuận sau thuế / Tổng tài sản."""
    if total_assets <= 0:
        return 0.0
    return net_income / total_assets


def roic(nopat: float, invested_capital: float) -> float:
    """Tỷ suất sinh lời trên vốn đầu tư (ROIC) = NOPAT / Vốn đầu tư (Nợ vay + Vốn CSH - Tiền mặt)."""
    if invested_capital <= 0:
        return 0.0
    return nopat / invested_capital


# ==============================================================================
# 2. LIQUIDITY & SOLVENCY RATIOS (Thanh khoản & Đòn bẩy tài chính)
# ==============================================================================

def current_ratio(current_assets: float, current_liabilities: float) -> float:
    """Hệ số thanh toán hiện hành = Tài sản ngắn hạn / Nợ ngắn hạn."""
    if current_liabilities <= 0:
        return 0.0
    return current_assets / current_liabilities


def quick_ratio(current_assets: float, inventory: float, current_liabilities: float) -> float:
    """Hệ số thanh toán nhanh = (Tài sản ngắn hạn - Hàng tồn kho) / Nợ ngắn hạn."""
    if current_liabilities <= 0:
        return 0.0
    return (current_assets - inventory) / current_liabilities


def cash_ratio(cash_and_equivalents: float, current_liabilities: float) -> float:
    """Hệ số thanh toán tiền mặt = Tiền và tương đương tiền / Nợ ngắn hạn."""
    if current_liabilities <= 0:
        return 0.0
    return cash_and_equivalents / current_liabilities


def debt_to_equity(total_debt: float, equity: float) -> float:
    """Hệ số Nợ / Vốn CSH (D/E) = Tổng nợ vay / Vốn chủ sở hữu."""
    if equity <= 0:
        return 0.0
    return total_debt / equity


def debt_to_assets(total_debt: float, total_assets: float) -> float:
    """Hệ số Nợ / Tổng tài sản = Tổng nợ / Tổng tài sản."""
    if total_assets <= 0:
        return 0.0
    return total_debt / total_assets


def financial_leverage(total_assets: float, equity: float) -> float:
    """Đòn bẩy tài chính (Equity Multiplier) = Tổng tài sản / Vốn chủ sở hữu."""
    if equity <= 0:
        return 0.0
    return total_assets / equity


def interest_coverage_ratio(ebit: float, interest_expense: float) -> float:
    """Hệ số khả năng trả lãi (ICR) = EBIT / Chi phí lãi vay."""
    if interest_expense <= 0:
        return float("inf") if ebit > 0 else 0.0
    return ebit / interest_expense


# ==============================================================================
# 3. EFFICIENCY RATIOS (Hiệu quả hoạt động)
# ==============================================================================

def asset_turnover(revenue: float, average_assets: float) -> float:
    """Vòng quay tổng tài sản = Doanh thu thuần / Tổng tài sản bình quân."""
    if average_assets <= 0:
        return 0.0
    return revenue / average_assets


def inventory_turnover(cogs: float, average_inventory: float) -> float:
    """Vòng quay hàng tồn kho = Giá vốn hàng bán / Hàng tồn kho bình quân."""
    if average_inventory <= 0:
        return 0.0
    return cogs / average_inventory


def receivables_turnover(revenue: float, average_receivables: float) -> float:
    """Vòng quay các khoản phải thu = Doanh thu / Phải thu khách hàng bình quân."""
    if average_receivables <= 0:
        return 0.0
    return revenue / average_receivables


def days_sales_outstanding(average_receivables: float, revenue: float, days: int = 365) -> float:
    """Số ngày thu tiền bình quân (DSO) = (Phải thu bình quân / Doanh thu) * Số ngày."""
    if revenue <= 0:
        return 0.0
    return (average_receivables / revenue) * days


def days_inventory_on_hand(average_inventory: float, cogs: float, days: int = 365) -> float:
    """Số ngày tồn kho bình quân (DIO) = (Tồn kho bình quân / Giá vốn) * Số ngày."""
    if cogs <= 0:
        return 0.0
    return (average_inventory / cogs) * days


# ==============================================================================
# 4. GROWTH RATES (Tốc độ tăng trưởng)
# ==============================================================================

def yoy_growth(current_val: float, prior_val: float) -> float:
    """Tăng trưởng cùng kỳ năm trước (YoY Growth Rate) = (Hiện tại - Quá khứ) / |Quá khứ|."""
    if prior_val == 0:
        return 0.0
    return (current_val - prior_val) / abs(prior_val)


def qoq_growth(current_val: float, prior_quarter_val: float) -> float:
    """Tăng trưởng so với quý liền trước (QoQ Growth Rate)."""
    return yoy_growth(current_val, prior_quarter_val)


def cagr(start_val: float, end_val: float, num_years: float) -> float:
    """Tốc độ tăng trưởng kép hàng năm (CAGR) = (Giá trị cuối / Giá trị đầu)^(1/n) - 1."""
    if start_val <= 0 or end_val <= 0 or num_years <= 0:
        return 0.0
    return (end_val / start_val) ** (1.0 / num_years) - 1.0


# ==============================================================================
# 5. MARKET VALUATION RATIOS (Chỉ số thị trường & Định giá)
# ==============================================================================

def eps(net_income: float, outstanding_shares: float) -> float:
    """Thu nhập trên mỗi cổ phần (EPS) = Lợi nhuận sau thuế / Số lượng CP lưu hành."""
    if outstanding_shares <= 0:
        return 0.0
    return net_income / outstanding_shares


def bvps(equity: float, outstanding_shares: float) -> float:
    """Giá trị sổ sách trên mỗi cổ phần (BVPS) = Vốn chủ sở hữu / Số lượng CP lưu hành."""
    if outstanding_shares <= 0:
        return 0.0
    return equity / outstanding_shares


def pe_ratio(market_price: float, eps_value: float) -> float:
    """Hệ số Giá trên Thu nhập (P/E) = Giá thị trường / EPS."""
    if eps_value <= 0:
        return 0.0
    return market_price / eps_value


def pb_ratio(market_price: float, bvps_value: float) -> float:
    """Hệ số Giá trên Giá trị sổ sách (P/B) = Giá thị trường / BVPS."""
    if bvps_value <= 0:
        return 0.0
    return market_price / bvps_value


def ps_ratio(market_cap: float, revenue: float) -> float:
    """Hệ số Giá trên Doanh thu (P/S) = Vốn hóa thị trường / Doanh thu."""
    if revenue <= 0:
        return 0.0
    return market_cap / revenue


def ev_to_ebitda(enterprise_value: float, ebitda: float) -> float:
    """Hệ số EV/EBITDA = Giá trị doanh nghiệp / EBITDA."""
    if ebitda <= 0:
        return 0.0
    return enterprise_value / ebitda


def dividend_yield(annual_dividend_per_share: float, market_price: float) -> float:
    """Tỷ suất cổ tức = Cổ tức tiền mặt trên mỗi CP / Giá thị trường."""
    if market_price <= 0:
        return 0.0
    return annual_dividend_per_share / market_price


# ==============================================================================
# 6. DUPONT ANALYSIS (Mô hình phân tích DuPont)
# ==============================================================================

def dupont_3step(net_income: float, revenue: float, total_assets: float, equity: float) -> Dict[str, float]:
    """
    Mô hình DuPont 3 bước:
      ROE = (Net Income / Revenue) * (Revenue / Assets) * (Assets / Equity)
          = Net Profit Margin * Asset Turnover * Equity Multiplier
    """
    pm = net_margin(net_income, revenue)
    at = asset_turnover(revenue, total_assets)
    em = financial_leverage(total_assets, equity)
    calculated_roe = pm * at * em

    return {
        "net_profit_margin": pm,
        "asset_turnover": at,
        "equity_multiplier": em,
        "roe": calculated_roe,
    }


def dupont_5step(
    net_income: float,
    ebt: float,
    ebit: float,
    revenue: float,
    total_assets: float,
    equity: float,
) -> Dict[str, float]:
    """
    Mô hình DuPont 5 bước:
      ROE = (Net Income / EBT) * (EBT / EBIT) * (EBIT / Revenue) * (Revenue / Assets) * (Assets / Equity)
          = Tax Burden * Interest Burden * Operating Margin * Asset Turnover * Equity Multiplier
    """
    tax_burden = (net_income / ebt) if ebt != 0 else 0.0
    interest_burden = (ebt / ebit) if ebit != 0 else 0.0
    op_margin = operating_margin(ebit, revenue)
    at = asset_turnover(revenue, total_assets)
    em = financial_leverage(total_assets, equity)
    calculated_roe = tax_burden * interest_burden * op_margin * at * em

    return {
        "tax_burden": tax_burden,
        "interest_burden": interest_burden,
        "operating_margin": op_margin,
        "asset_turnover": at,
        "equity_multiplier": em,
        "roe": calculated_roe,
    }
