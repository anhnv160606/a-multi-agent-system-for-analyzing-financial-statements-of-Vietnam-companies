"""
test_full_pipeline.py -- End-to-End Pipeline Test
=================================================
Test toan bo luong tu du lieu tho (CSV + PDF native) den bao cao HTML/PDF.

Cong ty test : HPG
Thoi ky du lieu: Q4 2022 den Q2 2026
Fiscal year   : Dung tat ca cac nam co trong CSV header (2022-2026)

Chay bang:
    python test_full_pipeline.py
"""

# ==============================================================================
# IMPORTS
# ==============================================================================

import os
import sys
import time
import traceback
from pathlib import Path
from typing import List, Optional, Tuple

# Fix UnicodeEncodeError tren Windows terminal (cp1252 khong ho tro emoji UTF-8)
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Thêm project root vào sys.path để import src.*
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env trước tất cả import khác
from src.utils.llm_client import _load_env_file
_load_env_file()


# ==============================================================================
# CONSTANTS — chỉnh ở đây nếu muốn test công ty khác
# ==============================================================================

TICKER       = "HPG"
FISCAL_YEAR  = 2025          # Năm dùng khi load vào DB (fallback; DB sẽ detect từ header)
DATA_DIR     = str(PROJECT_ROOT / "data"/TICKER)  # Thư mục chứa CSV + PDF native
OUTPUT_DIR   = str(PROJECT_ROOT / "reports")
COLLECTION_NAME = "test_hpg_v3"   # Tên mới để tránh conflict với chroma_db cũ

QUERY = (
    "Phân tích tình hình tài chính tổng thể của HPG từ năm 2022 đến 2026, "
    "bao gồm doanh thu, lợi nhuận, ROE, và đánh giá sức khỏe tài chính tổng quát. Cung cấp thêm các tin tức gần đây của doanh nghiệp"
)


# ==============================================================================
# HELPERS — banner & timer
# ==============================================================================

def _banner(phase_num: int, title: str) -> None:
    """In banner phân cách mỗi giai đoạn."""
    line = "=" * 70
    print(f"\n{line}")
    print(f"  PHASE {phase_num}: {title}")
    print(f"{line}")


def _ok(msg: str) -> None:
    print(f"  [OK]   {msg}")


def _warn(msg: str) -> None:
    print(f"  [WARN] {msg}")


def _err(msg: str) -> None:
    print(f"  [ERR]  {msg}")


def _info(msg: str) -> None:
    print(f"  [INFO] {msg}")


def _step(msg: str) -> None:
    print(f"\n  >>> {msg}")


# ==============================================================================
# PHASE 0 — ENVIRONMENT CHECK
# ==============================================================================

