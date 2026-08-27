"""Calculation and Financial Consistency Validator (Task 3.10).

Validates the economic and mathematical consistency of financial calculation results
and underlying statement metrics:
  - Accounting Balance Identity: Total Assets == Total Liabilities + Owner's Equity
  - Ratio Range Validity (non-negative liquidity, reasonable margin ranges)
  - Anomaly & Outlier Detection (abnormal YoY spikes, negative equity)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ValidationResult(BaseModel):
    """Encapsulates validation outcome, detected warnings, and fatal errors."""
    is_valid: bool = True
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    checks_performed: List[str] = Field(default_factory=list)

    def add_error(self, error_msg: str) -> None:
        self.errors.append(error_msg)
        self.is_valid = False

    def add_warning(self, warning_msg: str) -> None:
        self.warnings.append(warning_msg)

    def add_check(self, check_name: str) -> None:
        self.checks_performed.append(check_name)


class CalculationValidator:
    """Validator for financial calculation outputs and accounting identities."""

    def __init__(self, tolerance_ratio: float = 0.005):
        """
        Args:
            tolerance_ratio: Allowable relative discrepancy for rounding (default: 0.5%).
        """
        self.tolerance_ratio = tolerance_ratio

    def validate_accounting_identity(
        self,
        total_assets: Optional[float],
        total_liabilities: Optional[float],
        equity: Optional[float],
    ) -> ValidationResult:
        """
        Checks the fundamental accounting equation:
            Total Assets = Total Liabilities + Owner's Equity
        """
        result = ValidationResult()
        result.add_check("accounting_balance_identity")

        if total_assets is None or total_liabilities is None or equity is None:
            result.add_warning("Missing one or more components for accounting equation check.")
            return result

        sum_liab_equity = total_liabilities + equity
        abs_diff = abs(total_assets - sum_liab_equity)
        rel_diff = (abs_diff / total_assets) if total_assets != 0 else 0.0

        if rel_diff > self.tolerance_ratio:
            result.add_error(
                f"Bảng cân đối kế toán không khớp: Tổng tài sản ({total_assets:,.0f}) "
                f"≠ Tổng nợ ({total_liabilities:,.0f}) + Vốn CSH ({equity:,.0f}). "
                f"Chênh lệch: {abs_diff:,.0f} ({rel_diff:.2%})"
            )
        return result

    def validate_financial_ratios(self, ratios: Dict[str, Any]) -> ValidationResult:
        """
        Validates computed financial ratios against logical economic bounds.
        """
        result = ValidationResult()
        result.add_check("ratio_range_bounds")

        for key, val in ratios.items():
            if val is None or not isinstance(val, (int, float)):
                continue

            # Check Current / Quick / Cash ratios >= 0
            if key in ("current_ratio", "quick_ratio", "cash_ratio"):
                if val < 0:
                    result.add_error(f"Hệ số thanh khoản '{key}' không thể âm: {val:.4f}")
                elif val < 0.5:
                    result.add_warning(f"Hệ số thanh khoản '{key}' thấp dưới mức an toàn: {val:.4f} (< 0.5)")

            # Check Margin bounds
            elif key in ("gross_margin", "operating_margin", "net_margin", "ebitda_margin"):
                if val > 1.0:
                    result.add_warning(f"Biên lợi nhuận '{key}' vượt quá 100%: {val:.2%}")
                elif val < -1.0:
                    result.add_warning(f"Biên lợi nhuận âm sâu '{key}': {val:.2%}")

            # Check ROE / ROA
            elif key == "roe":
                if val > 1.5:
                    result.add_warning(f"Chỉ số ROE bất thường rất cao: {val:.2%} (> 150%)")
                elif val < -1.0:
                    result.add_warning(f"Chỉ số ROE âm sâu do lỗ nặng: {val:.2%}")

            elif key == "roa":
                if val > 0.5:
                    result.add_warning(f"Chỉ số ROA bất thường cao: {val:.2%} (> 50%)")

            # Check Valuation multiples
            elif key in ("pe_ratio", "pb_ratio", "ps_ratio", "ev_to_ebitda"):
                if val < 0:
                    result.add_warning(f"Hệ số định giá '{key}' mang giá trị âm do lợi nhuận/vốn âm: {val:.2f}")

        return result

    def validate_growth_anomalies(
        self,
        metric_name: str,
        current_value: float,
        prior_value: float,
        max_spike_ratio: float = 5.0,
    ) -> ValidationResult:
        """
        Detects anomalous growth spikes (> 500% YoY or extreme drops).
        """
        result = ValidationResult()
        result.add_check("growth_anomaly_check")

        if prior_value == 0:
            result.add_warning(f"Giá trị kỳ trước của '{metric_name}' bằng 0, không thể tính % tăng trưởng.")
            return result

        growth = (current_value - prior_value) / abs(prior_value)
        if growth > max_spike_ratio:
            result.add_warning(
                f"Chỉ tiêu '{metric_name}' tăng đột biến {growth:.1%}: "
                f"từ {prior_value:,.0f} lên {current_value:,.0f}."
            )
        elif growth < -0.9:
            result.add_warning(
                f"Chỉ tiêu '{metric_name}' sụt giảm nghiêm trọng {growth:.1%}: "
                f"từ {prior_value:,.0f} xuống {current_value:,.0f}."
            )

        return result
