"""
Embedding Cache Layer (Task 2.10).
Persistently caches vector embeddings using content SHA-256 hashing to prevent duplicate API/computation costs.
"""

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.utils.logger import get_logger

logger = get_logger("src.database.embedding_cache")


class EmbeddingCache:
    """
    Persistent SQLite-backed embedding cache.
    Stores and retrieves embedding vectors by SHA-256 content hash and model identifier.
    """

    def __init__(self, db_path: Optional[str | Path] = None):
        if db_path is None:
            project_root = Path(__file__).resolve().parent.parent.parent
            self.db_path = project_root / "data" / "cache" / "embedding_cache.db"
        else:
            self.db_path = Path(db_path)

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initializes cache table and hash indexes."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS embedding_cache (
                    content_hash TEXT PRIMARY KEY,
                    model_name TEXT NOT NULL,
                    dim INTEGER NOT NULL,
                    embedding_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cache_model ON embedding_cache (model_name);")
            conn.commit()

    def _compute_hash(self, text: str, model_name: str) -> str:
        """Computes SHA-256 hash for a given text content and model identifier."""
        clean_text = text.strip()
        composite = f"{model_name}:{clean_text}"
        return hashlib.sha256(composite.encode("utf-8")).hexdigest()

    def get(self, text: str, model_name: str) -> Optional[List[float]]:
        """
        Retrieves a cached embedding vector if present.
        """
        content_hash = self._compute_hash(text, model_name)
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT embedding_json FROM embedding_cache WHERE content_hash = ?",
                (content_hash,),
            )
            row = cursor.fetchone()
            if row:
                try:
                    return json.loads(row[0])
                except Exception as e:
                    logger.warning(f"Failed to decode cached embedding: {e}")
        return None

    def set(self, text: str, model_name: str, embedding: List[float]):
        """
        Stores an embedding vector in the cache.
        """
        if not embedding:
            return
        content_hash = self._compute_hash(text, model_name)
        emb_json = json.dumps(embedding)
        dim = len(embedding)

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO embedding_cache (content_hash, model_name, dim, embedding_json)
                VALUES (?, ?, ?, ?)
                """,
                (content_hash, model_name, dim, emb_json),
            )
            conn.commit()

    def get_batch(
        self, texts: List[str], model_name: str
    ) -> Tuple[List[Optional[List[float]]], List[int]]:
        """
        Batch retrieves embeddings from cache.
        Returns:
            (cached_embeddings, uncached_indices):
            - cached_embeddings: List with vectors where cached, None where missed.
            - uncached_indices: Indices in `texts` that need to be computed by model.
        """
        cached_results: List[Optional[List[float]]] = [None] * len(texts)
        uncached_indices: List[int] = []

        for idx, text in enumerate(texts):
            cached_emb = self.get(text, model_name)
            if cached_emb is not None:
                cached_results[idx] = cached_emb
            else:
                uncached_indices.append(idx)

        logger.debug(
            f"Embedding Cache ({model_name}): {len(texts) - len(uncached_indices)} hits, "
            f"{len(uncached_indices)} misses out of {len(texts)} texts."
        )
        return cached_results, uncached_indices

    def set_batch(
        self, texts: List[str], model_name: str, embeddings: List[List[float]]
    ):
        """
        Stores multiple embedding vectors in a single transaction.
        """
        if not texts or not embeddings or len(texts) != len(embeddings):
            return

        records = []
        for text, emb in zip(texts, embeddings):
            if emb:
                chash = self._compute_hash(text, model_name)
                records.append((chash, model_name, len(emb), json.dumps(emb)))

        if records:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO embedding_cache (content_hash, model_name, dim, embedding_json)
                    VALUES (?, ?, ?, ?)
                    """,
                    records,
                )
                conn.commit()

    def count(self) -> int:
        """Returns the total number of cached embedding entries."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM embedding_cache")
            return cursor.fetchone()[0]

    def clear(self):
        """Clears all cached embedding entries."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("DELETE FROM embedding_cache")
            conn.commit()
        logger.info("Cleared embedding cache.")
