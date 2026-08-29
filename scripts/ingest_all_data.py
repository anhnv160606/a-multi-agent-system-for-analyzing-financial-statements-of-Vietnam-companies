"""
scripts/ingest_all_data.py
==========================
Kịch bản tự động nạp và tiền xử lý toàn bộ dữ liệu (CSV + PDF BCTN) trong thư mục data/
vào CSDL SQL (financial_app.db) và Vector DB (ChromaDB - collection 'document_knowledge_base').

Sau khi chạy script này:
- Toàn bộ bảng BCTC của FPT, HPG, CTG, VIC, GEX được lưu sẵn vào database.
- Toàn bộ văn bản BCTN được cắt chunk và nhúng vector vào ChromaDB.
- Khi bật giao diện localhost:3000, AI có thể truy xuất tức thì mà không cần nạp lại.
"""

import io
import os
import re
import sys
import time
import traceback
from pathlib import Path
from typing import Dict, List

# Fix UTF-8 encoding trên Windows terminal
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env
from src.utils.llm_client import _load_env_file
_load_env_file()

from src.ingestion.full_pipeline_ingestion import run_full_ingestion
from src.database.mysql_loader import MySQLLoader
from src.chunking.text_chunker import TextChunker
from src.chunking.embedding_pipeline import EmbeddingPipeline
from src.database.vector_store import VectorStore

DATA_DIR = PROJECT_ROOT / "data"
COLLECTION_NAME = "document_knowledge_base"


def _detect_fiscal_year_from_table(tables: List, fallback: int = 2023) -> int:
    latest_year = fallback
    for table in tables:
        headers = getattr(table, "headers", []) or []
        for h in headers:
            m = re.search(r"\b(20\d{2})\b", str(h))
            if m:
                yr = int(m.group(1))
                if yr > latest_year:
                    latest_year = yr
    return latest_year


def main():
    print("=" * 75)
    print("  🚀 [FINAGENT] TIỀN XỬ LÝ & NẠP TOÀN BỘ DỮ LIỆU TÀI CHÍNH VÀO RAG SYSTEM")
    print(f"  📂 Thư mục dữ liệu: {DATA_DIR}")
    print(f"  🗄️  Vector Collection: {COLLECTION_NAME}")
    print("=" * 75)

    # 1. Bóc tách toàn bộ tài liệu trong data/
    print("\n>>> [1/3] Bóc tách tài liệu CSV và PDF từ data/...")
    t0 = time.time()
    all_docs = run_full_ingestion(data_dir=str(DATA_DIR))
    print(f"  ✅ Đã xử lý {len(all_docs)} tài liệu trong {time.time() - t0:.1f}s")

    # Nhóm tài liệu theo Ticker
    ticker_docs_map: Dict[str, List] = {}
    for doc in all_docs:
        ticker = getattr(doc, "ticker", "UNKNOWN").upper()
        ticker_docs_map.setdefault(ticker, []).append(doc)

    print(f"  📊 Tìm thấy các mã doanh nghiệp: {', '.join(sorted(ticker_docs_map.keys()))}")

    # 2. Nạp bảng tài chính vào CSDL SQL
    print("\n>>> [2/3] Nạp bảng tài chính CSV vào CSDL SQL (financial_app.db)...")
    loader = MySQLLoader()
    sql_summary = {}

    for ticker, docs in sorted(ticker_docs_map.items()):
        csv_docs = [d for d in docs if (getattr(d, "tables", None) or [])]
        if not csv_docs:
            continue

        loader.register_company({"ticker": ticker, "company_name": f"Công ty Cổ phần {ticker}"})
        ticker_inserted = 0
        for doc in csv_docs:
            tables = getattr(doc, "tables", []) or []
            fiscal_year = _detect_fiscal_year_from_table(tables, fallback=2023)
            n = loader.load_extracted_tables(
                tables=tables,
                ticker=ticker,
                fiscal_year=fiscal_year,
                source_file=doc.source_file,
                quarter=0,
                doc_type=doc.doc_type,
            )
            ticker_inserted += n
        sql_summary[ticker] = ticker_inserted
        print(f"  ✔ [{ticker}] Đã nạp {ticker_inserted} bản ghi BCTC vào SQL Database")

    # 3. Phân mảnh & Tạo Vector Embeddings lưu vào ChromaDB
    print(f"\n>>> [3/3] Phân mảnh BCTN & Tạo Vector Embeddings vào ChromaDB ('{COLLECTION_NAME}')...")
    vector_store = VectorStore(collection_name=COLLECTION_NAME)
    chunker = TextChunker()
    embed_pipeline = EmbeddingPipeline(vector_store=vector_store)
    vector_summary = {}

    for ticker, docs in sorted(ticker_docs_map.items()):
        pdf_docs = [d for d in docs if (getattr(d, "texts", None) or [])]
        if not pdf_docs:
            continue

        total_ticker_chunks = 0
        for doc in pdf_docs:
            texts = getattr(doc, "texts", None) or []
            if not texts:
                continue

            base_meta = {
                "ticker": ticker,
                "report_category": doc.report_category,
                "source_file": doc.source_file,
            }
            chunks = chunker.chunk_pages(texts, base_metadata=base_meta)
            if not chunks:
                continue

            print(f"  ⏳ Đang nhúng {len(chunks)} chunks cho [{ticker}] qua Jina Embedding...")
            records = embed_pipeline.run(chunks)
            total_ticker_chunks += len(records)

        vector_summary[ticker] = total_ticker_chunks
        print(f"  ✔ [{ticker}] Đã lưu {total_ticker_chunks} vector chunks vào ChromaDB")

    # Tổng kết
    print("\n" + "=" * 75)
    print("  🎉 [HOÀN TẤT NẠP DỮ LIỆU]")
    print("=" * 75)
    print(f"  {'MÃ DOANH NGHIỆP':<18} | {'BẢN GHI SQL':<15} | {'CHUNKS VECTOR':<15}")
    print("  " + "-" * 55)
    for ticker in sorted(ticker_docs_map.keys()):
        sql_cnt = sql_summary.get(ticker, 0)
        vec_cnt = vector_summary.get(ticker, 0)
        print(f"  {ticker:<18} | {sql_cnt:<15} | {vec_cnt:<15}")
    print("=" * 75)

    if not vector_store.use_fallback and vector_store.collection:
        total_in_db = vector_store.collection.count()
        print(f"  📦 Tổng số vector trong ChromaDB ('{COLLECTION_NAME}'): {total_in_db}")

    print("\n  👉 Tất cả dữ liệu đã sẵn sàng! Bây giờ bạn chỉ cần mở http://localhost:3000 để chat và phân tích.")


if __name__ == "__main__":
    main()
