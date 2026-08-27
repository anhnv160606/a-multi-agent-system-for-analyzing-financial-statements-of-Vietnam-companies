"""Unit tests for src.agents.calculator.validator."""

import pytest
from src.agents.calculator.validator import CalculationValidator, ValidationResult


def test_validate_accounting_identity_balanced():
    validator = CalculationValidator()
    # Assets = 60,325B = Liabilities 30,376B + Equity 29,949B
    res = validator.validate_accounting_identity(
        total_assets=60325000000.0,
        total_liabilities=30376000000.0,
        equity=29949000000.0,
    )
    assert res.is_valid is True
    assert len(res.errors) == 0


def test_validate_accounting_identity_unbalanced():
    validator = CalculationValidator()
    # Assets 100 ≠ Liab 50 + Equity 40 (Missing 10)
    res = validator.validate_accounting_identity(
        total_assets=100.0,
        total_liabilities=50.0,
        equity=40.0,
    )
    assert res.is_valid is False
    assert len(res.errors) == 1
    assert "Bảng cân đối kế toán không khớp" in res.errors[0]


def test_validate_financial_ratios():
    validator = CalculationValidator()
    valid_ratios = {
        "roe": 0.28,
        "roa": 0.14,
        "gross_margin": 0.38,
        "current_ratio": 1.45,
        "pe_ratio": 22.5,
    }
    res = validator.validate_financial_ratios(valid_ratios)
    assert res.is_valid is True
    assert len(res.errors) == 0
    assert len(res.warnings) == 0

    # Negative liquidity -> error
    invalid_ratios = {"current_ratio": -0.5, "roe": 2.5}
    res2 = validator.validate_financial_ratios(invalid_ratios)
    assert res2.is_valid is False
    assert any("không thể âm" in e for e in res2.errors)
    assert any("ROE bất thường" in w for w in res2.warnings)


def test_validate_growth_anomalies():
    validator = CalculationValidator()
    res_normal = validator.validate_growth_anomalies("Doanh thu", 120, 100)
    assert len(res_normal.warnings) == 0

    # Spike > 500%
    res_spike = validator.validate_growth_anomalies("Doanh thu", 800, 100)
    assert len(res_spike.warnings) == 1
    assert "tăng đột biến" in res_spike.warnings[0]
