"""Metadata Enricher — gắn metadata chi tiết cho mỗi chunk.

Bổ sung các field quan trọng cho filtered retrieval:
    - ticker, report_type, doc_type, source_file  (từ SplitDocument)
    - year, quarter  (regex heuristic từ nội dung)
    - section  (đã detect bởi text_chunker, bổ sung nếu thiếu)
"""

import re
from typing import Any, Dict, List, Optional

from src.chunking.models import Chunk
from src.utils.logger import get_logger

logger = get_logger("src.chunking.metadata_enricher")

# ---------------------------------------------------------------------------
# Regex patterns trích năm / quý từ nội dung văn bản
# ---------------------------------------------------------------------------
# "năm 2023", "năm tài chính 2024", "niên độ 2023"
_YEAR_PATTERNS = [
    re.compile(r"(?:năm|niên\s+độ)\s+(?:tài\s+chính\s+)?(\d{4})", re.IGNORECASE),
    re.compile(r"(\d{4})\s*[-–]\s*\d{4}"),  # "2022-2023" → lấy năm đầu
    re.compile(r"(?:FY|fiscal\s+year)\s*(\d{4})", re.IGNORECASE),
    re.compile(r"31/12/(\d{4})"),  # Ngày kết thúc kỳ kế toán
    re.compile(r"(?:ngày|tháng).+(\d{4})\b"),  # Fallback: năm 4 chữ số
]

# "Quý 3/2024", "quý III", "Q3 2024"
_QUARTER_PATTERNS = [
    re.compile(r"[Qq]uý\s+([IViv1-4]+)", re.IGNORECASE),
    re.compile(r"Q([1-4])\b", re.IGNORECASE),
]

# Mapping Roman → int
_ROMAN_TO_INT = {"i": 1, "ii": 2, "iii": 3, "iv": 4}

# ---------------------------------------------------------------------------
# Section detection patterns
# ---------------------------------------------------------------------------
_SECTION_PATTERNS = [
    (re.compile(r"BÁO CÁO TÀI CHÍNH", re.IGNORECASE), "Báo cáo tài chính"),
    (re.compile(r"BẢNG CÂN ĐỐI KẾ TOÁN", re.IGNORECASE), "Bảng cân đối kế toán"),
    (re.compile(r"BÁO CÁO KẾT QUẢ HOẠT ĐỘNG KINH DOANH", re.IGNORECASE), "Báo cáo KQHĐKD"),
    (re.compile(r"BÁO CÁO LƯU CHUYỂN TIỀN TỆ", re.IGNORECASE), "Báo cáo lưu chuyển tiền tệ"),
    (re.compile(r"THUYẾT MINH BÁO CÁO", re.IGNORECASE), "Thuyết minh BCTC"),
    (re.compile(r"TỔNG QUAN DOANH NGHIỆP", re.IGNORECASE), "Tổng quan doanh nghiệp"),
    (re.compile(r"BAN GIÁM ĐỐC|BAN ĐIỀU HÀNH", re.IGNORECASE), "Ban điều hành"),
    (re.compile(r"CƠ CẤU CỔ ĐÔNG", re.IGNORECASE), "Cơ cấu cổ đông"),
    (re.compile(r"BIÊN BẢN.+ĐẠI HỘI", re.IGNORECASE), "Biên bản ĐHCĐ"),
]


def _extract_year(text: str) -> Optional[int]:
    """Trích năm tài chính từ nội dung chunk."""
    for pattern in _YEAR_PATTERNS:
        m = pattern.search(text)
        if m:
            year_str = m.group(1)
            try:
                year = int(year_str)
                if 1990 <= year <= 2050:
                    return year
            except ValueError:
                continue
    return None


def _extract_quarter(text: str) -> Optional[int]:
    """Trích quý từ nội dung chunk."""
    for pattern in _QUARTER_PATTERNS:
        m = pattern.search(text)
        if m:
            raw = m.group(1).strip().lower()
            # Thử Roman numeral
            if raw in _ROMAN_TO_INT:
                return _ROMAN_TO_INT[raw]
            # Thử số
            try:
                q = int(raw)
                if 1 <= q <= 4:
                    return q
            except ValueError:
                continue
    return None


def _detect_section(text: str) -> Optional[str]:
    """Nhận diện section name từ nội dung chunk."""
    for pattern, section_name in _SECTION_PATTERNS:
        if pattern.search(text):
            return section_name
    return None


class MetadataEnricher:
    """Bổ sung metadata cho danh sách Chunk dựa trên SplitDocument + heuristic."""

    def enrich(
        self,
        chunks: List[Chunk],
        doc_ticker: Optional[str] = None,
        doc_report_type: Optional[str] = None,
        doc_type: Optional[str] = None,
        doc_source_file: Optional[str] = None,
        doc_fiscal_year: Optional[int] = None,
    ) -> List[Chunk]:
        """Gắn metadata cho từng chunk.

        Args:
            chunks: danh sách chunks cần enrich.
            doc_*: metadata cấp document từ SplitDocument.
        """
        # Đầu tiên, trích year toàn cục (lấy từ chunk đầu tiên có năm)
        global_year = doc_fiscal_year
        global_quarter: Optional[int] = None

        if not global_year:
            for c in chunks[:10]:  # Scan 10 chunks đầu
                y = _extract_year(c.content)
                if y:
                    global_year = y
                    break

        for c in chunks[:10]:
            q = _extract_quarter(c.content)
            if q:
                global_quarter = q
                break

        enriched_count = 0
        for chunk in chunks:
            changed = False

            # --- Ticker ---
            if not chunk.metadata.ticker and doc_ticker:
                chunk.metadata.ticker = doc_ticker
                changed = True

            # --- Report type ---
            if not chunk.metadata.report_type and doc_report_type:
                chunk.metadata.report_type = doc_report_type
                changed = True

            # --- Doc type ---
            if not chunk.metadata.doc_type and doc_type:
                chunk.metadata.doc_type = doc_type
                changed = True

            # --- Source file ---
            if not chunk.metadata.source_file and doc_source_file:
                chunk.metadata.source_file = doc_source_file
                changed = True

            # --- Year ---
            if not chunk.metadata.year:
                chunk_year = _extract_year(chunk.content)
                chunk.metadata.year = chunk_year or global_year
                if chunk.metadata.year:
                    changed = True

            # --- Quarter ---
            if not chunk.metadata.quarter:
                chunk_quarter = _extract_quarter(chunk.content)
                chunk.metadata.quarter = chunk_quarter or global_quarter
                if chunk.metadata.quarter:
                    changed = True

            # --- Section (bổ sung nếu chưa có) ---
            if not chunk.metadata.section:
                detected = _detect_section(chunk.content)
                if detected:
                    chunk.metadata.section = detected
                    changed = True

            if changed:
                enriched_count += 1

        logger.info(
            f"MetadataEnricher: enriched {enriched_count}/{len(chunks)} chunks "
            f"(ticker={doc_ticker}, year={global_year}, quarter={global_quarter})"
        )
        return chunks
