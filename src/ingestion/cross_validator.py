"""
Cross-Validation Module (Task 1.10).
Compares financial metrics extracted from PDF tables against VNStock Market API data,
calculates discrepancy percentages, and computes overall data confidence scores.
"""

import re
from typing import Dict, List, Optional

from src.ingestion.models import (
    ExtractedTable,
    FinancialRatioSummary,
    MismatchDetail,
    ValidationResult,
)
from src.utils.logger import get_logger

logger = get_logger("src.ingestion.cross_validator")


class CrossValidator:
    """
    Cross-validates financial figures from PDF against API benchmarks.
    Detects OCR/table extraction errors early before feeding numbers to reasoning agents.
    """

    # Keyword mappings for standard Vietnamese financial line items
    SYNONYM_MAP = {
        "revenue": [
            "doanh thu thuần",
            "doanh thu bán hàng",
            "tổng doanh thu",
            "doanh thu thuần về bán hàng",
            "doanh thu hoạt động",
        ],
        "net_profit": [
            "lợi nhuận sau thuế",
            "lợi nhuận thuần sau thuế",
            "lợi nhuận sau thuế thu nhập doanh nghiệp",
            "lãi sau thuế",
            "lợi nhuận sau thuế của cổ đông công ty mẹ",
        ],
        "total_assets": [
            "tổng cộng tài sản",
            "tổng tài sản",
            "tổng số tài sản",
        ],
    }

    def __init__(self, tolerance_pct: float = 2.0):
        self.tolerance_pct = tolerance_pct

    def validate(
        self,
        tables: List[ExtractedTable],
        api_data: FinancialRatioSummary,
        ticker: str,
        fiscal_year: int,
    ) -> ValidationResult:
        """
        Cross-validates extracted PDF tables with API metrics for a given company and year.
        """
        logger.info(f"Cross-validating data for {ticker} - Fiscal Year {fiscal_year}")

        # 1. Extract candidate numbers from tables
        extracted_metrics = self._extract_key_metrics_from_tables(tables)

        matched_items: List[str] = []
        mismatches: List[MismatchDetail] = []
        total_checks = 0
        successful_matches = 0

        # 2. Compare available metrics
        comparisons = [
            ("revenue", "Doanh thu thuần", extracted_metrics.get("revenue"), api_data.revenue),
            ("net_profit", "Lợi nhuận sau thuế", extracted_metrics.get("net_profit"), api_data.net_profit),
            ("total_assets", "Tổng tài sản", extracted_metrics.get("total_assets"), api_data.total_assets),
        ]

        for metric_key, metric_name, pdf_val, api_val in comparisons:
            if pdf_val is not None and api_val is not None and api_val != 0:
                total_checks += 1
                diff = abs(pdf_val - api_val)
                variance_pct = (diff / abs(api_val)) * 100.0

                if variance_pct <= self.tolerance_pct:
                    status = "MATCH"
                    successful_matches += 1
                    matched_items.append(f"{metric_name} (Khớp trong sai số {variance_pct:.2f}%)")
                elif variance_pct <= 5.0:
                    status = "MISMATCH_MINOR"
                    mismatches.append(
                        MismatchDetail(
                            metric=metric_name,
                            pdf_value=pdf_val,
                            api_value=api_val,
                            difference=diff,
                            variance_pct=variance_pct,
                            status=status,
                        )
                    )
                else:
                    status = "MISMATCH_MAJOR"
                    mismatches.append(
                        MismatchDetail(
                            metric=metric_name,
                            pdf_value=pdf_val,
                            api_value=api_val,
                            difference=diff,
                            variance_pct=variance_pct,
                            status=status,
                        )
                    )

        # 3. Compute overall confidence score
        if total_checks > 0:
            confidence_score = round(successful_matches / total_checks, 2)
            is_valid = confidence_score >= 0.70
        else:
            confidence_score = 1.0 if len(tables) > 0 else 0.5
            is_valid = True

        summary_notes = (
            f"Đối chiếu {total_checks} chỉ tiêu tài chính: "
            f"{successful_matches} chỉ tiêu khớp, {len(mismatches)} chỉ tiêu có độ lệch."
        )

        logger.info(
            f"Validation complete: is_valid={is_valid}, confidence={confidence_score} ({summary_notes})"
        )

        return ValidationResult(
            ticker=ticker,
            fiscal_year=fiscal_year,
            is_valid=is_valid,
            confidence_score=confidence_score,
            matched_items=matched_items,
            mismatches=mismatches,
            summary_notes=summary_notes,
        )

    def _extract_key_metrics_from_tables(self, tables: List[ExtractedTable]) -> Dict[str, float]:
        """
        Parses tables to find standard financial line items and their values.
        """
        found_metrics: Dict[str, float] = {}

        for table in tables:
            # Check headers to identify columns to ignore (Mã số, Thuyết minh)
            code_col_indices = set()
            for idx, h in enumerate(table.headers):
                h_lower = h.lower()
                if "mã số" in h_lower or "thuyết minh" in h_lower or h_lower == "stt":
                    code_col_indices.add(idx)

            for row in table.rows:
                if not row or len(row) < 2:
                    continue

                line_label = row[0].lower().strip()

                # Search through synonym patterns
                for standard_metric, patterns in self.SYNONYM_MAP.items():
                    if standard_metric in found_metrics:
                        continue  # Already extracted

                    for pat in patterns:
                        if pat in line_label:
                            # Filter cells by excluding known code column indices
                            candidate_cells = [
                                cell for idx, cell in enumerate(row[1:], start=1)
                                if idx not in code_col_indices
                            ]
                            value = self._parse_financial_value(candidate_cells)
                            if value is not None:
                                found_metrics[standard_metric] = value
                                break

        return found_metrics

    def _parse_financial_value(self, cells: List[str]) -> Optional[float]:
        """
        Extracts the most representative financial amount from row cells.
        Skips item codes (<= 100) if larger financial amounts (> 1000) are available.
        """
        parsed_numbers = []
        for cell in cells:
            clean = cell.strip()
            if not clean or clean == "-":
                continue

            # Check negative parenthesized format: (123.456) -> -123456
            is_negative = clean.startswith("(") and clean.endswith(")")
            clean = clean.replace("(", "").replace(")", "").strip()

            # Remove dot thousand separators and replace comma with dot
            normalized = clean.replace(".", "").replace(",", ".")

            match = re.search(r"[-+]?\d*\.?\d+", normalized)
            if match:
                try:
                    num = float(match.group())
                    val = -num if is_negative else num
                    parsed_numbers.append(val)
                except ValueError:
                    continue

        if not parsed_numbers:
            return None

        # If there are numbers > 1000, pick the first significant financial number (skipping 2-digit codes)
        significant = [n for n in parsed_numbers if abs(n) >= 1000]
        if significant:
            return significant[0]

        return parsed_numbers[0]

