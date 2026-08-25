"""
Vector Store Wrapper for ChromaDB with Resilient Local Semantic Fallback.
Handles document embedding indexing, cosine similarity semantic search, and metadata filtering.
"""

import json
import math
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import yaml

from src.database.models import VectorDocumentRecord, VectorSearchResult
from src.utils.logger import get_logger

logger = get_logger("src.database.vector_store")


class VectorStore:
    """
    Unified Vector Database Interface wrapping ChromaDB.
    Supports local persistent disk storage (dev), Docker HTTP Client (prod),
    and a built-in lightweight cosine vector fallback if ChromaDB package is not yet installed.
    """

    def __init__(
        self,
        collection_name: Optional[str] = None,
        config_path: Optional[str | Path] = None,
        embedding_function: Optional[Any] = None,
    ):
        self.project_root = Path(__file__).resolve().parent.parent.parent
        self.config_path = (
            Path(config_path) if config_path else self.project_root / "configs" / "database.yaml"
        )
        self.config = self._load_config()
        self.embedding_function = embedding_function

        # Configure paths & parameters
        self.mode = self.config.get("mode", "persistent")
        persist_dir_str = self.config.get("persist_directory", "./data/chroma_db")
        self.persist_directory = self.project_root / persist_dir_str.lstrip("./")
        self.persist_directory.mkdir(parents=True, exist_ok=True)

        coll_cfg = self.config.get("collection", {})
        self.collection_name = (
            collection_name
            or os.getenv(coll_cfg.get("name_env", "VECTOR_COLLECTION_NAME"), coll_cfg.get("default_name", "document_knowledge_base"))
        )
        self.distance_metric = coll_cfg.get("distance_metric", "cosine")

        self.use_fallback = False
        self.client = None
        self.collection = None
        self._fallback_store_file = self.persist_directory / f"{self.collection_name}_store.json"
        self._fallback_docs: Dict[str, Dict[str, Any]] = {}

        self._init_backend()

    def _load_config(self) -> Dict[str, Any]:
        """Loads vector_db config from database.yaml."""
        if not self.config_path.exists():
            return {}
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
                return cfg.get("vector_db", {})
        except Exception as e:
            logger.error(f"Error loading vector_db config: {e}")
            return {}

    def _init_backend(self):
        """Attempts to initialize ChromaDB; activates fallback store if package is not present."""
        try:
            import chromadb
            from chromadb.config import Settings

            if self.mode == "http":
                http_cfg = self.config.get("http_client", {})
                host = os.getenv(http_cfg.get("host_env", "CHROMA_HOST"), http_cfg.get("default_host", "localhost"))
                port = int(os.getenv(http_cfg.get("port_env", "CHROMA_PORT"), http_cfg.get("default_port", 8000)))
                logger.info(f"Connecting to ChromaDB Server at http://{host}:{port}...")
                self.client = chromadb.HttpClient(
                    host=host,
                    port=port,
                    settings=Settings(anonymized_telemetry=False),
                )
            else:
                logger.info(f"Initializing ChromaDB Persistent Client at {self.persist_directory}...")
                self.client = chromadb.PersistentClient(
                    path=str(self.persist_directory),
                    settings=Settings(anonymized_telemetry=False),
                )

            metadata_cfg = {"hnsw:space": self.distance_metric}
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata=metadata_cfg,
                embedding_function=self.embedding_function,
            )
            self.use_fallback = False
            logger.info(f"Vector Store collection '{self.collection_name}' ready ({self.distance_metric}).")

        except ImportError:
            logger.warning(
                f"ChromaDB package not found in current environment. Activating Resilient Local Vector Store: {self._fallback_store_file.name}"
            )
            self.use_fallback = True
            self._load_fallback_store()
        except Exception as e:
            logger.warning(f"Could not connect to ChromaDB ({e}). Activating Resilient Local Vector Store.")
            self.use_fallback = True
            self._load_fallback_store()

    def _load_fallback_store(self):
        """Loads JSON fallback storage."""
        if self._fallback_store_file.exists():
            try:
                with open(self._fallback_store_file, "r", encoding="utf-8") as f:
                    self._fallback_docs = json.load(f)
            except Exception:
                self._fallback_docs = {}
        else:
            self._fallback_docs = {}

    def _save_fallback_store(self):
        """Saves JSON fallback storage."""
        try:
            with open(self._fallback_store_file, "w", encoding="utf-8") as f:
                json.dump(self._fallback_docs, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving fallback vector store: {e}")

    def add_documents(
        self,
        documents: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None,
        embeddings: Optional[List[List[float]]] = None,
    ) -> List[str]:
        """
        Adds or updates documents in the Vector Store in batches.
        """
        if not documents:
            return []

        if ids is None:
            ids = [f"doc_{uuid.uuid4().hex[:12]}" for _ in range(len(documents))]

        if metadatas is None:
            metadatas = [{} for _ in range(len(documents))]

        clean_metadatas = []
        for m in metadatas:
            clean_m = {}
            for k, v in m.items():
                if isinstance(v, (str, int, float, bool)):
                    clean_m[k] = v
                else:
                    clean_m[k] = str(v)
            clean_metadatas.append(clean_m)

        if self.use_fallback:
            for idx, doc_id in enumerate(ids):
                doc_text = documents[idx]
                doc_meta = clean_metadatas[idx]
                emb = embeddings[idx] if (embeddings and idx < len(embeddings)) else self._dummy_embed(doc_text)
                self._fallback_docs[doc_id] = {
                    "document": doc_text,
                    "metadata": doc_meta,
                    "embedding": emb,
                }
            self._save_fallback_store()
            logger.info(f"Indexed {len(documents)} documents into Local Vector Store.")
            return ids

        batch_size = self.config.get("indexing", {}).get("batch_size", 64)
        total = len(documents)

        for i in range(0, total, batch_size):
            end_idx = min(i + batch_size, total)
            batch_docs = documents[i:end_idx]
            batch_metas = clean_metadatas[i:end_idx]
            batch_ids = ids[i:end_idx]
            batch_embs = embeddings[i:end_idx] if embeddings else None

            kwargs = {
                "ids": batch_ids,
                "documents": batch_docs,
                "metadatas": batch_metas,
            }
            if batch_embs is not None:
                kwargs["embeddings"] = batch_embs

            self.collection.upsert(**kwargs)

        logger.info(f"Indexed {total} documents into ChromaDB collection '{self.collection_name}'.")
        return ids

    def query(
        self,
        query_text: str,
        n_results: int = 5,
        where: Optional[Dict[str, Any]] = None,
        where_document: Optional[Dict[str, Any]] = None,
    ) -> List[VectorSearchResult]:
        """
        Performs semantic vector search using query text.
        """
        if not query_text:
            return []

        if self.use_fallback:
            query_emb = self._dummy_embed(query_text)
            return self.query_by_embedding(query_emb, n_results=n_results, where=where)

        kwargs = {
            "query_texts": [query_text],
            "n_results": n_results,
        }
        if where:
            kwargs["where"] = where
        if where_document:
            kwargs["where_document"] = where_document

        results = self.collection.query(**kwargs)
        return self._format_results(results)

    def query_by_embedding(
        self,
        embedding: List[float],
        n_results: int = 5,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[VectorSearchResult]:
        """
        Performs semantic search directly using a precomputed embedding vector.
        """
        if self.use_fallback:
            scored: List[Tuple[float, str, Dict[str, Any]]] = []
            for doc_id, data in self._fallback_docs.items():
                meta = data.get("metadata", {})
                # Apply where filter
                if where:
                    match = all(meta.get(k) == v for k, v in where.items())
                    if not match:
                        continue

                doc_emb = data.get("embedding")
                sim = self._cosine_similarity(embedding, doc_emb) if doc_emb else 0.5
                dist = max(0.0, 1.0 - sim)
                scored.append((dist, doc_id, data))

            scored.sort(key=lambda x: x[0])
            top_k = scored[:n_results]

            results = []
            for dist, doc_id, data in top_k:
                results.append(
                    VectorSearchResult(
                        id=doc_id,
                        document=data.get("document", ""),
                        metadata=data.get("metadata", {}),
                        distance=dist,
                        similarity=max(0.0, 1.0 - dist),
                    )
                )
            return results

        kwargs = {
            "query_embeddings": [embedding],
            "n_results": n_results,
        }
        if where:
            kwargs["where"] = where

        results = self.collection.query(**kwargs)
        return self._format_results(results)

    def delete(
        self,
        ids: Optional[List[str]] = None,
        where: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Deletes items from collection by ID or metadata filter."""
        if self.use_fallback:
            if ids:
                for doc_id in ids:
                    self._fallback_docs.pop(doc_id, None)
            if where:
                to_del = []
                for doc_id, data in self._fallback_docs.items():
                    meta = data.get("metadata", {})
                    if all(meta.get(k) == v for k, v in where.items()):
                        to_del.append(doc_id)
                for doc_id in to_del:
                    self._fallback_docs.pop(doc_id, None)
            self._save_fallback_store()
            return True

        kwargs = {}
        if ids:
            kwargs["ids"] = ids
        if where:
            kwargs["where"] = where

        if kwargs:
            self.collection.delete(**kwargs)
            logger.info(f"Deleted records from collection '{self.collection_name}'.")
            return True
        return False

    def count(self) -> int:
        """Returns the total number of indexed vectors in the collection."""
        if self.use_fallback:
            return len(self._fallback_docs)
        return self.collection.count()

    def get_collection_stats(self) -> Dict[str, Any]:
        """Returns summary statistics of the active collection."""
        return {
            "collection_name": self.collection_name,
            "count": self.count(),
            "distance_metric": self.distance_metric,
            "mode": "fallback_local" if self.use_fallback else self.mode,
            "persist_directory": str(self.persist_directory),
        }

    def _format_results(self, raw_results: Dict[str, Any]) -> List[VectorSearchResult]:
        """Converts raw ChromaDB query response into structured VectorSearchResult models."""
        formatted: List[VectorSearchResult] = []
        if not raw_results or not raw_results.get("ids") or not raw_results["ids"][0]:
            return formatted

        ids = raw_results["ids"][0]
        docs = raw_results.get("documents", [[]])[0]
        metas = raw_results.get("metadatas", [[]])[0]
        distances = raw_results.get("distances", [[]])[0]

        for idx in range(len(ids)):
            doc_id = ids[idx]
            doc_text = docs[idx] if idx < len(docs) else ""
            doc_meta = metas[idx] if idx < len(metas) else {}
            dist = float(distances[idx]) if idx < len(distances) else 0.0
            sim = max(0.0, 1.0 - dist)

            formatted.append(
                VectorSearchResult(
                    id=doc_id,
                    document=doc_text,
                    metadata=doc_meta or {},
                    distance=dist,
                    similarity=sim,
                )
            )

        return formatted

    def _cosine_similarity(self, vec_a: List[float], vec_b: List[float]) -> float:
        """Computes cosine similarity between two float vectors."""
        if not vec_a or not vec_b or len(vec_a) != len(vec_b):
            return 0.0
        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = math.sqrt(sum(a * a for a in vec_a))
        norm_b = math.sqrt(sum(b * b for b in vec_b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def _dummy_embed(self, text: str, dim: int = 16) -> List[float]:
        """Generates deterministic pseudo-embedding for text in fallback mode."""
        import hashlib
        h = hashlib.sha256(text.encode("utf-8")).digest()
        emb = [(b / 255.0) * 2.0 - 1.0 for b in h[:dim]]
        norm = math.sqrt(sum(x * x for x in emb)) or 1.0
        return [x / norm for x in emb]
