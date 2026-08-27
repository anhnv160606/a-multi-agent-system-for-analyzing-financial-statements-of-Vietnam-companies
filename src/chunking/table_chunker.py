"""Table Chunker — xử lý bảng: giữ nguyên bảng nhỏ, tạo summary cho bảng lớn.

Input:  List[ExtractedTable]  (từ SplitDocument.tables)
Output: List[Chunk]

Logic:
    - Bảng ≤ threshold tokens → giữ nguyên markdown → 1 Chunk (chunk_type="table")
    - Bảng > threshold → gọi Gemini tạo summary:
        * 1 Chunk summary (chunk_type="table_summary", embeddable=True)
        * 1 Chunk bảng gốc (chunk_type="table", embeddable=False) — lưu để trả khi retrieve
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from src.chunking.models import Chunk, ChunkMetadata, ChunkType
from src.utils.logger import get_logger

logger = get_logger("src.chunking.table_chunker")


def _load_table_config() -> Dict[str, Any]:
    """Load table chunking config từ settings.yaml."""
    config_path = Path(__file__).resolve().parent.parent.parent / "configs" / "settings.yaml"
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            return cfg.get("chunking", {})
        except Exception:
            pass
    return {}


def _estimate_tokens(text: str) -> int:
    """Ước lượng token count."""
    return len(text.split())


class TableChunker:
    """Xử lý bảng từ ExtractedTable thành Chunk(s)."""

    def __init__(
        self,
        summary_threshold: Optional[int] = None,
        api_key: Optional[str] = None,
        model_name: str = "gemini-3.1-flash-lite",
    ):
        cfg = _load_table_config()
        self.summary_threshold = summary_threshold or cfg.get("table_summary_threshold", 2000)
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        self.model_name = model_name
        self._genai_model = None

        logger.info(
            f"TableChunker khởi tạo: threshold={self.summary_threshold} tokens, "
            f"model={self.model_name}"
        )

    def _init_genai(self):
        """Lazy-init Gemini client."""
        if self._genai_model is not None:
            return self._genai_model

        if not self.api_key:
            logger.warning("Không có GOOGLE_API_KEY → table summary sẽ dùng fallback.")
            return None

        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self._genai_model = genai.GenerativeModel(self.model_name)
            logger.info(f"Gemini model '{self.model_name}' khởi tạo thành công.")
            return self._genai_model
        except Exception as e:
            logger.warning(f"Không khởi tạo được Gemini: {e}")
            return None

    def chunk_tables(
        self,
        tables: "List[Any]",
        base_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Chunk]:
        """Chuyển danh sách ExtractedTable → List[Chunk].

        Args:
            tables: List[ExtractedTable] từ SplitDocument.tables.
            base_metadata: metadata chung gắn vào mọi chunk.
        """
        base_metadata = base_metadata or {}
        all_chunks: List[Chunk] = []

        for table in tables:
            chunks = self._process_single_table(table, base_metadata)
            all_chunks.extend(chunks)

        logger.info(f"TableChunker: {len(tables)} bảng → {len(all_chunks)} chunks")
        return all_chunks

    def _process_single_table(
        self,
        table: "Any",
        base_metadata: Dict[str, Any],
    ) -> List[Chunk]:
        """Xử lý 1 ExtractedTable → 1 hoặc 2 Chunks."""
        # Chuẩn bị markdown content
        markdown = table.markdown.strip() if table.markdown else ""
        if not markdown:
            # Fallback: tạo markdown từ headers + rows
            markdown = self._build_markdown(table)

        if not markdown:
            return []

        token_count = _estimate_tokens(markdown)

        # Thêm title context nếu có
        title_prefix = ""
        if table.title:
            title_prefix = f"### {table.title}\n\n"

        # Build base chunk metadata
        table_meta_dict = getattr(table, "metadata", {}) or {}
        meta_kwargs = {
            k: v for k, v in base_metadata.items()
            if k in ChunkMetadata.model_fields
        }
        meta_kwargs["page"] = table.page_num
        meta_kwargs["extraction_engine"] = table.extraction_engine

        if token_count <= self.summary_threshold:
            # ---------- Bảng nhỏ: giữ nguyên ----------
            content = title_prefix + markdown
            meta = ChunkMetadata(chunk_type=ChunkType.TABLE, **meta_kwargs)
            return [Chunk(
                content=content,
                metadata=meta,
                level=2,
                token_count=token_count,
                embeddable=True,
            )]
        else:
            # ---------- Bảng lớn: summary + bảng gốc ----------
            chunks: List[Chunk] = []

            # Chunk 1: Summary (embeddable)
            summary = self._generate_summary(markdown, table.title)
            summary_content = title_prefix + summary
            summary_meta = ChunkMetadata(
                chunk_type=ChunkType.TABLE_SUMMARY, **meta_kwargs
            )
            summary_chunk = Chunk(
                content=summary_content,
                metadata=summary_meta,
                level=2,
                token_count=_estimate_tokens(summary_content),
                embeddable=True,
            )
            chunks.append(summary_chunk)

            # Chunk 2: Bảng gốc (không embed, lưu để trả khi retrieve)
            original_content = title_prefix + markdown
            original_meta = ChunkMetadata(
                chunk_type=ChunkType.TABLE, **meta_kwargs
            )
            original_chunk = Chunk(
                content=original_content,
                metadata=original_meta,
                level=2,
                token_count=token_count,
                embeddable=False,  # Không embed, chỉ lưu
                parent_id=summary_chunk.chunk_id,
            )
            chunks.append(original_chunk)

            logger.info(
                f"Bảng trang {table.page_num} vượt threshold "
                f"({token_count} > {self.summary_threshold}) → tạo summary"
            )
            return chunks

    def _generate_summary(self, markdown: str, title: Optional[str] = None) -> str:
        """Gọi Gemini tạo summary cho bảng lớn. Fallback nếu không có API."""
        model = self._init_genai()

        if model is None:
            return self._fallback_summary(markdown, title)

        title_hint = f" (tiêu đề: {title})" if title else ""
        prompt = (
            f"Bạn là chuyên gia phân tích báo cáo tài chính Việt Nam. "
            f"Hãy tóm tắt bảng số liệu sau{title_hint} thành một đoạn văn "
            f"ngắn gọn (3-5 câu), nêu rõ các chỉ tiêu chính, xu hướng nổi bật, "
            f"và số liệu quan trọng nhất. Trả lời bằng tiếng Việt.\n\n"
            f"Bảng:\n{markdown[:4000]}"  # Giới hạn 4000 ký tự tránh quá dài
        )

        try:
            response = model.generate_content(prompt)
            summary = response.text.strip() if response and response.text else ""
            if summary:
                return summary
        except Exception as e:
            logger.warning(f"Gemini summary thất bại: {e}")

        return self._fallback_summary(markdown, title)

    def _fallback_summary(self, markdown: str, title: Optional[str] = None) -> str:
        """Tạo summary heuristic khi không có API."""
        lines = markdown.strip().split("\n")
        # Lấy header + 3 dòng đầu + 2 dòng cuối
        header_line = lines[0] if lines else ""
        preview_lines = lines[1:4] if len(lines) > 4 else lines[1:]
        tail_lines = lines[-2:] if len(lines) > 6 else []

        parts = [f"Bảng{'  ' + title if title else ''} gồm {len(lines)} dòng."]
        if header_line:
            parts.append(f"Cột: {header_line.replace('|', ', ').strip()}")
        if preview_lines:
            parts.append("Dữ liệu mẫu: " + " | ".join(preview_lines[:2]))
        if tail_lines:
            parts.append("Dòng cuối: " + tail_lines[-1])

        return " ".join(parts)

    def _build_markdown(self, table: "Any") -> str:
        """Tạo markdown từ headers + rows nếu table.markdown rỗng."""
        headers = getattr(table, "headers", [])
        rows = getattr(table, "rows", [])
        if not headers or not rows:
            return ""

        lines = [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join(["---"] * len(headers)) + " |",
        ]
        for row in rows:
            padded = row + [""] * (len(headers) - len(row))
            lines.append("| " + " | ".join(padded) + " |")
        return "\n".join(lines)