def phase0_check_environment() -> bool:
    """
    Kiểm tra môi trường: API keys, packages, và file dữ liệu.
    Return True nếu đủ điều kiện tối thiểu để chạy pipeline.
    """
    _banner(0, "ENVIRONMENT CHECK")
    all_ok = True

    # --- 1. API Keys ---
    _step("Kiểm tra API keys...")
    keys_to_check = {
        "JINA_TOKEN":    ("Jina Embedding API",   True),
        "GROQ_API_KEY":  ("Groq LLM Provider",    True),
        "GOOGLE_API_KEY": ("Google Gemini (optional — hiện dùng Groq)", False),
    }
    for key, (desc, required) in keys_to_check.items():
        val = os.environ.get(key, "")
        if val:
            if key == "GOOGLE_API_KEY" and not val.startswith("AIza"):
                _warn(f"{key} ({desc}): Có giá trị nhưng KHÔNG đúng định dạng "
                      f"(cần bắt đầu bằng 'AIza...'). "
                      f"→ Đang dùng Groq thay thế.")
            else:
                _ok(f"{key} ({desc}): OK")
        else:
            if required:
                _err(f"{key} ({desc}): THIẾU — pipeline có thể thất bại!")
                all_ok = False
            else:
                _warn(f"{key} ({desc}): Không có (optional)")

    # --- 2. Python packages ---
    _step("Kiểm tra packages cần thiết...")
    packages = {
        "chromadb":   ("Vector Store ChromaDB",   True),
        "markdown2":  ("Markdown → HTML export",  False),
        "weasyprint": ("Markdown → PDF (optional — sẽ dùng HTML fallback nếu thiếu)", False),
        "pandas":     ("CSV loader",              True),
        "fitz":       ("PyMuPDF — PDF text extraction", True),
    }
    for pkg, (desc, required) in packages.items():
        try:
            __import__(pkg)
            _ok(f"{pkg} ({desc}): Installed")
        except ImportError:
            if required:
                _err(f"{pkg} ({desc}): CHƯA CÀI — chạy: pip install {pkg}")
                all_ok = False
            else:
                _warn(f"{pkg} ({desc}): Chưa cài → sẽ dùng fallback")

    # --- 3. Data files ---
    _step(f"Kiểm tra file dữ liệu trong: {DATA_DIR}")
    data_path = Path(DATA_DIR)
    if not data_path.exists():
        _err(f"Thư mục data không tồn tại: {DATA_DIR}")
        return False

    csv_files = sorted(data_path.glob(f"{TICKER}_*.csv"))
    pdf_files = sorted(data_path.glob(f"{TICKER}_*.pdf"))

    if csv_files:
        _ok(f"Tìm thấy {len(csv_files)} file CSV của {TICKER}:")
        for f in csv_files:
            print(f"       {f.name}  ({f.stat().st_size / 1024:.1f} KB)")
    else:
        _err(f"Không tìm thấy CSV cho ticker={TICKER} trong {DATA_DIR}")
        all_ok = False

    if pdf_files:
        _ok(f"Tìm thấy {len(pdf_files)} file PDF của {TICKER}:")
        for f in pdf_files:
            print(f"       {f.name}  ({f.stat().st_size / 1024 / 1024:.1f} MB)")
    else:
        _warn(f"Không tìm thấy PDF cho ticker={TICKER} → Phase 3 sẽ chỉ embed nếu có CSV text")

    # --- 4. Chroma DB cũ ---
    _step("Kiểm tra trạng thái ChromaDB...")
    old_chroma = data_path / "chroma_db"
    if old_chroma.exists():
        _warn(f"Thư mục chroma_db cũ đã tồn tại: {old_chroma}")
        _info(f"Script sẽ dùng collection mới '{COLLECTION_NAME}' để tránh conflict.")
    else:
        _ok("Không có chroma_db cũ — clean state")

    # --- Summary ---
    print()
    if all_ok:
        _ok("Môi trường đủ điều kiện. Bắt đầu pipeline...")
    else:
        _err("Môi trường CÒN VẤN ĐỀ. Pipeline có thể thất bại ở một số phase.")
        _info("Tiếp tục chạy để xem chi tiết lỗi từng phase.")

    return all_ok


# ==============================================================================
# PHASE 1 — DATA INGESTION
# ==============================================================================

def phase1_ingest_data() -> List:
    """
    Gọi full_pipeline_ingestion để nạp CSV + PDF native.
    Return: List[SplitDocument] đã lọc theo TICKER.
    """
    _banner(1, f"DATA INGESTION — Ticker: {TICKER}")

    from src.ingestion.full_pipeline_ingestion import run_full_ingestion

    _step(f"Đang quét thư mục: {DATA_DIR}")
    _info("Chỉ xử lý file của ticker HPG (CSV + PDF native BCTN)...")

    all_docs = run_full_ingestion(data_dir=DATA_DIR)

    # Lọc theo ticker (BUG #3 guard: dùng getattr an toàn)
    ticker_docs = [d for d in all_docs if getattr(d, "ticker", "").upper() == TICKER.upper()]

    _step(f"Kết quả ingestion (ticker={TICKER}):")
    if not ticker_docs:
        _warn(f"Không tìm thấy SplitDocument nào cho ticker={TICKER}!")
        return []

    total_tables = 0
    total_texts  = 0
    for doc in ticker_docs:
        tables = getattr(doc, "tables", None) or []   # BUG #3 guard
        texts  = getattr(doc, "texts", None) or []    # BUG #3 guard

        total_tables += len(tables)
        total_texts  += len(texts)

        print(f"\n  ┌─ SplitDocument")
        print(f"  │  ticker         : {doc.ticker}")
        print(f"  │  doc_type       : {doc.doc_type}")
        print(f"  │  report_category: {doc.report_category}")
        print(f"  │  source_file    : {Path(doc.source_file).name}")
        print(f"  │  tables         : {len(tables)}")
        print(f"  │  texts (pages)  : {len(texts)}")

        # In sample metadata của table đầu tiên
        if tables:
            t0 = tables[0]
            meta = getattr(t0, "metadata", {})
            hdrs = getattr(t0, "headers", [])[:5]
            print(f"  │  [Sample Table 0]")
            print(f"  │    title    : {getattr(t0, 'title', 'N/A')}")
            print(f"  │    engine   : {getattr(t0, 'extraction_engine', 'N/A')}")
            print(f"  │    headers  : {hdrs}...")
            print(f"  │    metadata : {meta}")

        if texts:
            t0 = texts[0]
            snippet = getattr(t0, "text", "")[:100].replace("\n", " ")
            print(f"  │  [Sample Text Page 0]: '{snippet}...'")

        print(f"  └─")

    print()
    _ok(f"Ingestion hoàn thành: {len(ticker_docs)} SplitDocument(s), "
        f"{total_tables} bảng, {total_texts} text page(s)")
    return ticker_docs


