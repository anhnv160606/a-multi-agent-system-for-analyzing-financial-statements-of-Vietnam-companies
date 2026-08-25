"""
Data Models and Entity Schemas for the Database Layer (MySQL & ChromaDB).
Defines records for companies, structured financial data, source document provenance, and vector storage.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CompanyRecord(BaseModel):
    """Represents a listed company profile stored in the MySQL `companies` table."""
    ticker: str = Field(..., max_length=10, description="Mã cổ phiếu (vd: VNM, FPT, HPG)")
    company_name: str = Field(..., description="Tên đầy đủ của doanh nghiệp")
    industry: Optional[str] = Field(None, description="Ngành nghề kinh doanh chính")
    sector: Optional[str] = Field(None, description="Lĩnh vực / Nhóm ngành")
    exchange: str = Field("HOSE", description="Sàn giao dịch (HOSE, HNX, UPCOM)")
    charter_capital: Optional[float] = Field(None, description="Vốn điều lệ (VND)")
    established_year: Optional[int] = Field(None, description="Năm thành lập")
    website: Optional[str] = Field(None, description="Website công ty")
    description: Optional[str] = Field(None, description="Tóm tắt giới thiệu doanh nghiệp")
    updated_at: datetime = Field(default_factory=datetime.now)


class FinancialDataRecord(BaseModel):
    """
    Represents a single standardized financial statement item stored in the MySQL `financial_data` table.
    Supports provenance tracking back to the source PDF/CSV and page number.
    """
    id: Optional[int] = None
    ticker: str = Field(..., max_length=10, description="Mã chứng khoán")
    fiscal_year: int = Field(..., description="Năm tài chính (vd: 2023)")
    fiscal_quarter: Optional[int] = Field(None, description="Quý (1, 2, 3, 4 hoặc None nếu là cả năm)")
    report_type: str = Field(
        ...,
        description="Loại báo cáo ('balance_sheet', 'income_statement', 'cash_flow', 'notes')"
    )
    line_code: Optional[str] = Field(None, description="Mã số chỉ tiêu theo chuẩn BCTC (vd: '100', '110', '60')")
    line_item: str = Field(..., description="Tên chỉ tiêu (vd: 'Doanh thu thuần', 'Tổng cộng tài sản')")
    value: Optional[float] = Field(None, description="Giá trị số thực đã chuẩn hóa (float)")
    raw_value: Optional[str] = Field(None, description="Giá trị chuỗi gốc đọc từ tài liệu")
    unit: str = Field("VND", description="Đơn vị tiền tệ (vd: 'VND', 'triệu VND', '%')")
    source_file: Optional[str] = Field(None, description="Tên file nguồn gốc")
    doc_type: str = Field("native", description="Nguồn gốc tài liệu ('native', 'scan', 'csv')")
    extraction_engine: str = Field("fitz", description="Engine trích xuất ('fitz', 'ppstructure', 'csv')")
    page_number: Optional[int] = Field(None, description="Số trang chứa chỉ tiêu này trong file PDF")
    created_at: datetime = Field(default_factory=datetime.now)


class SourceDocumentRecord(BaseModel):
    """
    Tracks metadata and ingestion provenance of raw files in the MySQL `source_documents` table.
    """
    id: Optional[int] = None
    file_name: str = Field(..., description="Tên file tài liệu gốc")
    file_path: str = Field(..., description="Đường dẫn lưu trữ file trên hệ thống")
    company_ticker: str = Field(..., max_length=10, description="Mã công ty liên quan")
    fiscal_year: Optional[int] = Field(None, description="Năm tài chính của tài liệu")
    doc_type: str = Field(..., description="Phân loại: 'native', 'scan', 'csv'")
    report_category: Optional[str] = Field(
        None, description="Loại tài liệu: 'bctc', 'annual_report', 'agm_minutes', 'market_data'"
    )
    processed_status: str = Field("completed", description="'pending', 'processing', 'completed', 'failed'")
    total_pages: Optional[int] = Field(None, description="Tổng số trang")
    uploaded_at: datetime = Field(default_factory=datetime.now)


class VectorDocumentRecord(BaseModel):
    """Represents a text chunk or table summary indexed in Vector DB (ChromaDB)."""
    id: str = Field(..., description="Unique Chunk ID")
    document: str = Field(..., description="Nội dung văn bản / tóm tắt bảng")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata kèm theo chunk")
    embedding: Optional[List[float]] = Field(None, description="Vector embedding của nội dung")


class VectorSearchResult(BaseModel):
    """Search result returned from Vector DB queries."""
    id: str
    document: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    distance: float = Field(0.0, description="Khoảng cách cosine / l2 (càng nhỏ càng khớp)")
    similarity: float = Field(1.0, description="Điểm tương đồng (1.0 - distance)")
