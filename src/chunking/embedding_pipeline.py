"""Embedding Pipeline — embed chunks thành vectors và lưu vào Vector DB (Sử dụng Hugging Face API)."""

import hashlib
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
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
    """Embed chunks qua Hugging Face API và lưu vào Vector DB với cache layer."""

    def __init__(
        self,
        model_name: Optional[str] = None,
        batch_size: Optional[int] = None,
        vector_store: Optional[VectorStore] = None,
        cache: Optional[EmbeddingCache] = None,
    ):
        cfg = _load_embedding_config()
        self.model_name = model_name or cfg.get("model_name", "BAAI/bge-m3")
        # Gọi API nên hạ batch_size xuống (khoảng 16 hoặc 32) để tránh timeout/payload too large
        self.batch_size = batch_size or cfg.get("batch_size", 16) 
        
        # Ưu tiên lấy token từ tham số, sau đó đến OS Env, cuối cùng là YAML
        self.hf_token = os.environ.get("HF_TOKEN") or cfg.get("hf_token")
        if not self.hf_token:
            logger.warning("Không tìm thấy HF_TOKEN. API có thể sẽ từ chối truy cập.")

        self.vector_store = vector_store
        self.cache = cache or EmbeddingCache()

        self.api_url = f"https://api-inference.huggingface.co/pipeline/feature-extraction/{self.model_name}"

        logger.info(
            f"EmbeddingPipeline (API Mode): model={self.model_name}, "
            f"batch_size={self.batch_size}"
        )

    def _call_hf_api(self, texts: List[str], max_retries: int = 5) -> List[List[float]]:
        """
        Gọi Hugging Face API để lấy embeddings.
        Tích hợp cơ chế retry xử lý lỗi 503 (Model is loading).
        """
        headers = {}
        if self.hf_token:
            headers["Authorization"] = f"Bearer {self.hf_token}"

        payload = {
            "inputs": texts,
            "options": {"wait_for_model": True}
        }

        for attempt in range(max_retries):
            try:
                response = requests.post(self.api_url, headers=headers, json=payload, timeout=60)
                
                if response.status_code == 200:
                    embeddings = response.json()
                    # BGE-M3 API trả về mảng 2D (batch_size, dim), đôi khi bị bọc thêm 1 chiều
                    # Đoạn này đảm bảo dữ liệu là List[List[float]]
                    if isinstance(embeddings, list) and isinstance(embeddings[0], list):
                        if isinstance(embeddings[0][0], list): # Xử lý nếu trả về 3D [batch, seq_len, dim]
                            # Pooling mặc định (lấy CLS token - phần tử đầu tiên của mỗi đoạn)
                            return [doc[0] for doc in embeddings]
                        return embeddings
                    else:
                        raise ValueError(f"Định dạng JSON trả về không mong đợi: {type(embeddings)}")

                elif response.status_code == 503:
                    # Lỗi cold-start đặc trưng của Hugging Face Free API
                    estimated_time = response.json().get("estimated_time", 15)
                    logger.info(f"[API] Mô hình đang khởi động. Chờ {estimated_time}s... (Attempt {attempt+1}/{max_retries})")
                    time.sleep(estimated_time)
                else:
                    logger.error(f"API Error {response.status_code}: {response.text}")
                    raise Exception(f"HF API trả về lỗi: {response.text}")

            except requests.exceptions.RequestException as e:
                logger.error(f"Lỗi mạng khi gọi HF API: {e}")
                time.sleep(5) # Chờ 5s rồi thử lại nếu lỗi mạng
        
        raise Exception("Đã hết số lần thử (retries) gọi Hugging Face API.")

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

            # Batch embed với progress
            all_new_embeddings = []
            total = len(uncached_texts)
            for start in range(0, total, self.batch_size):
                end = min(start + self.batch_size, total)
                batch = uncached_texts[start:end]

                logger.info(f" Đang gọi API cho batch {start + 1}-{end}/{total}...")
                
                # SỬ DỤNG API Ở ĐÂY THAY VÌ MÔ HÌNH LOCAL
                batch_embeddings = self._call_hf_api(batch)
                
                all_new_embeddings.extend(batch_embeddings)
                logger.info(f" Hoàn thành batch {start + 1}-{end}/{total}")

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