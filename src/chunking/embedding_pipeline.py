"""Embedding Pipeline — embed chunks thành vectors và lưu vào Vector DB.

Luồng:
    1. Nhận List[Chunk] (đã enrich metadata).
    2. Lọc chunks embeddable=True.
    3. Kiểm tra EmbeddingCache → skip chunks đã embed.
    4. Batch embedding bằng sentence-transformers (model từ settings.yaml).
    5. Cập nhật cache.
    6. Upsert vào ChromaDB qua VectorStore kèm metadata.
"""

import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from src.chunking.models import Chunk, EmbeddingRecord
from src.database.embedding_cache import EmbeddingCache
from src.database.vector_store import VectorStore
from src.utils.logger import get_logger

logger = get_logger("src.chunking.embedding_pipeline")


def _load_embedding_config() -> Dict[str, Any]:
    """Load embedding config từ settings.yaml."""
    config_path = Path(__file__).resolve().parent.parent.parent / "configs" / "settings.yaml"
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            return cfg.get("embedding", {})
        except Exception:
            pass
    return {}


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


class EmbeddingPipeline:
    """Embed chunks và lưu vào Vector DB với cache layer."""

    def __init__(
        self,
        model_name: Optional[str] = None,
        batch_size: Optional[int] = None,
        vector_store: Optional[VectorStore] = None,
        cache: Optional[EmbeddingCache] = None,
    ):
        cfg = _load_embedding_config()
        self.model_name = model_name or cfg.get("model_name", "BAAI/bge-m3")
        self.batch_size = batch_size or cfg.get("batch_size", 32)

        self.vector_store = vector_store
        self.cache = cache or EmbeddingCache()
        self._model = None

        logger.info(
            f"EmbeddingPipeline: model={self.model_name}, "
            f"batch_size={self.batch_size}"
        )

    def _init_model(self):
        """Lazy-load sentence-transformers model."""
        if self._model is not None:
            return self._model

        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
            logger.info(f"Loaded embedding model: {self.model_name}")
            return self._model
        except ImportError:
            raise ImportError(
                "Cần cài sentence-transformers: pip install sentence-transformers"
            )
        except Exception as e:
            logger.error(f"Lỗi load model {self.model_name}: {e}")
            raise

    def _init_vector_store(self):
        """Lazy-init VectorStore nếu chưa truyền vào."""
        if self.vector_store is None:
            self.vector_store = VectorStore()
        return self.vector_store

    def run(
        self,
        chunks: List[Chunk],
        skip_non_embeddable: bool = True,
    ) -> List[EmbeddingRecord]:
        """Chạy embedding pipeline end-to-end.

        Args:
            chunks: danh sách Chunk đã enrich metadata.
            skip_non_embeddable: bỏ qua chunks có embeddable=False.

        Returns:
            List[EmbeddingRecord] cho các chunks đã embed thành công.
        """
        # 1. Lọc embeddable
        if skip_non_embeddable:
            embeddable_chunks = [c for c in chunks if c.embeddable]
        else:
            embeddable_chunks = list(chunks)

        if not embeddable_chunks:
            logger.info("Không có chunk nào cần embed.")
            return []

        logger.info(
            f"Embedding {len(embeddable_chunks)}/{len(chunks)} chunks "
            f"(skipped {len(chunks) - len(embeddable_chunks)} non-embeddable)"
        )

        # 2. Kiểm tra cache
        texts = [c.content for c in embeddable_chunks]
        cached_results, uncached_indices = self.cache.get_batch(
            texts, self.model_name
        )

        logger.info(
            f"Cache: {len(texts) - len(uncached_indices)} hits, "
            f"{len(uncached_indices)} misses"
        )

        # 3. Embed uncached
        if uncached_indices:
            model = self._init_model()
            uncached_texts = [texts[i] for i in uncached_indices]

            # Batch embed với progress
            all_new_embeddings = []
            total = len(uncached_texts)
            for start in range(0, total, self.batch_size):
                end = min(start + self.batch_size, total)
                batch = uncached_texts[start:end]

                batch_embeddings = model.encode(
                    batch,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                ).tolist()

                all_new_embeddings.extend(batch_embeddings)
                logger.info(
                    f"  Embedded batch {start + 1}-{end}/{total}"
                )

            # Ghi vào cache
            self.cache.set_batch(uncached_texts, self.model_name, all_new_embeddings)

            # Merge vào cached_results
            for idx, emb in zip(uncached_indices, all_new_embeddings):
                cached_results[idx] = emb

        # 4. Chuẩn bị dữ liệu cho vector store
        records: List[EmbeddingRecord] = []
        store_ids: List[str] = []
        store_docs: List[str] = []
        store_metas: List[Dict[str, Any]] = []
        store_embeddings: List[List[float]] = []

        for i, chunk in enumerate(embeddable_chunks):
            emb = cached_results[i]
            if emb is None:
                logger.warning(f"Chunk {chunk.chunk_id} không có embedding, bỏ qua.")
                continue

            # Build metadata dict cho ChromaDB (chỉ scalar values)
            meta_dict = {}
            for field_name, field_value in chunk.metadata.model_dump().items():
                if field_value is not None:
                    meta_dict[field_name] = field_value

            # Thêm fields bổ sung
            meta_dict["chunk_id"] = chunk.chunk_id
            meta_dict["level"] = chunk.level
            if chunk.parent_id:
                meta_dict["parent_id"] = chunk.parent_id

            store_ids.append(chunk.chunk_id)
            store_docs.append(chunk.content)
            store_metas.append(meta_dict)
            store_embeddings.append(emb)

            records.append(EmbeddingRecord(
                chunk_id=chunk.chunk_id,
                content_hash=_content_hash(chunk.content),
                embedding=emb,
                model_name=self.model_name,
                dim=len(emb),
            ))

        # 5. Upsert vào vector store
        if store_ids:
            vs = self._init_vector_store()
            vs.add_documents(
                documents=store_docs,
                metadatas=store_metas,
                ids=store_ids,
                embeddings=store_embeddings,
            )
            logger.info(
                f"Upserted {len(store_ids)} chunks vào vector store "
                f"(collection: {vs.collection_name})"
            )

        # 6. Lưu cả non-embeddable chunks (bảng gốc) vào store KHÔNG kèm embedding
        non_embeddable = [c for c in chunks if not c.embeddable]
        if non_embeddable:
            ne_ids = [c.chunk_id for c in non_embeddable]
            ne_docs = [c.content for c in non_embeddable]
            ne_metas = []
            for c in non_embeddable:
                m = {k: v for k, v in c.metadata.model_dump().items() if v is not None}
                m["chunk_id"] = c.chunk_id
                m["level"] = c.level
                m["embeddable"] = False
                if c.parent_id:
                    m["parent_id"] = c.parent_id
                ne_metas.append(m)

            vs = self._init_vector_store()
            vs.add_documents(
                documents=ne_docs,
                metadatas=ne_metas,
                ids=ne_ids,
            )
            logger.info(
                f"Lưu thêm {len(non_embeddable)} non-embeddable chunks "
                f"(bảng gốc) vào store."
            )

        logger.info(
            f"Pipeline hoàn thành: {len(records)} embeddings, "
            f"{len(non_embeddable) if not skip_non_embeddable or True else 0} bảng gốc."
        )
        return records
