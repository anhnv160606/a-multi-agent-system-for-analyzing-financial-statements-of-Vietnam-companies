"""
Database Schema Definitions (DDL) and Table Initialization.
Provides DDL for MySQL 8.0 and SQLite (fallback) for companies, source documents, and financial data.
"""

from typing import Any, List
from src.utils.logger import get_logger

logger = get_logger("src.database.mysql_schema")

# ==============================================================================
# MySQL 8.0 DDL Statements
# ==============================================================================

MYSQL_TABLE_COMPANIES = """
CREATE TABLE IF NOT EXISTS companies (
    ticker VARCHAR(10) PRIMARY KEY,
    company_name VARCHAR(255) NOT NULL,
    industry VARCHAR(100),
    sector VARCHAR(100),
    exchange VARCHAR(20) DEFAULT 'HOSE',
    charter_capital DOUBLE,
    established_year INT,
    website VARCHAR(255),
    description TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_company_industry (industry),
    INDEX idx_company_exchange (exchange)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

MYSQL_TABLE_SOURCE_DOCUMENTS = """
CREATE TABLE IF NOT EXISTS source_documents (
    id INT AUTO_INCREMENT PRIMARY KEY,
    file_name VARCHAR(255) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    company_ticker VARCHAR(10) NOT NULL,
    fiscal_year INT,
    doc_type VARCHAR(50) NOT NULL,
    report_category VARCHAR(100),
    processed_status VARCHAR(50) DEFAULT 'completed',
    total_pages INT,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (company_ticker) REFERENCES companies(ticker) ON DELETE CASCADE,
    INDEX idx_doc_ticker_year (company_ticker, fiscal_year),
    INDEX idx_doc_type (doc_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

MYSQL_TABLE_FINANCIAL_DATA = """
CREATE TABLE IF NOT EXISTS financial_data (
    id INT AUTO_INCREMENT PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    fiscal_year INT NOT NULL,
    fiscal_quarter INT DEFAULT 0,
    report_type VARCHAR(50) NOT NULL,
    line_code VARCHAR(50) DEFAULT '',
    line_item VARCHAR(255) NOT NULL,
    value DOUBLE,
    raw_value VARCHAR(255),
    unit VARCHAR(50) DEFAULT 'VND',
    source_file VARCHAR(255),
    doc_type VARCHAR(50) DEFAULT 'native',
    extraction_engine VARCHAR(50) DEFAULT 'fitz',
    page_number INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ticker) REFERENCES companies(ticker) ON DELETE CASCADE,
    UNIQUE KEY uq_fin_entry (ticker, fiscal_year, fiscal_quarter, report_type, line_code, line_item),
    INDEX idx_fin_search (ticker, fiscal_year, report_type),
    INDEX idx_fin_item (ticker, line_item)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

# ==============================================================================
# SQLite Compatible Fallback DDL Statements
# ==============================================================================

SQLITE_TABLE_COMPANIES = """
CREATE TABLE IF NOT EXISTS companies (
    ticker TEXT PRIMARY KEY,
    company_name TEXT NOT NULL,
    industry TEXT,
    sector TEXT,
    exchange TEXT DEFAULT 'HOSE',
    charter_capital REAL,
    established_year INTEGER,
    website TEXT,
    description TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

SQLITE_TABLE_SOURCE_DOCUMENTS = """
CREATE TABLE IF NOT EXISTS source_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    company_ticker TEXT NOT NULL,
    fiscal_year INTEGER,
    doc_type TEXT NOT NULL,
    report_category TEXT,
    processed_status TEXT DEFAULT 'completed',
    total_pages INTEGER,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (company_ticker) REFERENCES companies(ticker) ON DELETE CASCADE
);
"""

SQLITE_TABLE_FINANCIAL_DATA = """
CREATE TABLE IF NOT EXISTS financial_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    fiscal_year INTEGER NOT NULL,
    fiscal_quarter INTEGER DEFAULT 0,
    report_type TEXT NOT NULL,
    line_code TEXT DEFAULT '',
    line_item TEXT NOT NULL,
    value REAL,
    raw_value TEXT,
    unit TEXT DEFAULT 'VND',
    source_file TEXT,
    doc_type TEXT DEFAULT 'native',
    extraction_engine TEXT DEFAULT 'fitz',
    page_number INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ticker) REFERENCES companies(ticker) ON DELETE CASCADE,
    UNIQUE(ticker, fiscal_year, fiscal_quarter, report_type, line_code, line_item)
);
"""


def get_schema_statements(is_sqlite: bool = False) -> List[str]:
    """Returns the ordered list of DDL statements based on database dialect."""
    if is_sqlite:
        return [
            SQLITE_TABLE_COMPANIES,
            SQLITE_TABLE_SOURCE_DOCUMENTS,
            SQLITE_TABLE_FINANCIAL_DATA,
        ]
    return [
        MYSQL_TABLE_COMPANIES,
        MYSQL_TABLE_SOURCE_DOCUMENTS,
        MYSQL_TABLE_FINANCIAL_DATA,
    ]


def init_database_schema(client: Any) -> bool:
    """
    Executes DDL statements to ensure all required tables and indexes exist.
    """
    is_sqlite = getattr(client, "is_sqlite", False)
    statements = get_schema_statements(is_sqlite=is_sqlite)
    logger.info(f"Initializing database schema ({'SQLite' if is_sqlite else 'MySQL'})...")

    try:
        for stmt in statements:
            client.execute(stmt)
        logger.info("Database schema initialized successfully.")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize database schema: {e}")
        raise
