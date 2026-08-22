# Cấu trúc thư mục dự án — Multi-Agent Financial Statement Analysis

> [!NOTE]
> Mỗi file/thư mục đều ghi rõ **nhiệm vụ** và **cần code gì**. Số task tham chiếu feature_list.md.
> Ký hiệu: 📁 = thư mục, 📄 = file

---

```
finagent-rag/
├── 📄 pyproject.toml
├── 📄 requirements.txt
├── 📄 docker-compose.yml
├── 📄 Dockerfile
├── 📄 .env.example
├── 📄 .gitignore
├── 📄 Makefile
├── 📄 README.md
│
├── 📁 configs/
├── 📁 prompts/
├── 📁 src/
│   ├── 📁 ingestion/
│   ├── 📁 chunking/
│   ├── 📁 database/
│   ├── 📁 agents/
│   ├── 📁 orchestrator/
│   ├── 📁 finance/
│   ├── 📁 ui/
│   └── 📁 utils/
├── 📁 tests/
├── 📁 data/
├── 📁 scripts/
├── 📁 notebooks/
└── 📁 docs/
```

---

## Root Files — Cấu hình dự án

### 📄 `pyproject.toml`
- **Nhiệm vụ:** Quản lý project metadata, dependencies, build system
- **Cần code:**
  - Khai báo tất cả dependencies: `langchain`, `langgraph`, `chromadb`, `pdfplumber`, `docling`, `tesseract`, `vnstock`, `mysql-connector-python`, `streamlit`, ...
  - Cấu hình `[tool.pytest]`, `[tool.ruff]` (linter)
  - Python >= 3.11
- **Task:** 0.2

### 📄 `requirements.txt`
- **Nhiệm vụ:** Fallback dependency list cho môi trường không dùng pyproject.toml
- **Cần code:** Pin version cho tất cả packages (ví dụ: `langgraph==0.2.x`)
- **Task:** 0.2

### 📄 `docker-compose.yml`
- **Nhiệm vụ:** Định nghĩa tất cả services cần thiết để chạy hệ thống
- **Cần code:**
  - Service `mysql`: MySQL 8.0, volume mount, port 3306
  - Service `chromadb`: ChromaDB server, port 8000
  - Service `app`: Build từ Dockerfile, mount source code
  - Service `sandbox`: Container chạy code sandbox cho Calculator Agent (Python restricted)
  - Network nội bộ cho các service giao tiếp
- **Task:** 0.4

### 📄 `Dockerfile`
- **Nhiệm vụ:** Build image cho ứng dụng chính
- **Cần code:** Base image Python 3.11, cài Tesseract OCR, copy source, entrypoint

### 📄 `.env.example`
- **Nhiệm vụ:** Template biến môi trường
- **Cần code:** Các key: `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `MYSQL_*`, `CHROMADB_*`, `LANGSMITH_API_KEY`

### 📄 `.gitignore`
- **Nhiệm vụ:** Loại trừ file không cần track
- **Cần code:** Ignore `.env`, `__pycache__`, `data/raw/`, `*.pdf`, `.venv/`, `mlruns/`
- **Task:** 0.7

### 📄 `Makefile`
- **Nhiệm vụ:** Shortcut commands cho dev workflow
- **Cần code:** Targets: `make setup`, `make run`, `make test`, `make docker-up`, `make lint`

### 📄 `README.md`
- **Nhiệm vụ:** Tài liệu tổng quan dự án, hướng dẫn cài đặt và chạy

---

## 📁 `configs/` — Quản lý cấu hình

```
configs/
├── 📄 settings.yaml          # Cấu hình chính
├── 📄 models.yaml             # Cấu hình LLM models
├── 📄 database.yaml           # Cấu hình database connections
└── 📄 logging.yaml            # Cấu hình logging
```

### 📄 `configs/settings.yaml`
- **Nhiệm vụ:** Cấu hình tập trung cho toàn hệ thống — **không hardcode bất kỳ tham số nào trong code**
- **Cần code:**
  ```yaml
  chunking:
    text_chunk_size: 1000
    text_chunk_overlap: 200
    table_summary_threshold: 2000  # tokens, vượt qua → tạo summary
  
  retrieval:
    top_k: 10
    rerank_top_k: 5
    similarity_threshold: 0.7
    hybrid_search_alpha: 0.5  # tỉ lệ vector vs BM25
  
  embedding:
    model_name: "BAAI/bge-m3"
    batch_size: 32
  
  ocr:
    engine: "tesseract"  # hoặc "paddleocr"
    language: "vie"
  
  sandbox:
    timeout_seconds: 30
    max_memory_mb: 512
  ```
- **Task:** 0.5

### 📄 `configs/models.yaml`
- **Nhiệm vụ:** Cấu hình cho từng LLM model sử dụng trong hệ thống
- **Cần code:**
  ```yaml
  router:
    model: "gemini-2.0-flash"
    temperature: 0.0
  
  agents:
    default:
      model: "gemini-2.5-pro"
      temperature: 0.2
      max_tokens: 4096
    
    calculator:
      model: "gemini-2.5-pro"
      temperature: 0.0  # cần deterministic
    
    report_writer:
      model: "gemini-2.5-pro"
      temperature: 0.5
      max_tokens: 8192
  ```

### 📄 `configs/database.yaml`
- **Nhiệm vụ:** Connection strings và config cho MySQL + Vector DB
- **Cần code:** Host, port, database name, collection name, authentication

### 📄 `configs/logging.yaml`
- **Nhiệm vụ:** Structured logging configuration
- **Cần code:** JSON format, log levels per module, file rotation, console output
- **Task:** 0.6

---

## 📁 `prompts/` — Prompt Templates (Version Controlled)

> [!IMPORTANT]
> Tất cả prompt templates tập trung ở đây, **KHÔNG hardcode prompt trong source code**. Đánh version bằng Git.

```
prompts/
├── 📄 router.yaml                # Prompt cho Adaptive Strategy Router
├── 📄 retriever.yaml             # Prompt cho query reformulation
├── 📄 calculator.yaml            # Prompt cho PoT code generation
├── 📄 sql_generator.yaml         # Prompt cho SQL query generation
├── 📄 analysis.yaml              # Prompt cho Analysis Agent (DuPont, Trend, ...)
├── 📄 modeling.yaml              # Prompt cho Modeling Agent (chọn model, fill params)
├── 📄 synthesis.yaml             # Prompt cho Synthesis Agent
├── 📄 report.yaml                # Prompt cho Report Agent
├── 📄 bull.yaml                  # System prompt cho Bull Agent (lạc quan)
├── 📄 bear.yaml                  # System prompt cho Bear Agent (bi quan)
├── 📄 judge.yaml                 # Prompt cho Judge Agent + rubric scoring
├── 📄 evaluator.yaml             # Prompt cho Evaluator Agent
├── 📄 table_summarizer.yaml      # Prompt tóm tắt bảng lớn
└── 📄 image_captioner.yaml       # Prompt mô tả hình ảnh/biểu đồ
```

### Mỗi file prompt cần có format:
```yaml
name: "calculator_agent"
version: "1.0.0"
description: "Sinh Python code tính toán chỉ số tài chính"

