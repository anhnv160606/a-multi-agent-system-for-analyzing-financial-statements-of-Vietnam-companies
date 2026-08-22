"""
PDF Table Extraction Module (Task 1.4).
Extracts tabular data from Vietnamese financial reports, normalizes columns & numbers,
and exports into Markdown (for LLMs) and CSV/Structured records (for SQL DB).
"""

import io
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from src.ingestion.models import ExtractedTable
from src.utils.logger import get_logger

logger = get_logger("src.ingestion.table_extractor")


class TableExtractor:
    """
    Extracts and standardizes tables from PDF financial statements.
    Supports PyMuPDF (fitz) and pdfplumber with smart Vietnamese financial format cleanup.
    """

    # Common financial statement title patterns
    TITLE_PATTERNS = [
        r"(BÁO CÁO TÀI CHÍNH.*)",
        r"(BẢNG CÂN ĐỐI KẾ TOÁN.*)",
        r"(BÁO CÁO KẾT QUẢ HOẠT ĐỘNG KINH DOANH.*)",
        r"(BÁO CÁO LƯU CHUYỂN TIỀN TỆ.*)",
        r"(BẢN THUYẾT MINH BÁO CÁO TÀI CHÍNH.*)",
        r"(Bảng số liệu.*)",
        r"(Biểu số.*)",
    ]

    def __init__(self):
        self._has_fitz = False
        self._has_pdfplumber = False
        self._check_backends()

    def _check_backends(self):
        """Checks available PDF extraction libraries."""
        try:
            import fitz
            self._has_fitz = True
        except ImportError:
            self._has_fitz = False

        try:
            import pdfplumber
            self._has_pdfplumber = True
        except ImportError:
            self._has_pdfplumber = False

        if not self._has_fitz and not self._has_pdfplumber:
            logger.warning("Neither PyMuPDF (fitz) nor pdfplumber found. Table extraction will be limited.")

    def extract_tables_from_pdf(self, pdf_path: str | Path) -> List[ExtractedTable]:
        """
        Extracts all tables from the given PDF file.
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        extracted_tables: List[ExtractedTable] = []
        logger.info(f"Extracting tables from: {pdf_path.name}")

        if self._has_fitz:
            extracted_tables = self._extract_with_fitz(pdf_path)
        elif self._has_pdfplumber:
            extracted_tables = self._extract_with_pdfplumber(pdf_path)
        else:
            logger.error("No supported PDF parser backend available.")

        logger.info(f"Total tables extracted from {pdf_path.name}: {len(extracted_tables)}")
        return extracted_tables

    def _extract_with_fitz(self, pdf_path: Path) -> List[ExtractedTable]:
        """Extracts tables using PyMuPDF (fitz) table finder."""
        import fitz

        tables: List[ExtractedTable] = []
        doc = fitz.open(str(pdf_path))

        try:
            for page_index, page in enumerate(doc):
                page_num = page_index + 1
                try:
                    # fitz find_tables() available in PyMuPDF >= 1.23.0
                    tabs = page.find_tables()
                    for t_idx, tab in enumerate(tabs):
                        raw_table = tab.extract()
                        if not raw_table or len(raw_table) < 2:
                            continue

                        extracted = self._process_raw_table(
                            raw_rows=raw_table,
                            page_num=page_num,
                            table_idx=t_idx + 1,
                            bbox=tab.bbox,
                            page_text=page.get_text("text")
                        )
                        if extracted:
                            tables.append(extracted)
                except Exception as page_err:
                    logger.debug(f"fitz table extraction error on page {page_num}: {page_err}")
        finally:
            doc.close()

        return tables

    def _extract_with_pdfplumber(self, pdf_path: Path) -> List[ExtractedTable]:
        """Extracts tables using pdfplumber."""
        import pdfplumber

        tables: List[ExtractedTable] = []
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page_index, page in enumerate(pdf.pages):
                page_num = page_index + 1
                raw_tables = page.extract_tables()
                page_text = page.extract_text() or ""

                for t_idx, raw_table in enumerate(raw_tables):
                    if not raw_table or len(raw_table) < 2:
                        continue

                    extracted = self._process_raw_table(
                        raw_rows=raw_table,
                        page_num=page_num,
                        table_idx=t_idx + 1,
                        bbox=None,
                        page_text=page_text
                    )
                    if extracted:
                        tables.append(extracted)

        return tables

    def _process_raw_table(
        self,
        raw_rows: List[List[Any]],
        page_num: int,
        table_idx: int,
        bbox: Optional[Tuple[float, float, float, float]] = None,
        page_text: str = ""
    ) -> Optional[ExtractedTable]:
        """
        Cleans and formats raw extracted rows into an ExtractedTable object.
        """
        if not raw_rows or len(raw_rows) < 2:
            return None

        # Clean string cells
        cleaned_rows: List[List[str]] = []
        for row in raw_rows:
            cleaned_row = [self._clean_cell(cell) for cell in row]
            # Ignore completely empty rows
            if any(cell for cell in cleaned_row):
                cleaned_rows.append(cleaned_row)

        if len(cleaned_rows) < 2:
            return None

        # Normalize column lengths
        max_cols = max(len(r) for r in cleaned_rows)
        for i in range(len(cleaned_rows)):
            if len(cleaned_rows[i]) < max_cols:
                cleaned_rows[i].extend([""] * (max_cols - len(cleaned_rows[i])))

        # Extract headers (first row, or combined first 2 rows if subheaders present)
        headers = cleaned_rows[0]
        data_rows = cleaned_rows[1:]

        # If header contains default None/empty, auto-assign column names
        for c_idx in range(len(headers)):
            if not headers[c_idx]:
                headers[c_idx] = f"Cột {c_idx + 1}"

        # Detect table title from surrounding text
        title = self._detect_table_title(page_text, headers)

        # Generate Markdown representation
        markdown_str = self._generate_markdown(headers, data_rows, title=title, page_num=page_num)

        # Generate CSV representation
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
            metadata={"num_rows": len(data_rows), "num_cols": len(headers)}
        )

    def _clean_cell(self, cell: Any) -> str:
        """Cleans whitespace, newlines, and unicode artifacts from a cell."""
        if cell is None:
            return ""
        text = str(cell).strip()
        # Replace multiple spaces / newlines within cell with single space
        text = re.sub(r"\s+", " ", text)
        return text

    def _detect_table_title(self, page_text: str, headers: List[str]) -> Optional[str]:
        """Tries to find the formal title of the financial statement table."""
        if not page_text:
            return None

        for pattern in self.TITLE_PATTERNS:
            match = re.search(pattern, page_text, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        # Fallback: Check if first header contains financial terms
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
        """Constructs a standard GitHub Markdown table."""
        lines = []
        if title:
            lines.append(f"### {title} (Trang {page_num})\n")

        # Header line
        header_line = "| " + " | ".join(headers) + " |"
        separator_line = "| " + " | ".join(["---"] * len(headers)) + " |"
        lines.append(header_line)
        lines.append(separator_line)

        # Row lines
        for row in rows:
            row_line = "| " + " | ".join(row) + " |"
            lines.append(row_line)

        return "\n".join(lines)

    def _generate_csv(self, headers: List[str], rows: List[List[str]]) -> str:
        """Generates standard CSV representation using pandas."""
        df = pd.DataFrame(rows, columns=headers)
        output = io.StringIO()
        df.to_csv(output, index=False)
        return output.getvalue()
