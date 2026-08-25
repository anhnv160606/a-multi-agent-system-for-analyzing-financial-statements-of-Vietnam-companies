"""Full Ingestion Pipeline -- điểm vào duy nhất cho toàn bộ luồng nạp dữ liệu.

Quy cách đặt file đầu vào:
    {ticker}_{BS/IS/CF}     .csv   →  Báo cáo tài chính (CSV)
    {ticker}_bchcd           .pdf   →  Biên bản họp cổ đông (PDF scan)
    {ticker}_bctn             .pdf   →  Báo cáo thường niên   (PDF native)

Output: List[SplitDocument]  -- một SplitDocument cho mỗi file (hoặc mỗi nhóm
CSV cùng ticker), sẵn sàng cho downstream chunking / vector-store / SQL.

Thiết kế chính:
    1.  Nhận danh sách đường dẫn file (hoặc 1 thư mục).
    2.  Phân loại file → CSV / PDF.
    3.  Với PDF: Định tuyến trực tiếp theo quy ước tên file (bchcd -> scan, bctn -> native).
    4.  **Ticker enrichment**: trích ticker từ tên file, gắn vào
        SplitDocument.ticker VÀ inject thêm vào metadata của mỗi
        ExtractedTable (để retriever downstream filter chính xác theo mã).
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.ingestion.models import (
    ExtractedTable,
    ImageProcessingResult,
    PageContent,
    SplitDocument,
)
from src.utils.logger import get_logger

logger = get_logger("src.ingestion.full_pipeline_ingestion")

# ---------------------------------------------------------------------------
# Hằng số mapping hậu tố tên file → report_category
# ---------------------------------------------------------------------------
_SUFFIX_TO_CATEGORY = {
    "bs": "bctc",
    "is": "bctc",
    "cf": "bctc",
    "bchcd": "bien_ban_dhcd",
    "bctn": "bao_cao_thuong_nien",
}

# Hậu tố thuộc nhóm CSV tài chính
_CSV_SUFFIXES = {"bs", "is", "cf"}

# Regex parse tên file:  {TICKER}_{SUFFIX}  (case-insensitive)
_FILENAME_PATTERN = re.compile(
    r"^(?P<ticker>[A-Za-z0-9]+)_(?P<suffix>BS|IS|CF|bchcd|bctn)$",
    re.IGNORECASE,
)


# ===========================================================================
# Helper: Trích ticker & loại báo cáo từ tên file
# ===========================================================================

def parse_filename(file_path: str | Path) -> Tuple[str, str]:
    """Trích (ticker, suffix) từ tên file theo quy cách {ticker}_{suffix}.

    Returns:
        (ticker_upper, suffix_lower)  -- ví dụ ("FPT", "bs"), ("VNM", "bchcd").

    Raises:
        ValueError nếu tên file không khớp quy cách.
    """
    stem = Path(file_path).stem
    m = _FILENAME_PATTERN.match(stem)
    if not m:
        raise ValueError(
            f"Tên file '{stem}' không khớp quy cách {{ticker}}_{{BS/IS/CF/bchcd/bctn}}. "
            "Không thể trích mã cổ phiếu."
        )
    return m.group("ticker").upper(), m.group("suffix").lower()


def _report_category(suffix: str) -> str:
    """Chuyển suffix → report_category chuẩn."""
    return _SUFFIX_TO_CATEGORY.get(suffix.lower(), "unknown")


# ===========================================================================
# Ticker Metadata Enrichment
# ===========================================================================

def _enrich_tables_metadata(
    tables: List[ExtractedTable],
    ticker: str,
    report_category: str,
    source_file: str,
) -> None:
    """Inject ticker + report_category vào metadata của từng ExtractedTable."""
    for table in tables:
        table.metadata["ticker"] = ticker
        table.metadata["report_category"] = report_category
        table.metadata["source_file"] = source_file


def _enrich_pages_metadata(
    pages: List[PageContent],
    ticker: str,
    source_file: str,
) -> None:
    """Inject ticker vào layout_info của từng PageContent."""
    for page in pages:
        page.layout_info["ticker"] = ticker
        page.layout_info["source_file"] = source_file


# ===========================================================================
# Sub-pipeline: CSV financial statements
# ===========================================================================

def _ingest_csv_group(
    ticker: str,
    csv_paths: Dict[str, str],
) -> SplitDocument:
    """Xử lý nhóm CSV (BS/IS/CF) cùng ticker → 1 SplitDocument."""
    from src.ingestion.CSV.csv_loader import CSVFinancialLoader

    loader = CSVFinancialLoader()
    tables = loader.load_company_financials(
        bs_path=csv_paths.get("bs", ""),
        is_path=csv_paths.get("is", ""),
        cf_path=csv_paths.get("cf", ""),
    )

    # Enrich metadata
    all_sources = ", ".join(csv_paths.values())
    _enrich_tables_metadata(tables, ticker, "bctc", all_sources)

    return SplitDocument(
        source_file=all_sources,
        doc_type="csv",
        report_category="bctc",
        ticker=ticker,
        tables=tables,
    )


# ===========================================================================
# Sub-pipeline: PDF scan (biên bản họp cổ đông)
# ===========================================================================

def _ingest_pdf_scan(
    pdf_path: str,
    ticker: str,
    report_category: str,
) -> SplitDocument:
    """Pipeline cho PDF scan: detect trang → table/text extraction."""
    import importlib.util

    from pdf2image import convert_from_path

    _scan_dir = Path(__file__).resolve().parent / "PDF scan"

    def _load_scan_module(module_file: str):
        spec = importlib.util.spec_from_file_location(
            module_file.removesuffix(".py"), _scan_dir / module_file
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    _mod_detector = _load_scan_module("page_type_detector_scan.py")
    _mod_table    = _load_scan_module("table_extractor_scan.py")
    _mod_text     = _load_scan_module("text_extractor_scan.py")

    PageTypeDetectorScan = _mod_detector.PageTypeDetectorScan
    TableExtractorScan   = _mod_table.TableExtractorScan
    TextExtractorScan    = _mod_text.TextExtractorScan

    logger.info(f"[SCAN] Bắt đầu xử lý: {pdf_path}  (ticker={ticker})")

    images = convert_from_path(pdf_path, dpi=300)
    detector = PageTypeDetectorScan()
    has_table_flags = detector.classify_pages(images)

    table_extractor = TableExtractorScan()
    text_extractor = TextExtractorScan()

    all_tables: List[ExtractedTable] = []
    all_texts: List[PageContent] = []

    for idx, (img, has_table) in enumerate(zip(images, has_table_flags)):
        page_num = idx + 1
        if has_table:
            tables, page_content = table_extractor.extract_page(
                img, page_num, pdf_path=pdf_path
            )
            all_tables.extend(tables)
            if page_content.text.strip():
                all_texts.append(page_content)
        else:
            page_content = text_extractor.extract_page(
                img, page_num, pdf_path=pdf_path
            )
            if page_content.text.strip():
                all_texts.append(page_content)

    # Enrich metadata
    _enrich_tables_metadata(all_tables, ticker, report_category, pdf_path)
    _enrich_pages_metadata(all_texts, ticker, pdf_path)

    logger.info(
        f"[SCAN] Hoàn thành {pdf_path}: "
        f"{len(all_tables)} bảng, {len(all_texts)} trang text."
    )

    return SplitDocument(
        source_file=pdf_path,
        doc_type="scan",
        report_category=report_category,
        ticker=ticker,
        tables=all_tables,
        texts=all_texts,
    )


# ===========================================================================
# Sub-pipeline: PDF native (báo cáo thường niên)
# ===========================================================================

def _ingest_pdf_native(
    pdf_path: str,
    ticker: str,
    report_category: str,
) -> SplitDocument:
    """Pipeline cho PDF native: layout → text / table / image extraction."""
    from src.ingestion.native import (
        TextExtractorNative
    )

    logger.info(f"[NATIVE] Bắt đầu xử lý: {pdf_path}  (ticker={ticker})")

    # --- Text ---
    text_extractor = TextExtractorNative()
    texts = text_extractor.extract_text_from_pdf(pdf_path)

    _enrich_pages_metadata(texts, ticker, pdf_path)

    logger.info(
        f"[NATIVE] Hoàn thành {pdf_path}: "
        f"{len(texts)} trang text, "
    )

    return SplitDocument(
        source_file=pdf_path,
        doc_type="native",
        report_category=report_category,
        ticker=ticker,
        texts=texts
    )


# ===========================================================================
# MAIN ENTRY: run_full_ingestion
# ===========================================================================

def run_full_ingestion(
    file_paths: Optional[List[str]] = None,
    data_dir: Optional[str] = None,
) -> List[SplitDocument]:
    """Điểm vào chính -- nạp toàn bộ file từ danh sách hoặc thư mục."""
    # ---- Thu thập danh sách file ----
    paths: List[Path] = []
    if file_paths:
        paths = [Path(p) for p in file_paths]
    elif data_dir:
        d = Path(data_dir)
        paths = sorted(d.glob("*.csv")) + sorted(d.glob("*.pdf"))
    else:
        default_dir = Path(__file__).resolve().parent.parent.parent / "data"
        paths = sorted(default_dir.glob("*.csv")) + sorted(default_dir.glob("*.pdf"))

    if not paths:
        logger.warning("Không tìm thấy file nào để xử lý.")
        return []

    logger.info(f"Tìm thấy {len(paths)} file để xử lý.")

    # ---- Phân loại file theo ticker & loại ----
    csv_groups: Dict[str, Dict[str, str]] = {}
    
    # Lưu thêm biến suffix vào tuple để lát sau dùng định tuyến
    pdf_files: List[Tuple[str, str, str, str]] = []  # (path, ticker, report_category, suffix)

    for p in paths:
        if not p.is_file():
            logger.warning(f"Bỏ qua (không phải file): {p}")
            continue

        try:
            ticker, suffix = parse_filename(p)
        except ValueError as e:
            logger.warning(str(e))
            continue

        category = _report_category(suffix)
        ext = p.suffix.lower()

        if ext == ".csv" and suffix in _CSV_SUFFIXES:
            csv_groups.setdefault(ticker, {})[suffix] = str(p)
        elif ext == ".pdf":
            pdf_files.append((str(p), ticker, category, suffix))
        else:
            logger.warning(f"Bỏ qua file không xác định loại: {p}")

    # ---- Chạy ingestion ----
    results: List[SplitDocument] = []

    # 1. CSV groups
    for ticker, suffix_map in csv_groups.items():
        logger.info(
            f"[CSV] Xử lý nhóm ticker={ticker}: "
            f"{', '.join(suffix_map.keys())}"
        )
        try:
            doc = _ingest_csv_group(ticker, suffix_map)
            results.append(doc)
        except Exception as e:
            logger.error(f"[CSV] Lỗi xử lý ticker={ticker}: {e}", exc_info=True)

    # 2. PDF files (Định tuyến theo suffix thay vì classify_pdf)
    for pdf_path, ticker, category, suffix in pdf_files:
        try:
            if suffix == "bchcd":
                logger.info(
                    f"[PDF] File {pdf_path} (theo quy ước tên) → type=scan, "
                    f"ticker={ticker}, category={category}"
                )
                doc = _ingest_pdf_scan(pdf_path, ticker, category)
                results.append(doc)
            
            elif suffix == "bctn":
                logger.info(
                    f"[PDF] File {pdf_path} (theo quy ước tên) → type=native, "
                    f"ticker={ticker}, category={category}"
                )
                doc = _ingest_pdf_native(pdf_path, ticker, category)
                results.append(doc)
                
            else:
                logger.warning(f"[PDF] Bỏ qua file PDF có hậu tố không được hỗ trợ: {pdf_path}")
                
        except Exception as e:
            logger.error(f"[PDF] Lỗi xử lý {pdf_path}: {e}", exc_info=True)

    logger.info(
        f"Pipeline hoàn thành: {len(results)} SplitDocument(s) tạo thành "
        f"từ {len(paths)} file."
    )
    return results


# ===========================================================================
# CLI quick-test
# ===========================================================================

if __name__ == "__main__":
    import os
    from pathlib import Path

    DATA_DIR = "data"

    print(f"🚀 BẮT ĐẦU CHẠY INGESTION PIPELINE CHO THƯ MỤC: {DATA_DIR}")
    if not os.path.exists(DATA_DIR):
        print(f"❌ Cảnh báo: Thư mục '{DATA_DIR}' không tồn tại. Vui lòng kiểm tra lại đường dẫn!")
    
    docs = run_full_ingestion(data_dir=DATA_DIR)

    print(f"\n🎉 HOÀN THÀNH! TỔNG SỐ SPLIT DOCUMENT TẠO RA: {len(docs)}")

    for doc in docs:
        print(f"\n{'='*70}")
        print(f"  Ticker   : {doc.ticker}")
        print(f"  Type     : {doc.doc_type}")
        print(f"  Category : {doc.report_category}")
        print(f"  Source   : {doc.source_file}")
        
        num_tables = len(doc.tables) if getattr(doc, 'tables', None) else 0
        num_texts = len(doc.texts) if getattr(doc, 'texts', None) else 0
        num_images = len(doc.images) if getattr(doc, 'images', None) else 0
        num_image_results = len(doc.image_results) if getattr(doc, 'image_results', None) else 0

        print(f"  Tables   : {num_tables}")
        print(f"  Texts    : {num_texts}")
        print(f"  Images   : {num_images}")
        print(f"  ImgRes   : {num_image_results}")

        if num_tables > 0:
            t = doc.tables[0]
            print(f"\n  [Sample Table Metadata - Table 1]")
            print(f"    title    : {getattr(t, 'title', 'N/A')}")
            print(f"    engine   : {getattr(t, 'extraction_engine', 'N/A')}")
            print(f"    metadata : {getattr(t, 'metadata', {})}")
            
            headers = getattr(t, 'headers', [])
            print(f"    headers  : {headers[:5]}..." if headers else "    headers  : []")
            print(f"    rows     : {len(getattr(t, 'rows', []))} dòng")