system_prompt: |
  Bạn là chuyên gia phân tích tài chính...

user_template: |
  Câu hỏi: {query}
  Dữ liệu: {context}
  Hãy sinh Python code...

variables:
  - query
  - context
```

- **Task:** 7.6

---

## 📁 `src/` — Source Code Chính

### 📄 `src/__init__.py`
- **Nhiệm vụ:** Đánh dấu `src` là Python package

### 📄 `src/config.py`
- **Nhiệm vụ:** Load và validate config từ `configs/` folder
- **Cần code:**
  - Class `Settings` — load YAML, merge với env vars, validate bằng Pydantic
  - Singleton pattern để dùng chung config toàn app
  - Hàm `get_settings() -> Settings`
- **Task:** 0.5

---

## 📁 `src/ingestion/` — Data Ingestion Pipeline (Phase 1)

```
src/ingestion/
├── 📄 __init__.py
├── 📄 pdf_classifier.py          # Phân loại PDF scan vs native
├── 📄 ocr_pipeline.py            # OCR cho PDF scan
├── 📄 text_extractor.py          # Extract text từ PDF native
├── 📄 table_extractor.py         # Extract bảng từ PDF
├── 📄 image_extractor.py         # Extract hình ảnh từ PDF
├── 📄 image_processor.py         # Xử lý hình ảnh (chart-to-data, captioning)
├── 📄 document_splitter.py       # Tách PDF thành 3 luồng: Text, Table, Images
├── 📄 vnstock_client.py          # Client gọi VNStock API
├── 📄 api_cache.py               # Cache kết quả API
├── 📄 cross_validator.py         # Đối chiếu dữ liệu PDF vs API
└── 📄 models.py                  # Pydantic models cho ingestion data
```

### 📄 `src/ingestion/pdf_classifier.py`
- **Nhiệm vụ:** Tự động phân loại PDF là scan (hình ảnh) hay native (có text layer)
- **Cần code:**
  - Hàm `classify_pdf(pdf_path: str) -> Literal["scan", "native"]`
  - Heuristic: dùng `pdfplumber` extract text, nếu text rỗng/quá ít → scan
  - Có thể thêm check metadata PDF (producer, creator)
- **Task:** 1.1

### 📄 `src/ingestion/ocr_pipeline.py`
- **Nhiệm vụ:** OCR cho PDF scan — chuyển ảnh thành text
- **Cần code:**
  - Class `OCRPipeline` với methods: `process(pdf_path) -> list[PageContent]`
  - Tích hợp Tesseract (default) hoặc PaddleOCR (fallback)
  - Pre-processing ảnh: deskew, denoise, contrast enhancement
  - Config ngôn ngữ: `vie` (tiếng Việt)
- **Task:** 1.2

### 📄 `src/ingestion/text_extractor.py`
- **Nhiệm vụ:** Extract text từ PDF native (có text layer sẵn)
- **Cần code:**
  - Class `TextExtractor` — dùng `pdfplumber` hoặc `LlamaParse`
  - Output: list các `PageContent(page_num, text, layout_info)`
  - Giữ structure: heading, paragraph, list
- **Task:** 1.3

### 📄 `src/ingestion/table_extractor.py`
- **Nhiệm vụ:** Extract bảng biểu từ PDF — chuyển thành dạng có cấu trúc
- **Cần code:**
  - Class `TableExtractor` — dùng `Docling` / `pdfplumber` / `Camelot`
  - Output: `list[ExtractedTable]` với fields: `page_num`, `headers`, `rows`, `markdown`, `csv`
  - Logic xử lý bảng merge cells, bảng nhiều trang
  - Xuất bảng dạng **Markdown** (cho LLM) và **CSV/DataFrame** (cho SQL)
- **Task:** 1.4

### 📄 `src/ingestion/image_extractor.py`
- **Nhiệm vụ:** Trích xuất hình ảnh nhúng trong PDF
- **Cần code:**
  - Hàm `extract_images(pdf_path) -> list[ExtractedImage]`
  - Metadata: page_num, bounding box, image bytes
  - Filter: bỏ ảnh quá nhỏ (logo, icon), giữ biểu đồ/sơ đồ
- **Task:** 1.5

### 📄 `src/ingestion/image_processor.py`
- **Nhiệm vụ:** Xử lý hình ảnh đã extract — chuyển biểu đồ thành dữ liệu
- **Cần code:**
  - Hàm `process_chart(image) -> TableData` — dùng DePlot/ChartOCR chuyển biểu đồ → bảng số liệu
  - Hàm `caption_image(image) -> str` — dùng VLM (Gemini Vision) tạo mô tả
  - Logic phân loại: chart vs diagram vs photo
- **Task:** 1.6

### 📄 `src/ingestion/document_splitter.py`
- **Nhiệm vụ:** Điều phối toàn bộ pipeline, tách PDF thành 3 luồng
- **Cần code:**
  - Class `DocumentSplitter` — orchestrate: classify → extract → split
  - Input: `pdf_path`
  - Output: `SplitDocument(texts: list, tables: list, images: list)`
  - Gọi lần lượt: `pdf_classifier` → chọn pipeline → `text_extractor` + `table_extractor` + `image_extractor`
- **Task:** 1.7

### 📄 `src/ingestion/vnstock_client.py`
- **Nhiệm vụ:** Client gọi VNStock API lấy dữ liệu thị trường
- **Cần code:**
  - Class `VNStockClient` với methods:
    - `get_stock_price(ticker, start, end)` — giá lịch sử OHLCV
    - `get_company_info(ticker)` — thông tin cơ bản DN
    - `get_financial_ratios(ticker)` — chỉ số tài chính cơ bản
    - `get_news(ticker, limit)` — tin tức
  - Error handling: retry, timeout
- **Task:** 1.8

### 📄 `src/ingestion/api_cache.py`
- **Nhiệm vụ:** Cache kết quả API để tránh gọi lại & fallback khi API down
- **Cần code:**
  - Cache layer (file-based hoặc Redis)
  - TTL (time-to-live) cho mỗi loại data
  - Fallback: trả cached data khi API timeout
- **Task:** 1.9

### 📄 `src/ingestion/cross_validator.py`
- **Nhiệm vụ:** Đối chiếu số liệu extract từ PDF với dữ liệu API
- **Cần code:**
  - Hàm `validate(extracted_data, api_data) -> ValidationResult`
  - So sánh: doanh thu, lợi nhuận, tổng tài sản
  - Output: match/mismatch report, confidence score
- **Task:** 1.10

### 📄 `src/ingestion/models.py`
- **Nhiệm vụ:** Pydantic data models cho toàn bộ module ingestion
- **Cần code:**
  - `PageContent`, `ExtractedTable`, `ExtractedImage`, `SplitDocument`, `ValidationResult`

---

## 📁 `src/chunking/` — Chunking & Embedding (Phase 2A)

```
src/chunking/
├── 📄 __init__.py
├── 📄 text_chunker.py            # Chunk văn bản theo semantic
├── 📄 table_chunker.py           # Chunk bảng biểu (giữ nguyên hoặc summary)
├── 📄 hierarchical_chunker.py    # Parent-child chunking
├── 📄 metadata_enricher.py       # Gắn metadata cho mỗi chunk
├── 📄 cross_reference_linker.py  # Liên kết text chunk ↔ table chunk
├── 📄 embedding_pipeline.py      # Pipeline embed chunks + upsert vào Vector DB
└── 📄 models.py                  # Pydantic models cho chunks
```

### 📄 `src/chunking/text_chunker.py`
- **Nhiệm vụ:** Chia văn bản thành các chunks theo ranh giới ngữ nghĩa
- **Cần code:**
  - Dùng `RecursiveCharacterTextSplitter` hoặc custom splitter
  - Config: `chunk_size`, `chunk_overlap` từ settings.yaml
  - Giữ heading context cho mỗi chunk
- **Task:** 2.1

### 📄 `src/chunking/table_chunker.py`
- **Nhiệm vụ:** Xử lý bảng — giữ nguyên bảng nhỏ, tạo summary cho bảng lớn
- **Cần code:**
  - Nếu bảng ≤ threshold tokens → giữ nguyên dạng Markdown
  - Nếu bảng > threshold → gọi LLM tạo summary mô tả
  - Lưu cả summary (để embed) và bảng gốc (để trả khi retrieve)
- **Task:** 2.2

### 📄 `src/chunking/hierarchical_chunker.py`
- **Nhiệm vụ:** Tạo cấu trúc parent-child cho chunks
- **Cần code:**
  - Level 0: Section summary (cha)
  - Level 1: Mục con
  - Level 2: Đoạn chi tiết (con)
  - Quan hệ parent_id → child_id
- **Task:** 2.3

### 📄 `src/chunking/metadata_enricher.py`
- **Nhiệm vụ:** Gắn metadata cho mỗi chunk để hỗ trợ filtered retrieval
- **Cần code:**
  - Extract/assign metadata: `{ticker, year, quarter, report_type, section, page, source_file, chunk_type}`
  - Heuristic nhận diện section name từ heading
- **Task:** 2.4

### 📄 `src/chunking/cross_reference_linker.py`
- **Nhiệm vụ:** Tạo liên kết giữa text chunk và table chunk khi có tham chiếu chéo
- **Cần code:**
  - Detect patterns: "Xem Bảng 5", "Chi tiết tại bảng số liệu..."
  - Lưu relationship: `text_chunk_id ↔ table_chunk_id`
- **Task:** 2.5

### 📄 `src/chunking/embedding_pipeline.py`
- **Nhiệm vụ:** Embed chunks thành vectors và lưu vào Vector DB
- **Cần code:**
  - Load embedding model (`bge-m3` hoặc `multilingual-e5`)
  - Batch embedding với progress bar
  - Upsert vào ChromaDB/Qdrant kèm metadata
  - Embedding cache: kiểm tra hash content, skip nếu đã embed
- **Task:** 2.9, 2.10

### 📄 `src/chunking/models.py`
- **Nhiệm vụ:** Data models cho chunks
- **Cần code:** `Chunk`, `ChunkMetadata`, `ChunkRelationship`, `EmbeddingRecord`

---

## 📁 `src/database/` — Database Layer (Phase 2B)

```
src/database/
├── 📄 __init__.py
├── 📄 mysql_client.py            # MySQL connection & query wrapper
├── 📄 mysql_schema.py            # Schema definition (DDL)
├── 📄 mysql_loader.py            # Load extracted data vào MySQL
├── 📄 vector_store.py            # ChromaDB/Qdrant wrapper
└── 📄 models.py                  # ORM models / schema definitions
```

### 📄 `src/database/mysql_schema.py`
- **Nhiệm vụ:** Định nghĩa schema cho MySQL — thiết kế bảng
- **Cần code:**
  ```sql
  -- Bảng companies: ticker, name, industry, exchange, founded_year
  -- Bảng financial_data: company_id, fiscal_year, fiscal_quarter, 
  --                      report_type, line_item, value, unit, source_file, page_number
  -- Bảng source_documents: file_path, upload_date, company_id, doc_type, processed_status
  ```
  - Migration script (tạo bảng, index)
- **Task:** 2.6

### 📄 `src/database/mysql_client.py`
- **Nhiệm vụ:** Wrapper kết nối MySQL, execute queries
- **Cần code:**
  - Connection pool
  - Methods: `execute_query()`, `execute_many()`, `fetch_one()`, `fetch_all()`
  - Context manager cho transaction
- **Task:** 2.6

### 📄 `src/database/mysql_loader.py`
- **Nhiệm vụ:** Script load bảng số liệu đã extract vào MySQL
- **Cần code:**
  - Hàm `load_tables(extracted_tables, company_ticker, fiscal_year)`
  - Map cột bảng extract → schema `financial_data`
  - Upsert logic (update nếu đã tồn tại)
- **Task:** 2.7

### 📄 `src/database/vector_store.py`
- **Nhiệm vụ:** Wrapper cho Vector DB (ChromaDB dev / Qdrant prod)
- **Cần code:**
  - Class `VectorStore` — abstract interface
  - Implementations: `ChromaDBStore`, `QdrantStore`
  - Methods: `add_documents()`, `search()`, `search_with_filter()`, `delete()`
  - Hybrid search: vector similarity + BM25
- **Task:** 2.8

---

## 📁 `src/agents/` — Tất cả Agents (Phase 3 & 4)

> [!IMPORTANT]
> Mỗi agent là một module riêng với cấu trúc thống nhất: logic chính + tools (nếu có).

```
src/agents/
├── 📄 __init__.py
├── 📄 base_agent.py              # Base class cho tất cả agents
│
├── 📁 retriever/                 # Agent truy xuất dữ liệu
│   ├── 📄 __init__.py
│   ├── 📄 agent.py               # Retriever Agent logic
│   ├── 📄 hybrid_search.py       # Hybrid search (vector + BM25)
│   └── 📄 reranker.py            # Re-rank kết quả retrieve
│
├── 📁 calculator/                # Agent tính toán (PoT)
│   ├── 📄 __init__.py
│   ├── 📄 agent.py               # Calculator Agent logic
│   ├── 📄 sandbox.py             # Sandbox execution
│   ├── 📄 validator.py           # Validation kết quả
│   └── 📄 sql_agent.py           # SQL query generation
│
├── 📁 analysis/                  # Agent phân tích
│   ├── 📄 __init__.py
│   └── 📄 agent.py               # Analysis Agent logic
│
├── 📁 modeling/                  # Agent định giá
│   ├── 📄 __init__.py
│   ├── 📄 agent.py               # Modeling Agent logic
│   └── 📄 model_selector.py      # Logic chọn model phù hợp
│
├── 📁 synthesis/                 # Agent tổng hợp
│   ├── 📄 __init__.py
│   └── 📄 agent.py               # Synthesis Agent logic
│
├── 📁 debate/                    # Bull/Bear/Judge system
│   ├── 📄 __init__.py
│   ├── 📄 bull_agent.py          # Bull Agent (lạc quan)
│   ├── 📄 bear_agent.py          # Bear Agent (bi quan)
│   └── 📄 judge_agent.py         # Judge Agent (phán quyết)
│
├── 📁 report/                    # Agent viết báo cáo
│   ├── 📄 __init__.py
│   ├── 📄 agent.py               # Report Agent logic
│   └── 📄 pdf_exporter.py        # Export Markdown → PDF
│
└── 📁 evaluator/                 # Agent đánh giá chất lượng
    ├── 📄 __init__.py
    └── 📄 agent.py               # Evaluator Agent logic
