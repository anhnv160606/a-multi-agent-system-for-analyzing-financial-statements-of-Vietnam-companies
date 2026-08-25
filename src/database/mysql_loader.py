"""
MySQL Financial Data Loader.
Loads structured financial tables from PDF Native, PDF Scan, and CSV into the MySQL `financial_data` table,
normalizing numerical values using `normalize_vn_number` and managing document provenance.
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from src.database.models import CompanyRecord, FinancialDataRecord, SourceDocumentRecord
from src.database.mysql_client import MySQLClient
from src.database.mysql_schema import init_database_schema
from src.ingestion.models import CompanyOverview, ExtractedTable
from src.ingestion.number_utils import normalize_vn_number
from src.utils.logger import get_logger

logger = get_logger("src.database.mysql_loader")


class MySQLLoader:
    """
    Ingests and normalizes financial statement tables into MySQL.
    Handles upserts and links financial data to company profiles and source documents.
    """

    def __init__(self, client: Optional[MySQLClient] = None):
        self.client = client or MySQLClient()
        # Ensure tables exist
        init_database_schema(self.client)

    def register_company(
        self, company: Union[CompanyRecord, CompanyOverview, Dict[str, Any]]
    ) -> bool:
        """
        Inserts or updates a company record in the `companies` table.
        """
        if isinstance(company, (CompanyRecord, CompanyOverview)):
            data = company.model_dump()
        else:
            data = dict(company)

        ticker = data.get("ticker", "").strip().upper()
        if not ticker:
            raise ValueError("Company ticker cannot be empty.")

        company_name = data.get("company_name", ticker)
        industry = data.get("industry")
        sector = data.get("sector")
        exchange = data.get("exchange", "HOSE")
        charter_capital = data.get("charter_capital")
        established_year = data.get("established_year")
        website = data.get("website")
        description = data.get("description")

        sql = """
        INSERT INTO companies 
        (ticker, company_name, industry, sector, exchange, charter_capital, established_year, website, description)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
        company_name = VALUES(company_name),
        industry = VALUES(industry),
        sector = VALUES(sector),
        exchange = VALUES(exchange),
        charter_capital = VALUES(charter_capital),
        established_year = VALUES(established_year),
        website = VALUES(website),
        description = VALUES(description);
        """
        params = (
            ticker,
            company_name,
            industry,
            sector,
            exchange,
            charter_capital,
            established_year,
            website,
            description,
        )

        try:
            self.client.execute(sql, params)
            logger.info(f"Registered/updated company: {ticker} ({company_name})")
            return True
        except Exception as e:
            logger.error(f"Failed to register company {ticker}: {e}")
            raise

    def record_source_document(
        self, doc: Union[SourceDocumentRecord, Dict[str, Any]]
    ) -> int:
        """
        Records a processed document in the `source_documents` table for provenance tracking.
        """
        if isinstance(doc, SourceDocumentRecord):
            data = doc.model_dump()
        else:
            data = dict(doc)

        # Ensure parent company exists
        ticker = data.get("company_ticker", "").strip().upper()
        self.register_company({"ticker": ticker, "company_name": ticker})

        sql = """
        INSERT INTO source_documents 
        (file_name, file_path, company_ticker, fiscal_year, doc_type, report_category, processed_status, total_pages)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        params = (
            data.get("file_name", Path(data.get("file_path", "unknown")).name),
            data.get("file_path", ""),
            ticker,
            data.get("fiscal_year"),
            data.get("doc_type", "native"),
            data.get("report_category", "bctc"),
            data.get("processed_status", "completed"),
            data.get("total_pages", 1),
        )

        try:
            rowcount = self.client.execute(sql, params)
            logger.info(f"Recorded source document: {params[0]} for ticker {ticker}")
            return rowcount
        except Exception as e:
            logger.error(f"Failed to record source document: {e}")
            return 0

    def load_extracted_tables(
        self,
        tables: List[ExtractedTable],
        ticker: str,
        fiscal_year: int,
        source_file: str,
        quarter: int = 0,
        doc_type: str = "native",
    ) -> int:
        """
        Processes a list of ExtractedTable objects and batch-upserts them into `financial_data`.
        """
        ticker = ticker.strip().upper()
        # Ensure company is registered
        self.register_company({"ticker": ticker, "company_name": ticker})

        total_inserted = 0
        records_to_insert: List[Tuple] = []

        for table in tables:
            report_type = self._classify_report_type(table.title, table.headers)
            engine = table.extraction_engine or "fitz"
            page_num = table.page_num

            # Determine column positions
            item_col, code_col, value_cols = self._detect_table_columns(table.headers, table.rows)

            for row in table.rows:
                if len(row) <= item_col:
                    continue

                line_item = row[item_col].strip()
                if not line_item or line_item.lower() in ("chỉ tiêu", "mục", "stt", "item"):
                    continue

                line_code = row[code_col].strip() if (code_col is not None and len(row) > code_col) else ""

                # Extract each value column (e.g. Current Year, Previous Year)
                for col_idx, col_name, target_year in value_cols:
                    if col_idx >= len(row):
                        continue

                    raw_val = row[col_idx].strip()
                    num_val = normalize_vn_number(raw_val)

                    # Determine unit
                    unit = "VND"
                    if "%" in raw_val:
                        unit = "%"

                    records_to_insert.append((
                        ticker,
                        target_year or fiscal_year,
                        quarter,
                        report_type,
                        line_code,
                        line_item,
                        num_val,
                        raw_val,
                        unit,
                        Path(source_file).name,
                        doc_type,
                        engine,
                        page_num,
                    ))

        if records_to_insert:
            upsert_sql = """
            INSERT INTO financial_data 
            (ticker, fiscal_year, fiscal_quarter, report_type, line_code, line_item, value, raw_value, unit, source_file, doc_type, extraction_engine, page_number)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
            value = VALUES(value),
            raw_value = VALUES(raw_value),
            unit = VALUES(unit),
            source_file = VALUES(source_file),
            doc_type = VALUES(doc_type),
            extraction_engine = VALUES(extraction_engine),
            page_number = VALUES(page_number);
            """
            try:
                total_inserted = self.client.execute_many(upsert_sql, records_to_insert)
                logger.info(
                    f"Successfully loaded {len(records_to_insert)} financial items for {ticker} ({fiscal_year}) into MySQL."
                )
            except Exception as e:
                logger.error(f"Error loading tables into MySQL for {ticker}: {e}")
                raise

        return len(records_to_insert)

    def get_financial_data(
        self,
        ticker: str,
        fiscal_year: Optional[int] = None,
        report_type: Optional[str] = None,
        line_item_like: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Queries financial data records for downstream Agent SQL or Analysis.
        """
        ticker = ticker.strip().upper()
        sql = "SELECT * FROM financial_data WHERE ticker = %s"
        params: List[Any] = [ticker]

        if fiscal_year is not None:
            sql += " AND fiscal_year = %s"
            params.append(fiscal_year)

        if report_type is not None:
            sql += " AND report_type = %s"
            params.append(report_type)

        if line_item_like:
            sql += " AND line_item LIKE %s"
            params.append(f"%{line_item_like}%")

        sql += " ORDER BY fiscal_year DESC, id ASC"
        return self.client.fetch_all(sql, params)

    def _classify_report_type(self, title: Optional[str], headers: List[str]) -> str:
        """Determines report category: balance_sheet, income_statement, cash_flow, notes."""
        text_context = (title or "") + " " + " ".join(headers)
        text_lower = text_context.lower()

        if any(w in text_lower for w in ("cân đối kế toán", "tình hình tài chính", "balance sheet", "tài sản", "nguồn vốn")):
            return "balance_sheet"
        elif any(w in text_lower for w in ("kết quả kinh doanh", "kết quả hoạt động", "income statement", "doanh thu", "lợi nhuận")):
            return "income_statement"
        elif any(w in text_lower for w in ("lưu chuyển tiền", "cash flow", "tiền tệ")):
            return "cash_flow"
        elif "thuyết minh" in text_lower:
            return "notes"
        return "financial_report"

    def _detect_table_columns(
        self, headers: List[str], rows: List[List[str]]
    ) -> Tuple[int, Optional[int], List[Tuple[int, str, Optional[int]]]]:
        """
        Detects index for line_item column, code column, and numerical value columns.
        Returns: (item_col_idx, code_col_idx, [(val_col_idx, col_name, target_year)])
        """
        item_col = 0
        code_col = None
        value_cols: List[Tuple[int, str, Optional[int]]] = []

        for idx, h in enumerate(headers):
            h_lower = h.lower()
            if any(k in h_lower for k in ("chỉ tiêu", "tên chỉ tiêu", "item", "nội dung")):
                item_col = idx
            elif any(k in h_lower for k in ("mã số", "mã", "code")):
                code_col = idx
            elif any(k in h_lower for k in ("thuyết minh", "tm")):
                continue
            else:
                # Check for year in column header
                year_match = re.search(r"20\d\d", h)
                target_year = int(year_match.group(0)) if year_match else None
                value_cols.append((idx, h, target_year))

        # Fallback if no specific value cols detected: inspect rows
        if not value_cols and rows:
            for c_idx in range(len(headers)):
                if c_idx != item_col and c_idx != code_col:
                    value_cols.append((c_idx, headers[c_idx], None))

        return item_col, code_col, value_cols
