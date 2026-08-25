"""Pydantic Data Models cho Chunking Pipeline.

Models ở đây đại diện cho đơn vị nội dung SAU khi đã chia nhỏ (chunk) từ
SplitDocument (ingestion layer). Mỗi Chunk mang đầy đủ metadata để
downstream retriever có thể filter chính xác theo ticker, năm, loại báo cáo.
"""

import uuid
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ==============================================================================
# Enums
# ==============================================================================

class ChunkType(str, Enum):
    """Phân loại nội dung của chunk."""
    TEXT = "text"
    TABLE = "table"
    TABLE_SUMMARY = "table_summary"


class RelationType(str, Enum):
    """Loại quan hệ giữa 2 chunks."""
    PARENT_CHILD = "parent_child"


# ==============================================================================
# Chunk Metadata
# ==============================================================================

class ChunkMetadata(BaseModel):
    """Metadata gắn kèm mỗi chunk — dùng cho filtered retrieval."""
    ticker: Optional[str] = None
    year: Optional[int] = None
    quarter: Optional[int] = None
    report_type: Optional[str] = None        # "bctc" | "bao_cao_thuong_nien" | "bien_ban_dhcd"
    section: Optional[str] = None            # Tên section/heading cha
    page: Optional[int] = None
    source_file: Optional[str] = None
    doc_type: Optional[str] = None           # "csv" | "native" | "scan"
    chunk_type: str = ChunkType.TEXT         # "text" | "table" | "table_summary"
    extraction_engine: Optional[str] = None  # "fitz" | "ppstructure" | "csv" | ...


# ==============================================================================
# Chunk
# ==============================================================================

def _gen_chunk_id() -> str:
    return f"chunk_{uuid.uuid4().hex[:12]}"


class Chunk(BaseModel):
    """Đơn vị nội dung nhỏ nhất sẵn sàng để embed + index vào vector store."""
    chunk_id: str = Field(default_factory=_gen_chunk_id)
    content: str
    metadata: ChunkMetadata = Field(default_factory=ChunkMetadata)
    parent_id: Optional[str] = None
    level: int = 2                       # 0=section, 1=sub-section, 2=detail
    token_count: int = 0
    embeddable: bool = True              # False → lưu nhưng không embed (bảng gốc lớn)


# ==============================================================================
# Chunk Relationship
# ==============================================================================

class ChunkRelationship(BaseModel):
    """Quan hệ giữa 2 chunks (parent-child)."""
    source_chunk_id: str
    target_chunk_id: str
    relation_type: RelationType = RelationType.PARENT_CHILD


# ==============================================================================
# Embedding Record
# ==============================================================================

class EmbeddingRecord(BaseModel):
    """Bản ghi embedding đã tính cho 1 chunk."""
    chunk_id: str
    content_hash: str
    embedding: List[float] = Field(default_factory=list)
    model_name: str = ""
    dim: int = 0