```

### 📄 `src/agents/base_agent.py`
- **Nhiệm vụ:** Base class chung cho tất cả agents — tránh lặp code
- **Cần code:**
  - Class `BaseAgent(ABC)`:
    - `__init__(self, config, llm, prompt_template)`
    - `invoke(self, state) -> state` — method chính, mỗi agent override
    - `_load_prompt(self, template_name)` — load prompt từ `prompts/`
    - `_log_step(self, input, output, confidence)` — structured logging + provenance
  - Decorator `@track_tokens` — đếm token mỗi lần gọi LLM

---

### 📁 `src/agents/retriever/` — Retriever Agent

#### 📄 `src/agents/retriever/agent.py`
- **Nhiệm vụ:** Tìm kiếm và trả về chunks liên quan nhất từ Vector DB + MySQL
- **Cần code:**
  - Class `RetrieverAgent(BaseAgent)`
  - Hàm `invoke(state)`:
    1. Phân tích query → extract ticker, year, filters
    2. Gọi hybrid search (vector + BM25) với metadata filter
    3. Nếu retrieve được table summary → tự động fetch bảng gốc
    4. Trả về `state.retrieved_chunks`, `state.table_data`
  - Hàm `reformulate_query(query)` — reformulate khi retrieve ít kết quả
- **Task:** 3.1, 3.3, 3.4

#### 📄 `src/agents/retriever/hybrid_search.py`
- **Nhiệm vụ:** Kết hợp vector search + BM25 keyword search
- **Cần code:**
  - Hàm `hybrid_search(query, top_k, alpha, filters) -> list[Chunk]`
  - Alpha parameter: tỷ trọng vector vs keyword
  - Reciprocal Rank Fusion (RRF) để merge kết quả
- **Task:** 3.2

#### 📄 `src/agents/retriever/reranker.py`
- **Nhiệm vụ:** Re-rank kết quả sau retrieve để tăng precision
- **Cần code:**
  - Cross-encoder reranker hoặc LLM-based reranker
  - Input: query + candidate chunks → output: reranked chunks

---

### 📁 `src/agents/calculator/` — Calculator Agent (Program of Thought)

#### 📄 `src/agents/calculator/agent.py`
- **Nhiệm vụ:** Nhận câu hỏi tính toán → sinh Python code → thực thi → trả kết quả
- **Cần code:**
  - Class `CalculatorAgent(BaseAgent)`
  - Flow: query → LLM sinh Python code (sử dụng financial_functions) → sandbox execute → validate → return
  - Có access đến `src/finance/` library (import sẵn trong sandbox)
- **Task:** 3.7

#### 📄 `src/agents/calculator/sandbox.py`
- **Nhiệm vụ:** Chạy code LLM sinh ra trong môi trường an toàn
- **Cần code:**
  - Class `PythonSandbox`
  - Execute code trong Docker container hoặc `RestrictedPython`
  - Timeout, memory limit
  - Whitelist packages: `pandas`, `numpy`, `src.finance`
  - **KHÔNG BAO GIỜ** chạy trực tiếp trên host
- **Task:** 3.8

#### 📄 `src/agents/calculator/validator.py`
- **Nhiệm vụ:** Kiểm tra tính hợp lý của kết quả tính toán
- **Cần code:**
  - Hàm `validate_result(result, context) -> ValidationResult`
  - Rules: Tổng TS = Nợ + Vốn CSH, tỷ lệ không âm, % ≤ 100 (thường), YoY change hợp lý
  - Flag warning khi kết quả bất thường
- **Task:** 3.10

#### 📄 `src/agents/calculator/sql_agent.py`
- **Nhiệm vụ:** Sinh SQL query để truy vấn MySQL
- **Cần code:**
  - Class `SQLAgent` — LLM sinh SQL từ natural language
  - Schema-aware: inject MySQL schema vào prompt
  - SQL validation: chỉ cho phép SELECT, chặn DROP/DELETE/UPDATE
  - Execute query → trả kết quả dạng DataFrame
- **Task:** 3.11

---

### 📁 `src/agents/analysis/` — Analysis Agent

#### 📄 `src/agents/analysis/agent.py`
- **Nhiệm vụ:** Phân tích tài chính theo các framework chuẩn
- **Cần code:**
  - Class `AnalysisAgent(BaseAgent)`
  - Methods phân tích:
    - `dupont_analysis(data)` — phân tích ROE theo DuPont 3/5 bước
    - `trend_analysis(data)` — phân tích xu hướng qua các năm
    - `common_size_analysis(data)` — phân tích tỷ trọng
    - `peer_comparison(company_data, peer_data)` — so sánh cùng ngành
  - Output: structured JSON cho Synthesis Agent
- **Task:** 3.12, 3.13, 3.14, 3.15

---

### 📁 `src/agents/modeling/` — Modeling Agent (Định giá)

#### 📄 `src/agents/modeling/agent.py`
- **Nhiệm vụ:** Chạy các mô hình định giá cổ phiếu
- **Cần code:**
  - Class `ModelingAgent(BaseAgent)`
  - Gọi functions từ `src/finance/valuation.py` (deterministic code)
  - LLM chỉ làm: chọn model phù hợp + đề xuất assumptions
  - Output: valuation result + sensitivity analysis
- **Task:** 4.1–4.5

#### 📄 `src/agents/modeling/model_selector.py`
- **Nhiệm vụ:** LLM chọn mô hình định giá phù hợp dựa trên loại công ty
- **Cần code:**
  - Input: industry, data availability, company characteristics
  - Output: recommended model(s): DCF, DDM, Comparable, ...
  - Logic: công ty trả cổ tức → DDM, công ty growth → DCF, ...
- **Task:** 4.6

---

### 📁 `src/agents/synthesis/` — Synthesis Agent

#### 📄 `src/agents/synthesis/agent.py`
- **Nhiệm vụ:** Tổng hợp kết quả từ Analysis + Modeling thành structured data
- **Cần code:**
  - Class `SynthesisAgent(BaseAgent)`
  - Input: analysis results, valuation results, retrieved context
  - Output: `SynthesisResult` (structured JSON) — chứa:
    - Company overview, key metrics, analysis summary, valuation, risks, strengths
  - Đây là input cho Bull/Bear Agents
- **Task:** 4.8

---

### 📁 `src/agents/debate/` — Bull/Bear/Judge System

#### 📄 `src/agents/debate/bull_agent.py`
- **Nhiệm vụ:** Phân tích với góc nhìn lạc quan — tìm điểm mạnh
- **Cần code:**
  - Class `BullAgent(BaseAgent)` với system prompt thiên lạc quan
  - Input: SynthesisResult (cùng input với Bear)
  - Output: Luận điểm tích cực (thesis, evidence, risk mitigation)
- **Task:** 4.12

#### 📄 `src/agents/debate/bear_agent.py`
- **Nhiệm vụ:** Phân tích với góc nhìn bi quan — tìm rủi ro
- **Cần code:**
  - Class `BearAgent(BaseAgent)` với system prompt thiên bi quan
  - Input: SynthesisResult (cùng input với Bull)
  - Output: Luận điểm tiêu cực (risks, weaknesses, concerns)
- **Task:** 4.13

#### 📄 `src/agents/debate/judge_agent.py`
- **Nhiệm vụ:** Đánh giá cả 2 luận điểm Bull/Bear theo rubric scoring
- **Cần code:**
  - Class `JudgeAgent(BaseAgent)`
  - Input: bull_thesis + bear_thesis
  - Rubric: data_quality (0-10), logic_consistency (0-10), assumption_reasonableness (0-10)
  - Output: verdict, scores, final recommendation
- **Task:** 4.14, 4.15

---

### 📁 `src/agents/report/` — Report Agent

#### 📄 `src/agents/report/agent.py`
- **Nhiệm vụ:** Sinh báo cáo phân tích hoàn chỉnh từ structured data
- **Cần code:**
  - Class `ReportAgent(BaseAgent)`
  - Load Jinja2 template → LLM fill content
  - Output: Markdown report
  - Sections: Executive Summary, Company Overview, Financial Analysis, Valuation, Bull/Bear Cases, Conclusion
- **Task:** 4.9, 4.10

#### 📄 `src/agents/report/pdf_exporter.py`
- **Nhiệm vụ:** Chuyển Markdown report → PDF
- **Cần code:**
  - Dùng `weasyprint` hoặc `reportlab`
  - Styling: header, footer, page numbers, table formatting
- **Task:** 4.11

---

### 📁 `src/agents/evaluator/` — Evaluator Agent

#### 📄 `src/agents/evaluator/agent.py`
- **Nhiệm vụ:** Kiểm tra tính nhất quán kết quả, trigger retry khi confidence thấp
- **Cần code:**
  - Class `EvaluatorAgent(BaseAgent)`
  - Checks: cross-check số liệu giữa các agents, confidence scoring
  - Decision: PASS → tiếp tục, RETRY → retry với query reformulation
  - Selective reflection: chỉ chạy khi có tín hiệu bất thường (tiết kiệm token)
- **Task:** 5.6

---

## 📁 `src/orchestrator/` — LangGraph Orchestration (Phase 5)

```
src/orchestrator/
├── 📄 __init__.py
├── 📄 state.py                   # TypedDict state definition
├── 📄 graph.py                   # LangGraph graph definition
├── 📄 router.py                  # Adaptive Strategy Router
├── 📄 nodes.py                   # Node functions (wrap agents)
├── 📄 edges.py                   # Conditional edge logic
└── 📄 provenance.py              # Provenance tracking
```

### 📄 `src/orchestrator/state.py`
- **Nhiệm vụ:** Định nghĩa state TypedDict cho toàn bộ LangGraph graph
- **Cần code:**
  ```python
  class FinancialAnalysisState(TypedDict):
      query: str
      query_type: Literal["simple", "calculate", "analysis", "valuation"]
      company_ticker: str
      fiscal_years: list[int]
      retrieved_chunks: list[Document]
      table_data: dict
      calculation_results: dict
      analysis: dict
      valuation: dict
      synthesis: dict
      bull_thesis: str
      bear_thesis: str
      judge_verdict: dict
      confidence_score: float
      retry_count: int
      max_retries: int
      final_report: str
      provenance: list[dict]
      errors: list[str]
  ```
- **Task:** 5.1

### 📄 `src/orchestrator/graph.py`
- **Nhiệm vụ:** Định nghĩa LangGraph graph — nodes, edges, conditional edges
- **Cần code:**
  - Build graph: `StateGraph(FinancialAnalysisState)`
  - Add nodes: router, retriever, calculator, analysis, modeling, synthesis, debate, report, evaluator
  - Add edges: conditional routing dựa trên query_type
  - Compile graph → `app = graph.compile()`
- **Task:** 5.2

### 📄 `src/orchestrator/router.py`
- **Nhiệm vụ:** Adaptive Strategy Router — phân loại complexity và route query
- **Cần code:**
  - Hàm `classify_query(query) -> QueryType`
  - 4 tiers: Lookup → Calculate → Analysis → Valuation
  - Dùng LLM nhỏ (Flash) hoặc rule-based classifier
- **Task:** 5.3

### 📄 `src/orchestrator/nodes.py`
- **Nhiệm vụ:** Wrap mỗi agent thành một node function cho LangGraph
- **Cần code:**
  - Mỗi hàm nhận `state` → gọi agent → update state → return state
  - Hàm `retriever_node(state)`, `calculator_node(state)`, `analysis_node(state)`, ...
- **Task:** 5.4, 5.5

### 📄 `src/orchestrator/edges.py`
- **Nhiệm vụ:** Logic cho conditional edges (rẽ nhánh trong graph)
- **Cần code:**
  - `should_retry(state) -> str` — "retry" nếu confidence thấp, "continue" nếu ok
  - `route_by_complexity(state) -> str` — "simple" | "complex"
  - `should_run_debate(state) -> str` — chỉ chạy debate cho valuation queries
- **Task:** 5.7

### 📄 `src/orchestrator/provenance.py`
- **Nhiệm vụ:** Ghi log nguồn gốc mỗi con số, mỗi bước reasoning
- **Cần code:**
  - Class `ProvenanceTracker`
  - Log: agent_name, input, output, source_chunks, page_numbers, confidence
  - Export provenance chain cho report
- **Task:** 5.9

---

## 📁 `src/finance/` — Financial Functions Library

> [!IMPORTANT]
> **Deterministic code** — tất cả tính toán tài chính là pure Python functions. LLM KHÔNG tính toán, chỉ gọi hàm.

```
src/finance/
├── 📄 __init__.py
├── 📄 ratios.py                  # Chỉ số tài chính cơ bản
├── 📄 valuation.py               # Mô hình định giá
├── 📄 analysis_frameworks.py     # DuPont, Common-size
└── 📄 simulation.py              # Monte Carlo simulation
```

### 📄 `src/finance/ratios.py`
- **Nhiệm vụ:** Bộ hàm tính chỉ số tài chính — PHẢI deterministic, KHÔNG dùng LLM
- **Cần code:**
  - Liquidity: `current_ratio()`, `quick_ratio()`
  - Profitability: `roe()`, `roa()`, `gross_margin()`, `net_margin()`, `ebitda_margin()`
  - Leverage: `debt_to_equity()`, `interest_coverage()`
  - Efficiency: `asset_turnover()`, `inventory_turnover()`
  - Growth: `cagr()`, `yoy_growth()`
  - Valuation: `pe_ratio()`, `pb_ratio()`, `ev_ebitda()`
- **Task:** 3.9

### 📄 `src/finance/valuation.py`
- **Nhiệm vụ:** Mô hình định giá cổ phiếu — pure Python
- **Cần code:**
  - `dcf_model(free_cash_flows, discount_rate, terminal_growth, years) -> float`
  - `ddm_model(dividends, required_return, growth_rate) -> float`
  - `wacc(equity_weight, cost_equity, debt_weight, cost_debt, tax_rate) -> float`
  - `comparable_analysis(peer_multiples, company_metric) -> dict`
- **Task:** 4.1, 4.2, 4.3, 4.4

### 📄 `src/finance/analysis_frameworks.py`
- **Nhiệm vụ:** Framework phân tích tài chính
- **Cần code:**
  - `dupont_3step(net_income, revenue, assets, equity) -> dict` — Profit Margin x Asset Turnover x Equity Multiplier
  - `dupont_5step(...)` — 5 thành phần
  - `common_size_analysis(data, base_item) -> dict` — tính tỷ trọng
  - `trend_analysis(data_series) -> dict` — xu hướng + CAGR
- **Task:** 3.12, 3.13, 3.14

### 📄 `src/finance/simulation.py`
- **Nhiệm vụ:** Monte Carlo simulation cho mô hình định giá
- **Cần code:**
  - `monte_carlo_dcf(assumptions_ranges, n_simulations) -> SimulationResult`
  - Output: distribution of valuations, confidence intervals
- **Task:** 4.5

---

## 📁 `src/ui/` — User Interface (Phase 6)

```
src/ui/
├── 📄 __init__.py
├── 📄 cli.py                     # Command-line interface
├── 📄 streamlit_app.py           # Web chat interface
├── 📁 templates/                 # Jinja2 report templates
│   ├── 📄 report_template.md     # Template báo cáo Markdown
│   └── 📄 report_style.css       # CSS cho PDF export
└── 📁 components/                # Streamlit components
    ├── 📄 chat.py                # Chat interface component
    ├── 📄 upload.py              # PDF upload component
    ├── 📄 status.py              # Processing status display
    └── 📄 report_viewer.py       # Report display + download