# ==============================================================================
# PHASE 2 — LOAD CSV DATA → DATABASE (SQLite / MySQL)
# ==============================================================================

def phase2_load_to_database(docs: List):
    """
    Nạp dữ liệu dạng bảng từ CSV SplitDocument vào MySQL/SQLite.
    BUG #2: fiscal_year được detect từ header CSV khi có thể, fallback = FISCAL_YEAR.
    Return: MySQLLoader instance đã nạp xong.
    """
    _banner(2, "LOAD CSV DATA → DATABASE (SQLite / MySQL)")

    from src.database.mysql_loader import MySQLLoader

    _step("Khởi tạo MySQLLoader (tự tạo schema nếu chưa có)...")
    loader = MySQLLoader()

    backend = "SQLite (auto-fallback)" if loader.client.is_sqlite else "MySQL"
    _ok(f"Backend database: {backend}")

    # Lọc docs có tables (CSV docs)
    csv_docs = [d for d in docs if (getattr(d, "tables", None) or [])]

    if not csv_docs:
        _warn("Không có SplitDocument nào có tables → bỏ qua Phase 2")
        return loader

    total_inserted = 0
    for doc in csv_docs:
        tables = getattr(doc, "tables", []) or []
        source_file = doc.source_file

        # BUG #2: Detect năm từ headers của table (Q4 2022, Q1 2023, ...)
        fiscal_year_to_use = _detect_fiscal_year_from_table(tables, fallback=FISCAL_YEAR)

        _step(f"Nạp {len(tables)} bảng từ: {Path(source_file).name}")
        _info(f"  fiscal_year được detect: {fiscal_year_to_use}")

        try:
            # Đăng ký company
            loader.register_company({"ticker": TICKER, "company_name": f"Công ty {TICKER}"})
            _ok(f"  Đã register company: {TICKER}")

            # Nạp financial tables
            n = loader.load_extracted_tables(
                tables=tables,
                ticker=TICKER,
                fiscal_year=fiscal_year_to_use,
                source_file=source_file,
                quarter=0,
                doc_type=doc.doc_type,
            )
            total_inserted += n
            _ok(f"  Đã nạp {n} bản ghi vào financial_data")

        except Exception as e:
            _err(f"  Lỗi khi nạp bảng từ {Path(source_file).name}: {e}")
            traceback.print_exc()

    # Verify
    _step("Xác minh dữ liệu trong database...")
    try:
        rows = loader.get_financial_data(TICKER)
        _ok(f"Tổng số bản ghi financial_data cho {TICKER}: {len(rows)}")
        if rows:
            sample = rows[0]
            print(f"  Sample row: line_item='{sample.get('line_item', 'N/A')}', "
                  f"fiscal_year={sample.get('fiscal_year', 'N/A')}, "
                  f"value={sample.get('value', 'N/A')}")
    except Exception as e:
        _warn(f"Không thể verify DB: {e}")

    _ok(f"Phase 2 hoàn thành: tổng {total_inserted} bản ghi đã nạp (backend: {backend})")
    return loader


def _detect_fiscal_year_from_table(tables: List, fallback: int = 2023) -> int:
    """
    BUG #2 fix: Trích năm từ header CSV.
    CSV header dạng: ['CHỈ TIÊU', 'Q4 2022', 'Q1 2023', ..., 'Q2 2026']
    → Lấy năm cuối cùng xuất hiện (2026 hoặc 2025, v.v.)
    """
    import re
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


