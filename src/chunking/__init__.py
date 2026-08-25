"""
Chunking Package — biến SplitDocument thành chunks đã embed, sẵn sàng cho retrieval.

Pipeline:
    SplitDocument → TextChunker + TableChunker → MetadataEnricher
    → HierarchicalChunker → EmbeddingPipeline → ChromaDB
"""

from src.chunking.models import (
    Chunk,
    ChunkMetadata,
    ChunkRelationship,
    ChunkType,
    EmbeddingRecord,
    RelationType,
)
from src.chunking.text_chunker import TextChunker
from src.chunking.table_chunker import TableChunker
from src.chunking.hierarchical_chunker import HierarchicalChunker
from src.chunking.metadata_enricher import MetadataEnricher
from src.chunking.embedding_pipeline import EmbeddingPipeline

__all__ = [
    "Chunk",
    "ChunkMetadata",
    "ChunkRelationship",
    "ChunkType",
    "EmbeddingRecord",
    "RelationType",
    "TextChunker",
    "TableChunker",
    "HierarchicalChunker",
    "MetadataEnricher",
    "EmbeddingPipeline",
]