```

### 📄 `src/ui/cli.py`
- **Nhiệm vụ:** CLI cơ bản — MVP interface
- **Cần code:**
  - Dùng `click` hoặc `argparse`
  - Commands: `analyze <pdf_path> --ticker VNM --years 2023`, `query "Câu hỏi"`, `report --output report.pdf`
- **Task:** 6.1

### 📄 `src/ui/streamlit_app.py`
- **Nhiệm vụ:** Web chat interface — Streamlit app
- **Cần code:**
  - Chat UI: input box, message history, streaming response
  - Sidebar: PDF upload, ticker selection, year filter
  - Main area: chat + report display
  - Processing status bar: hiển thị agent nào đang chạy
- **Task:** 6.2, 6.3, 6.4, 6.5, 6.6, 6.7

### 📄 `src/ui/templates/report_template.md`
- **Nhiệm vụ:** Jinja2 template cho báo cáo phân tích
- **Cần code:**
  - Sections: Executive Summary, Company Overview, Financial Highlights, Analysis, Valuation, Risk Assessment, Conclusion
  - Placeholders: `{{ company_name }}`, `{{ key_metrics }}`, `{{ analysis_text }}`, ...
- **Task:** 4.9

---

## 📁 `src/utils/` — Tiện ích dùng chung

```
src/utils/
├── 📄 __init__.py
├── 📄 logger.py                  # Structured logging setup
├── 📄 token_tracker.py           # Token usage tracking
├── 📄 cache.py                   # LLM response cache + computed metrics cache
├── 📄 rate_limiter.py            # Rate limit handling cho LLM API
└── 📄 errors.py                  # Custom exception classes
```

### 📄 `src/utils/logger.py`
- **Nhiệm vụ:** Setup structured logging (JSON format)
- **Cần code:** JSON formatter, file + console handlers, per-module log levels
- **Task:** 0.6

### 📄 `src/utils/token_tracker.py`
- **Nhiệm vụ:** Theo dõi token usage theo agent, theo query
- **Cần code:** Decorator `@track_tokens`, dashboard data aggregation
- **Task:** 7.9

### 📄 `src/utils/cache.py`
- **Nhiệm vụ:** Cache layer cho LLM responses và computed metrics
- **Cần code:**
  - `LLMCache`: hash(query + context) → cached response
  - `MetricsCache`: lưu chỉ số đã tính vào DB, không tính lại
- **Task:** 7.10, 7.11

### 📄 `src/utils/rate_limiter.py`
- **Nhiệm vụ:** Retry policy khi LLM API bị rate limit
- **Cần code:** Exponential backoff, max retries, jitter
- **Task:** 7.12

### 📄 `src/utils/errors.py`
- **Nhiệm vụ:** Custom exceptions cho toàn hệ thống
- **Cần code:** `OCRError`, `RetrievalError`, `CalculationError`, `APIError`, `SandboxError`, `ValidationError`
- **Task:** 5.8

---

## 📁 `tests/` — Testing (Phase 7)

```
tests/
├── 📄 conftest.py                # Pytest fixtures dùng chung
├── 📄 test_config.yaml           # Config riêng cho test environment
│
├── 📁 unit/                      # Unit tests
│   ├── 📄 test_pdf_classifier.py
│   ├── 📄 test_text_chunker.py
│   ├── 📄 test_table_chunker.py
│   ├── 📄 test_financial_ratios.py
│   ├── 📄 test_valuation.py
│   ├── 📄 test_sandbox.py
│   └── 📄 test_hybrid_search.py
│
├── 📁 integration/               # Integration tests
│   ├── 📄 test_ingestion_pipeline.py
│   ├── 📄 test_retriever_agent.py
│   ├── 📄 test_calculator_agent.py
│   └── 📄 test_full_graph.py
│
├── 📁 evaluation/                # Quality evaluation
│   ├── 📄 golden_test_set.json   # 50+ câu hỏi + đáp án chuẩn
│   ├── 📄 eval_retrieval.py      # Đo precision/recall retriever
│   ├── 📄 eval_calculation.py    # So sánh tính toán vs manual
│   └── 📄 eval_report.py         # Checklist chất lượng báo cáo
│
└── 📁 fixtures/                  # Test data
    ├── 📄 sample_native.pdf      # PDF native mẫu
    ├── 📄 sample_scan.pdf        # PDF scan mẫu
    └── 📄 expected_outputs.json  # Expected outputs cho test