# ==============================================================================
# PHASE 3 — CHUNKING & EMBEDDING → VECTOR STORE
# ==============================================================================

def phase3_chunk_and_embed(docs: List):
    """
    Chunk text từ PDF native và embed vào VectorStore (ChromaDB).
    BUG #4: Kiểm tra chromadb trước.
    BUG #8: Dùng COLLECTION_NAME mới để tránh conflict.
    Return: VectorStore instance.
    """
    _banner(3, "CHUNKING & EMBEDDING → VECTOR STORE")

    # BUG #4: Kiểm tra chromadb
    try:
        import chromadb  # noqa: F401
        _ok("chromadb đã cài: sử dụng ChromaDB persistent store")
    except ImportError:
        _warn("chromadb CHƯA CÀI → dùng JSON fallback store (metadata filtering hạn chế)")
        _warn("Chạy: pip install chromadb  để có kết quả tốt hơn")

    from src.chunking.text_chunker import TextChunker
    from src.chunking.embedding_pipeline import EmbeddingPipeline
    from src.database.vector_store import VectorStore

    # BUG #8: Dùng collection name mới
    _step(f"Khởi tạo VectorStore (collection='{COLLECTION_NAME}')...")
    vector_store = VectorStore(collection_name=COLLECTION_NAME)
    _ok(f"VectorStore khởi tạo: use_fallback={vector_store.use_fallback}")

    # Lọc docs có texts (PDF native docs)
    pdf_docs = [d for d in docs if (getattr(d, "texts", None) or [])]

    if not pdf_docs:
        _warn("Không có SplitDocument nào có texts (PDF native) → bỏ qua embedding")
        _info("Phase 4 vẫn có thể hoạt động với dữ liệu từ SQL nếu Phase 2 thành công")
        return vector_store

    chunker = TextChunker()
    embed_pipeline = EmbeddingPipeline(vector_store=vector_store)

    total_chunks = 0
    for doc in pdf_docs:
        texts = getattr(doc, "texts", None) or []  # BUG #3 guard
        if not texts:
            continue

        source_name = Path(doc.source_file).name
        _step(f"Đang chunk {len(texts)} trang từ: {source_name}")

        # Base metadata cho tất cả chunks của doc này
        base_meta = {
            "ticker": doc.ticker,
            "report_category": doc.report_category,
            "source_file": doc.source_file,
        }

        try:
            chunks = chunker.chunk_pages(texts, base_metadata=base_meta)
            _info(f"  Tạo được {len(chunks)} chunks từ {len(texts)} trang")

            if not chunks:
                _warn(f"  Không có chunk nào từ {source_name}, bỏ qua embedding")
                continue

            _step(f"  Đang embed {len(chunks)} chunks qua Jina API...")
            records = embed_pipeline.run(chunks)
            total_chunks += len(records)
            _ok(f"  Đã embed và lưu {len(records)} chunks vào VectorStore")

        except Exception as e:
            _err(f"  Lỗi khi chunk/embed {source_name}: {e}")
            traceback.print_exc()

    # Verify: count trong vector store
    _step("Xác minh số lượng documents trong VectorStore...")
    try:
        if not vector_store.use_fallback and vector_store.collection:
            count = vector_store.collection.count()
            _ok(f"VectorStore (ChromaDB) count: {count} documents")
        elif vector_store.use_fallback:
            count = len(vector_store._fallback_docs)
            _ok(f"VectorStore (JSON fallback) count: {count} documents")
    except Exception as e:
        _warn(f"Không thể verify VectorStore count: {e}")

    _ok(f"Phase 3 hoàn thành: {total_chunks} embedding records đã tạo")
    return vector_store


# ==============================================================================
# PHASE 4 — MULTI-AGENT GRAPH INVOCATION
# ==============================================================================

