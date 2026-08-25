"""
Database & Storage Package (Person B - Phase 2B).
Provides unified interfaces for MySQL Relational DB, ChromaDB Vector DB, and Embedding Cache.
"""

from src.database.models import (
    CompanyRecord,
    FinancialDataRecord,
    SourceDocumentRecord,
    VectorDocumentRecord,
    VectorSearchResult,
)
from src.database.mysql_schema import init_database_schema
from src.database.mysql_client import MySQLClient
from src.database.mysql_loader import MySQLLoader
from src.database.vector_store import VectorStore
from src.database.embedding_cache import EmbeddingCache

__all__ = [
    "CompanyRecord",
    "FinancialDataRecord",
    "SourceDocumentRecord",
    "VectorDocumentRecord",
    "VectorSearchResult",
    "init_database_schema",
    "MySQLClient",
    "MySQLLoader",
    "VectorStore",
    "EmbeddingCache",
]