```

- **Task:** 7.1–7.5

---

## 📁 `data/` — Dữ liệu

```
data/
├── 📁 raw/                       # PDF gốc (KHÔNG commit vào Git)
│   └── 📄 .gitkeep
├── 📁 processed/                 # Dữ liệu đã xử lý
│   └── 📄 .gitkeep
├── 📁 embeddings_cache/          # Cache embeddings
│   └── 📄 .gitkeep
└── 📁 training/                  # Training data cho fine-tuning (Phase sau)
    ├── 📄 triplets.jsonl         # Contrastive learning triplets
    └── 📄 .gitkeep
```

> [!WARNING]
> Thư mục `data/raw/` chứa PDF gốc — **KHÔNG commit vào Git** (add vào .gitignore). Chỉ commit `.gitkeep` để giữ folder structure.

---

## 📁 `scripts/` — Utility Scripts

```
scripts/
├── 📄 init_db.py                 # Tạo bảng MySQL, setup schema
├── 📄 ingest_pdf.py              # Script chạy full ingestion pipeline cho 1 PDF
├── 📄 build_embeddings.py        # Batch embed tất cả chunks
├── 📄 generate_training_data.py  # Tạo triplets cho contrastive learning
└── 📄 run_evaluation.py          # Chạy evaluation suite
```

---

## 📁 `notebooks/` — Jupyter Notebooks (Thí nghiệm)

```
notebooks/
├── 📄 01_pdf_extraction_test.ipynb    # Thí nghiệm extract PDF
├── 📄 02_chunking_experiment.ipynb    # Thí nghiệm chunking strategies
├── 📄 03_retrieval_quality.ipynb      # Đánh giá retrieval
└── 📄 04_agent_prompting.ipynb        # Thí nghiệm prompt cho agents
```

---

## 📁 `docs/` — Tài liệu dự án

```
docs/
├── 📄 Architecture.md            # Thiết kế kiến trúc (file hiện tại)
├── 📄 feature_list.md            # Danh sách task (file hiện tại)
├── 📄 suggestion.md              # Gợi ý thiết kế (file hiện tại)
├── 📄 folder_structure.md        # File này
├── 📄 api_reference.md           # API documentation
└── 📄 deployment_guide.md        # Hướng dẫn deploy
```

---

## Tổng kết cấu trúc

| Thư mục | Số files (ước tính) | Phase liên quan | Mô tả |
|---------|---------------------|-----------------|-------|
| `configs/` | 4 | Phase 0 | Cấu hình YAML tập trung |
| `prompts/` | 14 | Phase 3, 4 | Prompt templates version-controlled |
| `src/ingestion/` | 12 | Phase 1 | Pipeline xử lý PDF + API |
| `src/chunking/` | 7 | Phase 2 | Chunking + embedding |
| `src/database/` | 5 | Phase 2 | MySQL + Vector DB layer |
| `src/agents/` | ~20 | Phase 3, 4 | Tất cả agents |
| `src/orchestrator/` | 6 | Phase 5 | LangGraph orchestration |
| `src/finance/` | 4 | Phase 3, 4 | Deterministic financial functions |
| `src/ui/` | ~8 | Phase 6 | CLI + Streamlit UI |
| `src/utils/` | 5 | Phase 0, 7 | Logging, caching, error handling |
| `tests/` | ~15 | Phase 7 | Unit + integration + evaluation |
| **Tổng** | **~100 files** | | |

> [!TIP]
> **Bắt đầu từ đâu?** Theo MVP scope:
> 1. Root files + `configs/` (Phase 0)
> 2. `src/ingestion/` (Phase 1)
> 3. `src/chunking/` + `src/database/` (Phase 2)
> 4. `src/orchestrator/state.py` + `graph.py` (Phase 5 — làm sớm!)
> 5. `src/agents/retriever/` + `src/agents/calculator/` + `src/finance/ratios.py` (Phase 3)
> 6. `src/ui/cli.py` (Phase 6 — MVP)
