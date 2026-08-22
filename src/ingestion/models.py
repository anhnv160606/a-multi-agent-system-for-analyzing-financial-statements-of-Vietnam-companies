"""
Pydantic Data Models for Data Ingestion Pipeline.
Standardizes data structures across PDF extraction, Market API, and Validation.
"""

from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field


# ==============================================================================
# PDF Ingestion Models
# ==============================================================================

class PageContent(BaseModel):
    """Represents raw text content and layout extracted from a PDF page."""
    page_num: int
    text: str
    layout_info: Dict[str, Any] = Field(default_factory=dict)


class ExtractedTable(BaseModel):
    """Represents a structured table extracted from a PDF document."""
    page_num: int
    table_index: int
    headers: List[str] = Field(default_factory=list)
    rows: List[List[str]] = Field(default_factory=list)
    markdown: str = ""
    csv: str = ""
    bbox: Optional[Tuple[float, float, float, float]] = None
    title: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_dict_records(self) -> List[Dict[str, str]]:
        """Converts table rows to a list of dictionary records keyed by headers."""
        if not self.headers or not self.rows:
            return []
        records = []
        for row in self.rows:
            # Pad row if shorter than headers
            padded_row = row + [""] * (len(self.headers) - len(row))
            records.append({self.headers[i]: padded_row[i] for i in range(len(self.headers))})
        return records


class ExtractedImage(BaseModel):
    """Represents an image extracted from a PDF page."""
    page_num: int
    image_index: int
    image_path: Optional[str] = None
    image_bytes: Optional[bytes] = None
    width: int
    height: int
    format: str = "png"
    bbox: Optional[Tuple[float, float, float, float]] = None
    image_type: str = "general"  # "chart", "diagram", "general"


class ImageProcessingResult(BaseModel):
    """Result of Vision LLM processing on an extracted chart/diagram."""
    image_index: int
    page_num: int
    caption: str
    chart_data: Optional[str] = None  # Markdown table format if it's a chart
    image_type: str = "general"
    confidence: float = 1.0


class SplitDocument(BaseModel):
    """Unified container for all 3 extracted streams (Text, Tables, Images)."""
    source_file: str
    ticker: Optional[str] = None
    fiscal_year: Optional[int] = None
    report_type: Optional[str] = None
    texts: List[PageContent] = Field(default_factory=list)
    tables: List[ExtractedTable] = Field(default_factory=list)
    images: List[ExtractedImage] = Field(default_factory=list)
    image_results: List[ImageProcessingResult] = Field(default_factory=list)


# ==============================================================================
# Market API Models (VNStock / Free Open Endpoints)
# ==============================================================================

class CompanyOverview(BaseModel):
    """Overview information of a listed company."""
    ticker: str
    company_name: str
    industry: Optional[str] = None
    sector: Optional[str] = None
    exchange: Optional[str] = None  # HOSE, HNX, UPCOM
    charter_capital: Optional[float] = None
    established_year: Optional[int] = None
    website: Optional[str] = None
    description: Optional[str] = None


class StockPriceItem(BaseModel):
    """OHLCV historical price record for a single trading day."""
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class StockPriceHistory(BaseModel):
    """Collection of historical price records for a ticker."""
    ticker: str
    records: List[StockPriceItem] = Field(default_factory=list)


class FinancialRatioSummary(BaseModel):
    """Financial ratios and key fundamental figures from market API."""
    ticker: str
    year: Optional[int] = None
    quarter: Optional[int] = None
    pe: Optional[float] = None
    pb: Optional[float] = None
    roe: Optional[float] = None
    roa: Optional[float] = None
    eps: Optional[float] = None
    market_cap: Optional[float] = None
    debt_to_equity: Optional[float] = None
    revenue: Optional[float] = None
    net_profit: Optional[float] = None
    total_assets: Optional[float] = None


class NewsItem(BaseModel):
    """Market and company news article."""
    id: Optional[str] = None
    ticker: str
    title: str
    summary: Optional[str] = None
    publish_date: Optional[str] = None
    source: Optional[str] = None
    url: Optional[str] = None


# ==============================================================================
# Cross-Validation Models
# ==============================================================================

class MismatchDetail(BaseModel):
    """Details of a numerical discrepancy between PDF and API."""
    metric: str
    pdf_value: float
    api_value: float
    difference: float
    variance_pct: float
    status: str  # "MATCH", "MISMATCH_MINOR", "MISMATCH_MAJOR"


class ValidationResult(BaseModel):
    """Cross-validation summary report between PDF extraction and Market API."""
    ticker: str
    fiscal_year: int
    is_valid: bool
    confidence_score: float  # Range: 0.0 to 1.0
    matched_items: List[str] = Field(default_factory=list)
    mismatches: List[MismatchDetail] = Field(default_factory=list)
    summary_notes: str = ""
