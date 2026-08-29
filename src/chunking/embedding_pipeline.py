"""Embedding Pipeline — embed chunks thành vectors và lưu vào Vector DB (Sử dụng Hugging Face API)."""

import hashlib
import os
import random
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib import response

import requests
import yaml

from src.chunking.models import Chunk, EmbeddingRecord
from src.database.embedding_cache import EmbeddingCache
from src.database.vector_store import VectorStore
from src.utils.llm_client import _load_env_file
from src.utils.logger import get_logger

logger = get_logger("src.chunking.embedding_pipeline")

_load_env_file()

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
    """Embed chunks qua Hugging Face API và lưu vào Vector DB với cache layer."""

    def __init__(
        self,
        api_url: Optional[str] = None,
        model_name: Optional[str] = None,
        vector_store: Optional[VectorStore] = None,
        cache: Optional[EmbeddingCache] = None,
    ):
        cfg = _load_embedding_config()
        self.model_name = model_name or cfg.get("model_name", "jina-embeddings-v4")
        self.api_url = api_url or cfg.get("API_URL", "https://api.jina.ai/v1/embeddings")
        self.jina_token = os.environ.get("JINA_TOKEN")
        if not self.jina_token:
            logger.warning("Không tìm thấy JINA_TOKEN. API có thể sẽ từ chối truy cập.")

        self.vector_store = vector_store
        self.cache = cache or EmbeddingCache()

        logger.info(
            f"EmbeddingPipeline (API Mode): model={self.model_name}, "
        )

    def _call_jina_api(self, texts: List[str], max_retries: int = 8, batch_size: int = 32) -> List[List[float]]:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.jina_token}",
        }

        all_embeddings: List[List[float]] = []

        for b_idx in range(0, len(texts), batch_size):
            batch_texts = texts[b_idx:b_idx + batch_size]
            payload = {
                "model": self.model_name,
                "input": batch_texts,
            }

            batch_succeeded = False
            for attempt in range(max_retries):
                try:
                    response = requests.post(
                        self.api_url,
                        headers=headers,
                        json=payload,
                        timeout=60,
                    )

                    if response.status_code == 200:
                        result = response.json()
                        batch_embs = [item["embedding"] for item in result["data"]]
                        all_embeddings.extend(batch_embs)
                        batch_succeeded = True
                        time.sleep(0.3)
                        break

                    elif response.status_code == 429:
                        retry_after = response.headers.get("Retry-After")
                        if retry_after:
                            try:
                                wait_time = float(retry_after)
                            except ValueError:
                                wait_time = max(3.0, float(2 ** attempt))
                        else:
                            wait_time = max(3.0, float(2 ** attempt) + random.uniform(0.5, 2.0))

                        logger.warning(
                            f"[JINA] Rate limit (429) on batch {b_idx//batch_size + 1}. "
                            f"Chờ {wait_time:.2f}s... (Attempt {attempt + 1}/{max_retries})"
                        )
                        time.sleep(wait_time)

                    elif response.status_code >= 500:
                        wait_time = min(float(2 ** attempt) + random.uniform(0.5, 2.0), 30.0)
                        logger.warning(
                            f"[JINA] Server error {response.status_code}. "
                            f"Chờ {wait_time:.2f}s... (Attempt {attempt + 1}/{max_retries})"
                        )
                        time.sleep(wait_time)

                    else:
                        logger.error(f"[JINA] API Error {response.status_code}: {response.text}")
                        raise Exception(f"Jina API error {response.status_code}: {response.text}")

                except (requests.exceptions.Timeout, requests.exceptions.ConnectionError, requests.exceptions.RequestException) as req_err:
                    wait_time = min(float(2 ** attempt), 30.0)
                    logger.warning(f"[JINA] Network error ({req_err}). Chờ {wait_time}s... (Attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)

            if not batch_succeeded:
                raise Exception(f"Đã hết {max_retries} lần thử khi gọi Jina API cho batch {b_idx//batch_size + 1}.")

        logger.info(f"[JINA] Embedding hoàn tất thành công ({len(all_embeddings)}/{len(texts)} texts)")
        return all_embeddings

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
        """Chạy embedding pipeline end-to-end qua API."""
        
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

        # 3. Embed uncached qua API
        if uncached_indices:
            uncached_texts = [texts[i] for i in uncached_indices]

            all_new_embeddings = self._call_jina_api(uncached_texts)
            logger.info(f" Hoàn thành embedding {len(all_new_embeddings)} chunks qua API.")

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