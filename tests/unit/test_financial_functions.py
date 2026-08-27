"""Unit tests for src.finance.financial_functions."""

import math
import pytest

from src.finance.financial_functions import (
    asset_turnover,
    bvps,
    cagr,
    cash_ratio,
    current_ratio,
    days_inventory_on_hand,
    days_sales_outstanding,
    debt_to_assets,
    debt_to_equity,
    dividend_yield,
    dupont_3step,
    dupont_5step,
    ebitda_margin,
    eps,
    ev_to_ebitda,
    financial_leverage,
    gross_margin,
    interest_coverage_ratio,
    inventory_turnover,
    net_margin,
    operating_margin,
    pb_ratio,
    pe_ratio,
    ps_ratio,
    quick_ratio,
    qoq_growth,
    receivables_turnover,
    roa,
    roe,
    roic,
    yoy_growth,
)


def test_profitability_ratios():
    assert gross_margin(300, 1000) == pytest.approx(0.3)
    assert gross_margin(0, 0) == 0.0
    assert operating_margin(150, 1000) == pytest.approx(0.15)
    assert net_margin(100, 1000) == pytest.approx(0.1)
    assert ebitda_margin(200, 1000) == pytest.approx(0.2)
    assert roe(200, 1000) == pytest.approx(0.2)
    assert roe(200, 0) == 0.0
    assert roa(100, 1000) == pytest.approx(0.1)
    assert roic(120, 800) == pytest.approx(0.15)


def test_liquidity_and_solvency_ratios():
    assert current_ratio(1500, 1000) == pytest.approx(1.5)
    assert current_ratio(1500, 0) == 0.0
    assert quick_ratio(1500, 500, 1000) == pytest.approx(1.0)
    assert cash_ratio(400, 1000) == pytest.approx(0.4)
    assert debt_to_equity(500, 1000) == pytest.approx(0.5)
    assert debt_to_assets(500, 2000) == pytest.approx(0.25)
    assert financial_leverage(2000, 1000) == pytest.approx(2.0)
    assert interest_coverage_ratio(300, 50) == pytest.approx(6.0)
    assert interest_coverage_ratio(300, 0) == float("inf")


def test_efficiency_ratios():
    assert asset_turnover(2000, 1000) == pytest.approx(2.0)
    assert inventory_turnover(800, 200) == pytest.approx(4.0)
    assert receivables_turnover(1200, 300) == pytest.approx(4.0)
    assert days_sales_outstanding(300, 1200, 365) == pytest.approx(91.25)
    assert days_inventory_on_hand(200, 800, 365) == pytest.approx(91.25)


def test_growth_rates():
    assert yoy_growth(120, 100) == pytest.approx(0.2)
    assert yoy_growth(80, 100) == pytest.approx(-0.2)
    assert qoq_growth(110, 100) == pytest.approx(0.1)
    # CAGR: from 100 to 200 in 3 years -> (2)^(1/3) - 1 ≈ 0.25992
    assert cagr(100, 200, 3) == pytest.approx(0.25992, rel=1e-3)
    assert cagr(0, 100, 3) == 0.0


def test_valuation_ratios():
    assert eps(1000000, 100000) == pytest.approx(10.0)
    assert bvps(5000000, 100000) == pytest.approx(50.0)
    assert pe_ratio(100, 10) == pytest.approx(10.0)
    assert pb_ratio(100, 50) == pytest.approx(2.0)
    assert ps_ratio(10000000, 5000000) == pytest.approx(2.0)
    assert ev_to_ebitda(12000000, 2000000) == pytest.approx(6.0)
    assert dividend_yield(5.0, 100.0) == pytest.approx(0.05)


def test_dupont_analysis():
    # 3-step: Net Margin (10%) * Asset Turnover (1.5) * Leverage (2.0) = ROE (30%)
    res3 = dupont_3step(net_income=100, revenue=1000, total_assets=666.6667, equity=333.3333)
    assert res3["net_profit_margin"] == pytest.approx(0.1)
    assert res3["asset_turnover"] == pytest.approx(1.5, rel=1e-3)
    assert res3["equity_multiplier"] == pytest.approx(2.0, rel=1e-3)
    assert res3["roe"] == pytest.approx(0.3, rel=1e-3)

    # 5-step: Tax Burden (0.8) * Interest Burden (0.75) * Op Margin (0.2) * Turnover (1.5) * Leverage (2.0) = 36%
    res5 = dupont_5step(
        net_income=80,
        ebt=100,
        ebit=133.3333,
        revenue=666.6667,
        total_assets=444.4444,
        equity=222.2222,
    )
    assert res5["tax_burden"] == pytest.approx(0.8)
    assert res5["interest_burden"] == pytest.approx(0.75, rel=1e-3)
    assert res5["operating_margin"] == pytest.approx(0.2, rel=1e-3)
    assert res5["asset_turnover"] == pytest.approx(1.5, rel=1e-3)
    assert res5["equity_multiplier"] == pytest.approx(2.0, rel=1e-3)
    assert res5["roe"] == pytest.approx(0.36, rel=1e-3)
