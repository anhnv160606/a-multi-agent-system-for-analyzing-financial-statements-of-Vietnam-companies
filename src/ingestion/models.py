"""Pydantic Data Models dùng chung cho Data Ingestion Pipeline.

Quy ước quan trọng:
    - Mọi model đại diện cho 1 đơn vị nội dung trên trang PDF đều có field
      `extraction_engine` (vd: "fitz", "pdfplumber", "ppstructure",
      "tesseract") -- bắt buộc set khi tạo object, để khi phát hiện dữ liệu
      sai, biết ngay cần debug ở module nào.
    - `rows`/`text` LUÔN là string thô, CHƯA chuẩn hóa số liệu (dấu chấm
      nghìn, ngoặc âm...). Việc chuẩn hóa số dùng number_utils.py ở tầng
      sau (khi load vào SQL), không normalize ngay tại model này -- để giữ
      bản ghi trung thực với PDF gốc, dễ đối chiếu khi debug sai lệch.
"""

from typing import Any, Callable, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field


# ==============================================================================
# PDF Ingestion Models (dùng chung cho cả native/ và scan/)
# ==============================================================================

class PageContent(BaseModel):
    """Text thuần túy của một trang -- KHÔNG bao gồm nội dung nằm trong bảng.

    Với PDF native: do text_extractor_native.py sinh ra, đã loại trừ vùng
    bảng/ảnh (xem pdf_layout.py).
    Với PDF scan: do text_extractor_scan.py sinh ra (Tesseract/PaddleOCR),
    CHỈ áp dụng cho trang đã xác nhận không có bảng; nếu trang có bảng,
    phần text đi kèm bảng do table_extractor_scan.py trả về (PPStructure
    tách sẵn), không đi qua model này.
    """
    page_num: int
    text: str
    extraction_engine: str  # "fitz" | "pdfplumber" | "tesseract" | "paddleocr" | "ppstructure"
    layout_info: Dict[str, Any] = Field(default_factory=dict)


class ExtractedTable(BaseModel):
    """Một bảng đã được trích và làm sạch (raw string, chưa chuẩn hóa số)."""
    page_num: int
    table_index: int
    headers: List[str] = Field(default_factory=list)
    rows: List[List[str]] = Field(default_factory=list)
    markdown: str = ""
    csv: str = ""
    bbox: Optional[Tuple[float, float, float, float]] = None
    title: Optional[str] = None
    extraction_engine: str  # "fitz" | "pdfplumber" | "ppstructure"
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_dict_records(self) -> List[Dict[str, str]]:
        """Chuyển rows thành list dict theo headers (vẫn raw string)."""
        if not self.headers or not self.rows:
            return []
        records = []
        for row in self.rows:
            padded_row = row + [""] * (len(self.headers) - len(row))
            records.append({self.headers[i]: padded_row[i] for i in range(len(self.headers))})
        return records

    def to_normalized_records(
        self,
        normalize_fn: Callable[[str], Optional[float]],
        min_success_ratio: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """Chuyển rows thành list dict theo headers, đồng thời chuẩn hóa số liệu
        bằng normalize_fn (vd: number_utils.parse_number), chỉ chuẩn hóa các cột
        có chứa dữ liệu số.
        """
        if not self.headers or not self.rows:
            return []

        padded_rows = [
            row + [""] * (len(self.headers) - len(row)) for row in self.rows
        ]

        numeric_col_idx = set()
        for col_idx in range(len(self.headers)):
            col_values = [row[col_idx] for row in padded_rows]
            non_empty = [v for v in col_values if v.strip()]
            if not non_empty:
                continue
            success = sum(1 for v in non_empty if normalize_fn(v) is not None)
            if success / len(non_empty) >= min_success_ratio:
                numeric_col_idx.add(col_idx)

        normalized: List[Dict[str, Any]] = []
        for row in padded_rows:
            record: Dict[str, Any] = {}
            for i, header in enumerate(self.headers):
                value = row[i]
                record[header] = normalize_fn(value) if i in numeric_col_idx else value
            normalized.append(record)

        return normalized


class ExtractedImage(BaseModel):
    """Một ảnh nhúng trích từ PDF native"""
    page_num: int
    image_index: int
    file_path: Optional[str] = None
    image_bytes: Optional[bytes] = None
    width: int
    height: int
    ext: str = "png"
    bbox: Optional[Tuple[float, float, float, float]] = None
    image_type: str = "general"  # "chart" | "diagram" | "general"
    extraction_engine: str = "fitz"


class ImageProcessingResult(BaseModel):
    """Kết quả Vision LLM xử lý ảnh (biểu đồ/sơ đồ) đã trích ra."""
    image_index: int
    page_num: int
    caption: str
    chart_data: Optional[str] = None  # dạng Markdown table nếu là biểu đồ
    image_type: str = "general"
    confidence: float = 1.0


class SplitDocument(BaseModel):
    """Container thống nhất cho toàn bộ nội dung trích từ 1 file PDF,
    bất kể file đó qua luồng native/ hay scan/ -- đây là điểm hội tụ mà cả
    2 nhóm cùng nhắm tới khi ghép kết quả cho downstream (SQL/Vector DB)."""
    source_file: str
    doc_type: str  # "native" | "scan"
    report_category: Optional[str] = None  # "bctc" | "bao_cao_thuong_nien" | "bien_ban_dhcd"
    ticker: Optional[str] = None
    fiscal_year: Optional[int] = None
    texts: List[PageContent] = Field(default_factory=list)
    tables: List[ExtractedTable] = Field(default_factory=list)
    images: List[ExtractedImage] = Field(default_factory=list)
    image_results: List[ImageProcessingResult] = Field(default_factory=list)


# ==============================================================================
# Market API Models (vnstock)
# ==============================================================================

class CompanyOverview(BaseModel):
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
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class StockPriceHistory(BaseModel):
    ticker: str
    records: List[StockPriceItem] = Field(default_factory=list)


class FinancialRatioSummary(BaseModel):
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
    metric: str
    pdf_value: float
    api_value: float
    difference: float
    variance_pct: float
    status: str  # "MATCH" | "MISMATCH_MINOR" | "MISMATCH_MAJOR"


class ValidationResult(BaseModel):
    ticker: str
    fiscal_year: int
    is_valid: bool
    confidence_score: float  # 0.0 - 1.0
    matched_items: List[str] = Field(default_factory=list)
    mismatches: List[MismatchDetail] = Field(default_factory=list)
    summary_notes: str = ""