def phase4_invoke_agents(vector_store, mysql_loader) -> dict:
    """
    Build LangGraph và invoke toàn bộ multi-agent pipeline.
    In verbose progress từng node.
    Return: final_state dict.
    """
    _banner(4, "MULTI-AGENT GRAPH INVOCATION")

    import yaml
    from src.orchestrator.graph import build_graph, create_initial_state
    from src.utils.llm_client import get_default_llm

    # Load config
    _step("Load configs/models.yaml...")
    config_path = PROJECT_ROOT / "configs" / "models.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # Lấy provider thực tế để in thông báo
    default_provider = config.get("agents", {}).get("default", {}).get("provider", "unknown")
    _ok(f"Default LLM provider: {default_provider}")
    _info(f"Query: \"{QUERY[:80]}...\"")
    _info(f"Ticker: {TICKER}, Fiscal year: {FISCAL_YEAR}")

    # Build graph
    _step("Đang build LangGraph...")
    try:
        llm = get_default_llm("default")
        graph = build_graph(
            config=config,
            llm=llm,
            vector_store=vector_store,
            mysql_loader=mysql_loader,
        )
        _ok("Graph compiled thành công")
    except Exception as e:
        _err(f"Không thể build graph: {e}")
        traceback.print_exc()
        return {}

    # Tạo initial state
    _step("Tạo initial state...")
    initial_state = create_initial_state(
        query=QUERY,
        company_ticker=TICKER,
        fiscal_years=[2022, 2023, 2024],
        max_retries=1,
    )
    _ok(f"Initial state: run_id={initial_state.get('run_id', '')[:8]}...")

    # Invoke graph
    _step("Đang invoke graph (Router → Retriever → Calculator → Analysis → Synthesis → Report → Evaluator)...")
    _info("Theo dõi log bên dưới để thấy progress từng agent:")
    print()

    try:
        t0 = time.perf_counter()
        final_state = graph.invoke(initial_state)
        elapsed = time.perf_counter() - t0
    except Exception as e:
        _err(f"Graph invoke thất bại: {e}")
        traceback.print_exc()
        return {}

    # In kết quả tổng hợp
    print()
    _step(f"Graph invoke hoàn thành trong {elapsed:.1f}s. Tóm tắt kết quả:")

    query_type = final_state.get("query_type", "N/A")
    retrieved  = final_state.get("retrieved_chunks") or []
    table_data = final_state.get("table_data") or []
    calc_res   = final_state.get("calculator_results") or {}
    analysis   = final_state.get("analysis_results") or {}
    synthesis  = final_state.get("synthesis_results") or {}
    report     = final_state.get("final_report") or ""
    errors     = final_state.get("errors") or []

    print(f"  {'Phân loại query (query_type)':<35}: {query_type}")
    print(f"  {'Số retrieved_chunks':<35}: {len(retrieved)}")
    print(f"  {'Số table_data rows':<35}: {len(table_data)}")
    print(f"  {'calculator_results':<35}: {'Có' if calc_res else 'Rỗng'} ({len(calc_res)} metrics)")
    print(f"  {'analysis_results':<35}: {'Có' if analysis else 'Rỗng'}")
    print(f"  {'synthesis_results':<35}: {'Có' if synthesis else 'Rỗng'}")
    print(f"  {'final_report':<35}: {'Có' if report else 'RỖNG — báo cáo không tạo được'} ({len(report)} chars)")
    print(f"  {'Số lỗi trong state[errors]':<35}: {len(errors)}")

    if errors:
        print()
        _warn("Danh sách lỗi trong state['errors']:")
        for i, e in enumerate(errors, 1):
            print(f"    [{i}] {e}")

    if report:
        print()
        _ok("Đoạn đầu final_report (500 ký tự đầu):")
        print("  " + "-" * 60)
        preview = report[:500].replace("\n", "\n  ")
        print(f"  {preview}")
        print("  " + "-" * 60)
    else:
        _warn("final_report rỗng — ReportAgent bị skip hoặc lỗi")

    confidence = final_state.get("confidence_score", 0)
    _ok(f"Confidence score cuối: {confidence:.2%}")

    return final_state


# ==============================================================================
# PHASE 5 — EXPORT REPORT → HTML / PDF
# ==============================================================================

