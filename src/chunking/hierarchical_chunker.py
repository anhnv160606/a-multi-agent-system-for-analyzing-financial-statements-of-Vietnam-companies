"""Hierarchical Chunker — tạo cấu trúc parent-child 3 cấp cho chunks.

Nhận List[Chunk] (level=2, đã tạo bởi text_chunker/table_chunker) và nhóm
chúng thành hierarchy:
    Level 0: Section summary (cha)    — tóm tắt toàn bộ 1 section lớn
    Level 1: Sub-section              — heading con bên trong section
    Level 2: Detail chunks            — text/table chunks cụ thể (giữ nguyên)

Dựa trên field `metadata.section` (heading đã detect bởi text_chunker) để
nhóm chunks vào sections, rồi tạo parent chunks tổng hợp.
"""

from collections import OrderedDict
from typing import Dict, List, Optional

from src.chunking.models import Chunk, ChunkMetadata, ChunkRelationship, ChunkType, RelationType
from src.utils.logger import get_logger

logger = get_logger("src.chunking.hierarchical_chunker")


def _estimate_tokens(text: str) -> int:
    return len(text.split())


class HierarchicalChunker:
    """Tổ chức flat chunks thành cấu trúc phân cấp 3 levels."""

    def __init__(self, max_summary_length: int = 500):
        """
        Args:
            max_summary_length: Số ký tự tối đa cho section summary (level 0).
        """
        self.max_summary_length = max_summary_length

    def build_hierarchy(
        self,
        chunks: List[Chunk],
    ) -> tuple[List[Chunk], List[ChunkRelationship]]:
        """Nhận flat chunks (level 2) → trả (all_chunks, relationships).

        Returns:
            all_chunks: danh sách chunks bao gồm cả parent chunks mới tạo
            relationships: danh sách quan hệ parent-child
        """
        if not chunks:
            return [], []

        # Nhóm chunks theo section name
        section_groups = self._group_by_section(chunks)

        all_chunks: List[Chunk] = []
        relationships: List[ChunkRelationship] = []

        for section_name, section_chunks in section_groups.items():
            # ---- Tạo Level 0: Section summary ----
            section_summary = self._create_section_summary(
                section_name, section_chunks
            )
            all_chunks.append(section_summary)

            # ---- Phân nhóm sub-section (Level 1) ----
            sub_groups = self._group_sub_sections(section_chunks)

            for sub_name, sub_chunks in sub_groups.items():
                if len(sub_groups) > 1:
                    # Có nhiều sub-section → tạo level 1
                    sub_section = self._create_sub_section(
                        sub_name, sub_chunks, parent_id=section_summary.chunk_id
                    )
                    all_chunks.append(sub_section)
                    relationships.append(ChunkRelationship(
                        source_chunk_id=section_summary.chunk_id,
                        target_chunk_id=sub_section.chunk_id,
                        relation_type=RelationType.PARENT_CHILD,
                    ))

                    # Level 2: detail chunks → gắn parent = sub_section
                    for chunk in sub_chunks:
                        chunk.parent_id = sub_section.chunk_id
                        chunk.level = 2
                        all_chunks.append(chunk)
                        relationships.append(ChunkRelationship(
                            source_chunk_id=sub_section.chunk_id,
                            target_chunk_id=chunk.chunk_id,
                            relation_type=RelationType.PARENT_CHILD,
                        ))
                else:
                    # Chỉ 1 sub-group → gắn trực tiếp vào section (skip level 1)
                    for chunk in sub_chunks:
                        chunk.parent_id = section_summary.chunk_id
                        chunk.level = 2
                        all_chunks.append(chunk)
                        relationships.append(ChunkRelationship(
                            source_chunk_id=section_summary.chunk_id,
                            target_chunk_id=chunk.chunk_id,
                            relation_type=RelationType.PARENT_CHILD,
                        ))

        logger.info(
            f"HierarchicalChunker: {len(chunks)} flat chunks → "
            f"{len(all_chunks)} total chunks, {len(relationships)} relationships"
        )
        return all_chunks, relationships

    def _group_by_section(
        self, chunks: List[Chunk]
    ) -> "OrderedDict[str, List[Chunk]]":
        """Nhóm chunks theo metadata.section, giữ thứ tự xuất hiện."""
        groups: OrderedDict[str, List[Chunk]] = OrderedDict()
        for chunk in chunks:
            section = chunk.metadata.section or "__no_section__"
            groups.setdefault(section, []).append(chunk)
        return groups

    def _group_sub_sections(
        self, chunks: List[Chunk]
    ) -> "OrderedDict[str, List[Chunk]]":
        """Trong 1 section, phân nhóm theo sub-heading (nếu có).

        Sub-heading được detect khi chunk content bắt đầu bằng pattern
        [heading] (do text_chunker prepend).
        """
        groups: OrderedDict[str, List[Chunk]] = OrderedDict()
        current_sub = "__default__"

        for chunk in chunks:
            # Detect sub-heading từ content
            content = chunk.content.strip()
            if content.startswith("[") and "]\n" in content:
                bracket_end = content.index("]\n")
                heading_in_bracket = content[1:bracket_end].strip()
                # Chỉ coi là sub-section nếu khác section cha
                if heading_in_bracket != (chunk.metadata.section or ""):
                    current_sub = heading_in_bracket

            groups.setdefault(current_sub, []).append(chunk)

        return groups

    def _create_section_summary(
        self, section_name: str, chunks: List[Chunk]
    ) -> Chunk:
        """Tạo chunk Level 0: tóm tắt section."""
        # Lấy metadata từ chunk đầu tiên làm base
        base_meta = chunks[0].metadata.model_copy() if chunks else ChunkMetadata()
        base_meta.section = section_name
        base_meta.chunk_type = ChunkType.TEXT

        # Tạo summary bằng cách ghép đầu mỗi chunk
        preview_parts = []
        for c in chunks[:5]:  # Lấy tối đa 5 chunks đầu
            text = c.content.strip()
            # Bỏ heading prefix [...]
            if text.startswith("[") and "]\n" in text:
                text = text[text.index("]\n") + 2:]
            # Lấy câu đầu
            first_sentence = text.split(".")[0].strip() + "."
            if len(first_sentence) > 100:
                first_sentence = first_sentence[:100] + "..."
            preview_parts.append(first_sentence)

        display_name = section_name if section_name != "__no_section__" else "Nội dung chung"
        summary = f"[Tóm tắt mục: {display_name}] " + " ".join(preview_parts)
        summary = summary[:self.max_summary_length]

        return Chunk(
            content=summary,
            metadata=base_meta,
            level=0,
            token_count=_estimate_tokens(summary),
            embeddable=True,
        )

    def _create_sub_section(
        self, sub_name: str, chunks: List[Chunk], parent_id: str
    ) -> Chunk:
        """Tạo chunk Level 1: sub-section."""
        base_meta = chunks[0].metadata.model_copy() if chunks else ChunkMetadata()
        base_meta.section = sub_name
        base_meta.chunk_type = ChunkType.TEXT

        # Preview ngắn
        preview_parts = []
        for c in chunks[:3]:
            text = c.content.strip()
            if text.startswith("[") and "]\n" in text:
                text = text[text.index("]\n") + 2:]
            snippet = text[:80].strip()
            if snippet:
                preview_parts.append(snippet + "...")

        display_name = sub_name if sub_name != "__default__" else "Mục con"
        summary = f"[{display_name}] " + " ".join(preview_parts)
        summary = summary[:300]

        return Chunk(
            content=summary,
            metadata=base_meta,
            parent_id=parent_id,
            level=1,
            token_count=_estimate_tokens(summary),
            embeddable=True,
        )
