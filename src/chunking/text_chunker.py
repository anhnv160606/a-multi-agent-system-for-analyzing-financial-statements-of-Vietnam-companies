"""Text Chunker — chia văn bản thành chunks theo ranh giới ngữ nghĩa.

Input:  List[PageContent]  (từ SplitDocument.texts)
Output: List[Chunk]        (chunk_type="text", level=2)

Đặc điểm:
    - Dùng RecursiveCharacterTextSplitter (langchain) với chunk_size/overlap
      đọc từ configs/settings.yaml.
    - Giữ heading context: detect heading patterns tiếng Việt, prepend heading
      hiện tại vào mỗi chunk để retriever có ngữ cảnh khi trả kết quả.
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.chunking.models import Chunk, ChunkMetadata, ChunkType
from src.utils.logger import get_logger

logger = get_logger("src.chunking.text_chunker")

# ---------------------------------------------------------------------------
# Heading detection patterns (tiếng Việt)
# ---------------------------------------------------------------------------
# Nhận diện heading theo thứ tự ưu tiên giảm dần (heading lớn → nhỏ)
_HEADING_PATTERNS = [
    # PHẦN I, PHẦN II, ... (all caps section)
    re.compile(r"^(PHẦN\s+[IVXLCDM\d]+[.:]*\s*.*)$", re.MULTILINE | re.IGNORECASE),
    # CHƯƠNG 1, CHƯƠNG I, ...
    re.compile(r"^(CHƯƠNG\s+[IVXLCDM\d]+[.:]*\s*.*)$", re.MULTILINE | re.IGNORECASE),
    # I., II., III., IV., V., ... (roman numeral heading)
    re.compile(r"^([IVXLCDM]+\.\s+.+)$", re.MULTILINE),
    # 1., 2., 3., ... (numbered heading, nhưng chỉ khi đủ ngắn ≤ 120 ký tự)
    re.compile(r"^(\d+\.\s+.{3,120})$", re.MULTILINE),
    # Các heading ALL CAPS tiếng Việt (≥4 từ, ≤ 150 ký tự)
    re.compile(
        r"^([A-ZÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬĐÈÉẺẼẸÊẾỀỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴ]"
        r"[A-ZÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬĐÈÉẺẼẸÊẾỀỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴ\s,\-–]{8,150})$",
        re.MULTILINE,
    ),
]


def _load_chunking_config() -> Dict[str, Any]:
    """Load chunking config từ configs/settings.yaml."""
    config_path = Path(__file__).resolve().parent.parent.parent / "configs" / "settings.yaml"
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            return cfg.get("chunking", {})
        except Exception as e:
            logger.warning(f"Không load được settings.yaml: {e}")
    return {}


def _detect_current_heading(text: str) -> Optional[str]:
    """Trích heading cuối cùng (gần nhất) trong đoạn text."""
    last_heading = None
    for pattern in _HEADING_PATTERNS:
        for match in pattern.finditer(text):
            last_heading = match.group(1).strip()
    return last_heading


def _estimate_tokens(text: str) -> int:
    """Ước lượng token count (tiếng Việt ≈ 1 token/từ, English ≈ 0.75 token/word)."""
    return len(text.split())


class TextChunker:
    """Chia text từ PageContent thành các Chunk nhỏ, giữ heading context."""

    def __init__(
        self,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
    ):
        cfg = _load_chunking_config()
        self.chunk_size = chunk_size or cfg.get("text_chunk_size", 1000)
        self.chunk_overlap = chunk_overlap or cfg.get("text_chunk_overlap", 200)

        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separators=["\n\n", "\n", ". ", ", ", " ", ""],
            length_function=len,
        )

        logger.info(
            f"TextChunker khởi tạo: chunk_size={self.chunk_size}, "
            f"chunk_overlap={self.chunk_overlap}"
        )

    def chunk_pages(
        self,
        pages: "List[Any]",
        base_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Chunk]:
        """Chia danh sách PageContent thành List[Chunk].

        Args:
            pages: List[PageContent] từ SplitDocument.texts.
            base_metadata: metadata chung (ticker, report_type, ...) sẽ gắn
                           vào mọi chunk.

        Returns:
            List[Chunk] với chunk_type="text", level=2.
        """
        base_metadata = base_metadata or {}
        all_chunks: List[Chunk] = []

        # Nối toàn bộ text các trang, giữ page boundary
        full_text = ""
        page_boundaries: List[Dict[str, Any]] = []  # (start_idx, page_num, layout_info)

        for page in pages:
            text = page.text.strip()
            if not text:
                continue
            start_idx = len(full_text)
            full_text += text + "\n\n"
            page_boundaries.append({
                "start": start_idx,
                "end": len(full_text),
                "page_num": page.page_num,
                "layout_info": getattr(page, "layout_info", {}),
            })

        if not full_text.strip():
            return []

        # Chia chunks bằng RecursiveCharacterTextSplitter
        raw_chunks = self.splitter.split_text(full_text)

        # Track heading context xuyên suốt document
        current_heading: Optional[str] = None
        char_offset = 0

        for raw_text in raw_chunks:
            # Detect heading trong chunk hiện tại
            detected = _detect_current_heading(raw_text)
            if detected:
                current_heading = detected

            # Prepend heading context nếu chunk không bắt đầu bằng heading
            content = raw_text.strip()
            if current_heading and not raw_text.strip().startswith(current_heading):
                content = f"[{current_heading}]\n{content}"

            # Xác định page_num cho chunk này
            chunk_start = full_text.find(raw_text, char_offset)
            if chunk_start == -1:
                chunk_start = char_offset
            char_offset = chunk_start + len(raw_text)

            page_num = self._find_page_for_position(chunk_start, page_boundaries)

            # Build metadata
            meta = ChunkMetadata(
                chunk_type=ChunkType.TEXT,
                page=page_num,
                **{k: v for k, v in base_metadata.items()
                   if k in ChunkMetadata.model_fields},
            )
            if current_heading:
                meta.section = current_heading

            chunk = Chunk(
                content=content,
                metadata=meta,
                level=2,
                token_count=_estimate_tokens(content),
                embeddable=True,
            )
            all_chunks.append(chunk)

        logger.info(
            f"TextChunker: {len(pages)} trang → {len(all_chunks)} chunks "
            f"(size={self.chunk_size}, overlap={self.chunk_overlap})"
        )
        return all_chunks

    def _find_page_for_position(
        self, position: int, boundaries: List[Dict[str, Any]]
    ) -> Optional[int]:
        """Tìm page_num chứa vị trí ký tự `position` trong full_text."""
        for b in boundaries:
            if b["start"] <= position < b["end"]:
                return b["page_num"]
        # Fallback: trả page cuối
        return boundaries[-1]["page_num"] if boundaries else None