def phase5_export_report(final_state: dict) -> Optional[str]:
    """
    Xuất final_report sang HTML (fallback nếu weasyprint không có).
    BUG #7: Chấp nhận HTML output trên Windows.
    Return: đường dẫn file đã tạo, hoặc None nếu thất bại.
    """
    _banner(5, "EXPORT REPORT → HTML / PDF")

    from src.agents.report.pdf_exporter import PDFExporter

    final_report = final_state.get("final_report") or ""
    if not final_report.strip():
        _warn("final_report rỗng hoặc không có — không thể export")
        _info("Kiểm tra lại Phase 4: synthesis_results và analysis_results có dữ liệu không?")
        return None

    _step("Khởi tạo PDFExporter...")
    exporter = PDFExporter()

    # BUG #7: Kiểm tra và thông báo rõ loại output
    if exporter._weasyprint_available:
        _ok("weasyprint có sẵn → sẽ tạo file PDF")
        output_ext = ".pdf"
    else:
        _warn("weasyprint KHÔNG có sẵn (thường xảy ra trên Windows thiếu GTK+)")
        _info("→ Sẽ xuất file HTML thay thế (nội dung tương đương, mở bằng browser)")
        output_ext = ".html"

    # Tạo thư mục output
    output_dir = Path(OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = str(output_dir / f"{TICKER}_report{output_ext}")

    _step(f"Đang export báo cáo ({len(final_report)} chars) → {output_path}")

    try:
        if exporter._weasyprint_available:
            actual_path = exporter.export(final_report, output_path)
        else:
            # Force HTML export (BUG #7: không crash, dùng export_html)
            actual_path = exporter.export_html(final_report, output_path)

        # Verify file tồn tại và có nội dung
        p = Path(actual_path)
        if p.exists() and p.stat().st_size > 0:
            size_kb = p.stat().st_size / 1024
            _ok(f"File xuất thành công!")
            print(f"  📄 Đường dẫn : {actual_path}")
            print(f"  📦 Kích thước : {size_kb:.1f} KB")
            return actual_path
        else:
            _err(f"File được tạo nhưng rỗng hoặc không tồn tại: {actual_path}")
            return None

    except Exception as e:
        _err(f"Export thất bại: {e}")
        traceback.print_exc()
        return None


# ==============================================================================
# MAIN — chạy tuần tự 5 phase, in summary
# ==============================================================================

def main():
    print("\n" + "=" * 70)
    print("  [START] FULL PIPELINE END-TO-END TEST")
    print(f"  Ticker      : {TICKER}")
    print(f"  Query       : {QUERY[:65]}...")
    print(f"  Data dir    : {DATA_DIR}")
    print(f"  Output dir  : {OUTPUT_DIR}")
    print(f"  Collection  : {COLLECTION_NAME}")
    print("=" * 70)

    phase_results: List[Tuple[str, str, float]] = []  # (name, status, elapsed_s)

    def run_phase(num: int, name: str, fn, *args):
        """Wrapper: jalankan sebuah phase, catat status & waktu."""
        t0 = time.perf_counter()
        result = None
        try:
            result = fn(*args)
            elapsed = time.perf_counter() - t0
            phase_results.append((f"Phase {num}: {name}", "✅ PASS", elapsed))
        except Exception as e:
            elapsed = time.perf_counter() - t0
            _err(f"PHASE {num} THẤT BẠI với exception: {type(e).__name__}: {e}")
            traceback.print_exc()
            phase_results.append((f"Phase {num}: {name}", "❌ FAIL", elapsed))
        return result

    # ---- Chạy từng phase ----
    run_phase(0, "Environment Check", phase0_check_environment)

    docs = run_phase(1, "Data Ingestion", phase1_ingest_data)
    docs = docs or []

    mysql_loader = run_phase(2, "Load to Database", phase2_load_to_database, docs)

    vector_store = run_phase(3, "Chunking & Embedding", phase3_chunk_and_embed, docs)

    final_state = run_phase(4, "Multi-Agent Pipeline", phase4_invoke_agents,
                            vector_store, mysql_loader)
    final_state = final_state or {}

    output_file = run_phase(5, "Export Report", phase5_export_report, final_state)

    # ---- Summary table ----
    print("\n\n" + "=" * 70)
    print("  [SUMMARY] PIPELINE TEST SUMMARY")
    print("=" * 70)
    for name, status, elapsed in phase_results:
        print(f"  {status}  {name:<40} ({elapsed:.1f}s)")
    print("=" * 70)

    if output_file:
        print(f"\n  [SUCCESS] BAO CAO DA TAO THANH CONG: {output_file}")
    else:
        print(f"\n  [WARN] Bao cao KHONG duoc tao -- kiem tra loi tung phase o tren.")

    print()
    all_pass = all("PASS" in s for _, s, _ in phase_results)
    if all_pass:
        print("  [PERFECT] TAT CA PHASE DEU PASS!")
    else:
        failed = [n for n, s, _ in phase_results if "FAIL" in s]
        print(f"  [FAIL] {len(failed)} phase that bai: {', '.join(failed)}")
    print()


if __name__ == "__main__":
    main()
