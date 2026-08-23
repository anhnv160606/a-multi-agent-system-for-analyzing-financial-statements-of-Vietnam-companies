"""
Table Extractor for Native PDF Documents.
Extracts structured financial tables, normalizes columns & headers,
and integrates normalize_vn_number() for numerical standardization.
"""

import io
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import fitz
import pandas as pd

try:
    from src.ingestion.models import ExtractedTable
except ImportError:
    from src.ingestion.models import ExtractedTable

try:
    from src.ingestion.number_utils import normalize_vn_number
except ImportError:
    from src.ingestion.number_utils import normalize_vn_number

from src.utils.logger import get_logger

logger = get_logger("src.ingestion.native.table_extractor")


class TableExtractorNative:
    """
    Extracts and standardizes tables from native PDF financial statements.
    Uses PyMuPDF find_tables engine with Vietnamese financial format cleanup.
    """

    TITLE_PATTERNS = [
        r"(BÁO CÁO TÀI CHÍNH.*)",
        r"(BẢNG CÂN ĐỐI KẾ TOÁN.*)",
        r"(BÁO CÁO KẾT QUẢ HOẠT ĐỘNG KINH DOANH.*)",
        r"(BÁO CÁO LƯU CHUYỂN TIỀN TỆ.*)",
        r"(BẢN THUYẾT MINH BÁO CÁO TÀI CHÍNH.*)",
    ]

    def extract_tables_from_pdf(self, pdf_path: str | Path) -> List[ExtractedTable]:
        """
        Extracts all tables from the given native PDF file.
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        extracted_tables: List[ExtractedTable] = []
        doc = fitz.open(str(pdf_path))
        logger.info(f"Extracting native tables from: {pdf_path.name}")

        try:
            for page_index, page in enumerate(doc):
                page_num = page_index + 1
                try:
                    tabs = page.find_tables()
                    page_text = page.get_text("text")

                    for t_idx, tab in enumerate(tabs):
                        raw_table = tab.extract()
                        if not raw_table or len(raw_table) < 2:
                            continue

                        extracted = self._process_raw_table(
                            raw_rows=raw_table,
                            page_num=page_num,
                            table_idx=t_idx + 1,
                            bbox=tab.bbox,
                            page_text=page_text,
                        )
                        if extracted:
                            extracted_tables.append(extracted)
                except Exception as page_err:
                    logger.debug(f"fitz table error on page {page_num}: {page_err}")
        finally:
            doc.close()

        logger.info(f"Extracted {len(extracted_tables)} tables from {pdf_path.name}")
        return extracted_tables

    def _process_raw_table(
        self,
        raw_rows: List[List[Any]],
        page_num: int,
        table_idx: int,
        bbox: Optional[Tuple[float, float, float, float]] = None,
        page_text: str = "",
    ) -> Optional[ExtractedTable]:
        """
        Cleans and normalizes raw table cells into an ExtractedTable object.
        """
        if not raw_rows or len(raw_rows) < 2:
            return None

        # Clean string cells
        cleaned_rows: List[List[str]] = []
        for row in raw_rows:
            cleaned_row = [self._clean_cell(cell) for cell in row]
            if any(cell for cell in cleaned_row):
                cleaned_rows.append(cleaned_row)

        if len(cleaned_rows) < 2:
            return None

        # Normalize column lengths
        max_cols = max(len(r) for r in cleaned_rows)
        for i in range(len(cleaned_rows)):
            if len(cleaned_rows[i]) < max_cols:
                cleaned_rows[i].extend([""] * (max_cols - len(cleaned_rows[i])))

        # Extract headers and data rows
        headers = cleaned_rows[0]
        data_rows = cleaned_rows[1:]

        # Auto-name unnamed columns
        for c_idx in range(len(headers)):
            if not headers[c_idx]:
                headers[c_idx] = f"Cột {c_idx + 1}"

        # Detect table title
        title = self._detect_table_title(page_text, headers)

        # Markdown & CSV output
        markdown_str = self._generate_markdown(headers, data_rows, title=title, page_num=page_num)
        csv_str = self._generate_csv(headers, data_rows)

        return ExtractedTable(
            page_num=page_num,
            table_index=table_idx,
            headers=headers,
            rows=data_rows,
            markdown=markdown_str,
            csv=csv_str,
            bbox=bbox,
            title=title,
            extraction_engine="fitz",
            metadata={"num_rows": len(data_rows), "num_cols": len(headers)},
        )

    def _clean_cell(self, cell: Any) -> str:
        """Cleans cell whitespace and linebreaks."""
        if cell is None:
            return ""
        text = str(cell).strip()
        text = re.sub(r"\s+", " ", text)
        return text

    def _detect_table_title(self, page_text: str, headers: List[str]) -> Optional[str]:
        """Identifies financial report title from context or header."""
        if page_text:
            for pattern in self.TITLE_PATTERNS:
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    return match.group(1).strip()

        header_joint = " ".join(headers).lower()
        if "tài sản" in header_joint or "nguồn vốn" in header_joint:
            return "Bảng Cân đối Kế toán"
        elif "doanh thu" in header_joint or "lợi nhuận" in header_joint:
            return "Báo cáo Kết quả Kinh doanh"
        elif "lưu chuyển tiền" in header_joint:
            return "Báo cáo Lưu chuyển Tiền tệ"
        return None

    def _generate_markdown(
        self, headers: List[str], rows: List[List[str]], title: Optional[str] = None, page_num: int = 1
    ) -> str:
        """Constructs GitHub Flavored Markdown table."""
        lines = []
        if title:
            lines.append(f"### {title} (Trang {page_num})\n")

        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
        for row in rows:
            lines.append("| " + " | ".join(row) + " |")

        return "\n".join(lines)

    def _generate_csv(self, headers: List[str], rows: List[List[str]]) -> str:
        """Generates standard CSV representation."""
        df = pd.DataFrame(rows, columns=headers)
        output = io.StringIO()
        df.to_csv(output, index=False)
        return output.getvalue()
