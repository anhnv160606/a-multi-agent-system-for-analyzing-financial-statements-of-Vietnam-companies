"""Provenance Tracker: Source & Audit Trail Logging (Task 5.9).

Ghi nhận và truy vết nguồn gốc của từng con số và kết luận:
    - Agent nào tạo ra.
    - Chunk văn bản nào (Chunk ID, số trang PDF).
    - Dòng số liệu nào trong SQL (Bảng, chỉ tiêu, năm).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ProvenanceRecord(BaseModel):
    """Bản ghi truy vết nguồn gốc dữ liệu."""
    agent: str
    action: str = "executed"
    source_type: str = "sql_or_vector"  # "sql", "vector_chunk", "pdf_page", "llm_synthesis"
    source_reference: Optional[str] = None
    page_number: Optional[int] = None
    confidence: float = 1.0
    details: Dict[str, Any] = Field(default_factory=dict)


def format_provenance_summary(provenance_list: List[Dict[str, Any]]) -> str:
    """Định dạng danh sách provenance thành chuỗi báo cáo kiểm toán dễ đọc."""
    if not provenance_list:
        return "Không có bản ghi truy vết nguồn gốc."

    lines = ["=== BẢNG TRUY VẾT NGUỒN GỐC DỮ LIỆU (AUDIT TRAIL) ==="]
    for idx, entry in enumerate(provenance_list, 1):
        agent_name = entry.get("agent", "Unknown Agent")
        score = entry.get("confidence", entry.get("score", entry.get("confidence_score", "N/A")))
        details = ", ".join(f"{k}={v}" for k, v in entry.items() if k not in ("agent", "confidence", "score", "confidence_score"))
        lines.append(f"{idx}. [{agent_name}] Confidence: {score} | Chi tiết: {details}")

    return "\n".join(lines)
