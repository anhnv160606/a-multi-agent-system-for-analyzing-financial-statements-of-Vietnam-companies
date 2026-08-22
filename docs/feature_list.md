# Feature List & Task Checklist

> [!NOTE]
> Checklist đầu việc cho team 2 người. Đánh dấu `[x]` khi hoàn thành, `[/]` khi đang làm.
> Cột **Người** gợi ý phân công — team tự điều chỉnh phù hợp.

---

## Phase 0: Project Setup & Foundation

| # | Task | Chi tiết | Người | Status |
|---|------|----------|-------|--------|
| 0.1 | Khởi tạo project structure | Tạo folder structure chuẩn (src, tests, configs, prompts, data, ...) | A | `[ ]` |
| 0.2 | Setup Python environment | pyproject.toml / requirements.txt, Python 3.11+ | A | `[ ]` |
| 0.3 | Cài đặt LangGraph + dependencies | langchain, langgraph, chromadb, pdfplumber, ... | A | `[ ]` |
| 0.4 | Setup Docker Compose | MySQL, ChromaDB/Qdrant, app containers | B | `[ ]` |
| 0.5 | Config management | File YAML config cho tất cả tham số (model, temperature, chunk_size, ...) | A | `[ ]` |
| 0.6 | Setup logging framework | Structured logging (JSON), file + console output | B | `[ ]` |
| 0.7 | Setup Git workflow | Branch strategy, PR template, .gitignore | A+B | `[ ]` |

---

## Phase 1: Data Ingestion Pipeline

### 1A. PDF Processing

| # | Task | Chi tiết | Người | Status |
|---|------|----------|-------|--------|
| 1.1 | PDF Classifier | Tự động phân loại PDF scan vs PDF native (heuristic: thử extract text, nếu rỗng → scan) | A | `[ ]` |
| 1.2 | OCR Pipeline (PDF scan) | Tích hợp Tesseract/PaddleOCR cho PDF scan. Test trên BCTC thật | A | `[ ]` |
| 1.3 | Text Extraction (PDF native) | Dùng pdfplumber / LlamaParse cho PDF có text layer | A | `[ ]` |
| 1.4 | Table Extraction | Dùng Docling / pdfplumber / Camelot. Xuất dạng Markdown/CSV | B | `[ ]` |
| 1.5 | Image Extraction | Trích xuất hình ảnh từ PDF (biểu đồ, sơ đồ) | B | `[ ]` |
| 1.6 | Image Processing | Chart-to-data extraction (DePlot) hoặc VLM captioning cho biểu đồ | B | `[ ]` |
| 1.7 | Document Splitter | Tách PDF thành 3 luồng: Text, Table, Images | A | `[ ]` |

### 1B. API Data

| # | Task | Chi tiết | Người | Status |
|---|------|----------|-------|--------|
| 1.8 | VNStock API Integration | Kết nối VNStock, lấy: giá lịch sử, thông tin DN, tin tức | B | `[ ]` |
| 1.9 | API Data Caching | Cache kết quả API để tránh gọi lại + fallback khi API down | B | `[ ]` |
| 1.10 | Cross-validation module | Đối chiếu số liệu extract từ PDF với dữ liệu API | A+B | `[ ]` |

---

## Phase 2: Chunking & Storage

### 2A. Chunking Strategy

| # | Task | Chi tiết | Người | Status |
|---|------|----------|-------|--------|
| 2.1 | Text Chunking | Semantic paragraph chunking (RecursiveCharacterTextSplitter hoặc custom) | A | `[ ]` |
| 2.2 | Table-aware Chunking | Bảng nhỏ → giữ nguyên. Bảng lớn → LLM tạo summary, lưu bảng gốc riêng | A | `[ ]` |
| 2.3 | Hierarchical Chunking | Parent-child chunking cho văn bản (Section → Paragraph → Sentence) | A | `[ ]` |
| 2.4 | Metadata Enrichment | Gắn metadata mỗi chunk: `{ticker, year, report_type, section, page, source_file}` | A | `[ ]` |
| 2.5 | Cross-reference Linking | Liên kết text chunk ↔ table chunk khi có tham chiếu chéo | A | `[ ]` |

### 2B. Database Setup

| # | Task | Chi tiết | Người | Status |
|---|------|----------|-------|--------|
| 2.6 | MySQL Schema Design | Thiết kế bảng: companies, financial_data, source_documents | B | `[ ]` |
| 2.7 | MySQL Data Loader | Script load bảng số liệu đã extract vào MySQL | B | `[ ]` |
| 2.8 | Vector DB Setup | Cài đặt ChromaDB (dev) / Qdrant (prod), tạo collection | B | `[ ]` |
| 2.9 | Embedding Pipeline | Chọn embedding model (bge-m3 / multilingual-e5), pipeline embed + upsert | A | `[ ]` |
| 2.10 | Embedding Cache | Tránh re-embed cùng một document | B | `[ ]` |

---

## Phase 3: Core Agents (MVP)

### 3A. Retriever Agent

| # | Task | Chi tiết | Người | Status |
|---|------|----------|-------|--------|
| 3.1 | Basic RAG Retriever | Vector similarity search cơ bản, trả về top-k chunks | A | `[ ]` |
| 3.2 | Hybrid Search | Kết hợp embedding search + BM25 keyword search | A | `[ ]` |
| 3.3 | Metadata Filtering | Filter theo ticker, year, report_type khi retrieve | A | `[ ]` |
| 3.4 | Table Retrieval | Khi retrieve được table summary → tự động fetch bảng gốc | A | `[ ]` |
| 3.5 | Contrastive Financial Retriever | Fine-tune embedding model với triplets tài chính VN (giai đoạn sau) | A | `[ ]` |
| 3.6 | Training Data Generation | Tạo bộ (anchor, positive, hard_negative) từ BCTC thật | A | `[ ]` |

### 3B. Calculator Agent (Program of Thought)

| # | Task | Chi tiết | Người | Status |
|---|------|----------|-------|--------|
| 3.7 | PoT Code Generation | LLM sinh Python code từ câu hỏi tài chính | B | `[ ]` |
| 3.8 | Sandbox Execution | Docker container / restricted Python để chạy code sinh ra | B | `[ ]` |
| 3.9 | Financial Functions Library | Bộ hàm sẵn: ROE, ROA, CAGR, P/E, EV/EBITDA, Current Ratio, ... | B | `[ ]` |
| 3.10 | Calculation Validation | Kiểm tra tính hợp lý (Tổng TS = Nợ + Vốn CSH, tỷ lệ không âm, ...) | B | `[ ]` |
| 3.11 | SQL Query Agent | Agent sinh SQL query để truy vấn MySQL (bảng số liệu) | B | `[ ]` |

### 3C. Analysis Agent

| # | Task | Chi tiết | Người | Status |
|---|------|----------|-------|--------|
| 3.12 | DuPont Analysis | Phân tích ROE theo framework DuPont 3 bước / 5 bước | A | `[ ]` |
| 3.13 | Trend Analysis | Phân tích xu hướng qua các năm (revenue growth, margin trend) | A | `[ ]` |
| 3.14 | Common-size Analysis | Phân tích tỷ trọng (mỗi mục / tổng tài sản or doanh thu) | A | `[ ]` |
| 3.15 | Peer Comparison | So sánh chỉ số với công ty cùng ngành | A+B | `[ ]` |

---

## Phase 4: Advanced Agents

### 4A. Modeling Agent (Định giá)

| # | Task | Chi tiết | Người | Status |
|---|------|----------|-------|--------|
| 4.1 | DCF Model | Deterministic Python function cho Discounted Cash Flow | B | `[ ]` |
| 4.2 | DDM Model | Dividend Discount Model | B | `[ ]` |
| 4.3 | WACC Calculator | Tính Weighted Average Cost of Capital | B | `[ ]` |
| 4.4 | Comparable Company Analysis | P/E, EV/EBITDA so sánh với peer group | B | `[ ]` |
| 4.5 | Monte Carlo Simulation | Mô phỏng với range input assumptions | B | `[ ]` |
| 4.6 | Model Selection Logic | LLM chọn model phù hợp dựa trên loại công ty + data availability | A | `[ ]` |
| 4.7 | Assumption Management | Hệ thống quản lý input assumptions (LLM đề xuất, human xác nhận?) | A+B | `[ ]` |

### 4B. Synthesis & Report

| # | Task | Chi tiết | Người | Status |
|---|------|----------|-------|--------|
| 4.8 | Synthesis Agent | Tổng hợp kết quả từ Analysis + Modeling thành structured JSON | A | `[ ]` |
| 4.9 | Report Template | Thiết kế template báo cáo (Jinja2) | A | `[ ]` |
| 4.10 | Report Agent | LLM fill content vào template, sinh báo cáo Markdown | A | `[ ]` |
| 4.11 | PDF Export | Chuyển báo cáo Markdown → PDF | A | `[ ]` |

### 4C. Debate System (Bull/Bear/Judge)

| # | Task | Chi tiết | Người | Status |
|---|------|----------|-------|--------|
| 4.12 | Bull Agent | System prompt thiên về lạc quan, tìm điểm mạnh | B | `[ ]` |
| 4.13 | Bear Agent | System prompt thiên về bi quan, tìm rủi ro | B | `[ ]` |
| 4.14 | Judge Agent | Đánh giá cả 2 luận điểm theo rubric scoring | B | `[ ]` |
| 4.15 | Rubric Design | Thiết kế bảng điểm: data quality, logic, assumptions | A+B | `[ ]` |

---

## Phase 5: Orchestration & System Integration

| # | Task | Chi tiết | Người | Status |
|---|------|----------|-------|--------|
| 5.1 | LangGraph State Design | Thiết kế TypedDict state cho toàn bộ graph | A | `[ ]` |
| 5.2 | Graph Definition | Định nghĩa nodes, edges, conditional edges trong LangGraph | A | `[ ]` |
| 5.3 | Adaptive Strategy Router | Classify query complexity → route tới pipeline phù hợp | B | `[ ]` |
| 5.4 | Simple Query Path | Single RAG pass cho câu hỏi tra cứu đơn giản | A | `[ ]` |
| 5.5 | Complex Query Path | Full pipeline cho câu hỏi phân tích phức tạp | A | `[ ]` |
| 5.6 | Evaluator Agent | Kiểm tra tính nhất quán kết quả, trigger retry khi confidence thấp | B | `[ ]` |
| 5.7 | Retry / Reflection Loop | Logic retry với query reformulation khi retrieve fail | B | `[ ]` |
| 5.8 | Error Handling | Fallback khi OCR fail, API down, LLM timeout | A+B | `[ ]` |
| 5.9 | Provenance Tracking | Ghi log nguồn gốc mỗi con số: Agent nào, chunk nào, trang nào | A | `[ ]` |
| 5.10 | End-to-end Integration Test | Chạy full pipeline từ PDF → Report trên 1 công ty thật | A+B | `[ ]` |

---

## Phase 6: UI & User Experience

| # | Task | Chi tiết | Người | Status |
|---|------|----------|-------|--------|
| 6.1 | CLI Interface | Command-line interface cơ bản (MVP) | B | `[ ]` |
| 6.2 | Web Chat Interface | Streamlit / Gradio chat UI | A | `[ ]` |
| 6.3 | PDF Upload | UI cho user upload BCTC (PDF) | A | `[ ]` |
| 6.4 | Processing Status | Hiển thị tiến trình xử lý (Agent nào đang chạy) | A | `[ ]` |
| 6.5 | Streaming Response | Stream output từng bước (LangGraph streaming) | B | `[ ]` |
| 6.6 | Report Display | Hiển thị báo cáo cuối (Markdown rendered + download PDF) | A | `[ ]` |
| 6.7 | Source Citation UI | Hiển thị nguồn trích dẫn (click để xem trang PDF gốc) | B | `[ ]` |

---

## Phase 7: Quality, Testing & Operations

### 7A. Evaluation

| # | Task | Chi tiết | Người | Status |
|---|------|----------|-------|--------|
| 7.1 | Golden Test Set | Tạo bộ 50+ câu hỏi + đáp án chuẩn từ BCTC thật | A+B | `[ ]` |
| 7.2 | Retrieval Accuracy Test | Đo precision/recall của Retriever Agent trên test set | A | `[ ]` |
| 7.3 | Calculation Correctness Test | So sánh kết quả tính toán Agent vs manual calculation | B | `[ ]` |
| 7.4 | Report Quality Eval | Human evaluation chất lượng báo cáo (checklist) | A+B | `[ ]` |
| 7.5 | Regression Test Suite | Automated test chạy khi merge PR | A | `[ ]` |

### 7B. MLOps / LLMOps

| # | Task | Chi tiết | Người | Status |
|---|------|----------|-------|--------|
| 7.6 | Prompt Version Control | Lưu tất cả prompt templates vào `prompts/` folder, đánh version | A | `[ ]` |
| 7.7 | Experiment Tracking | Setup MLflow / W&B để track prompt version + metrics | B | `[ ]` |
| 7.8 | LangSmith Integration | Tích hợp LangSmith cho LLM observability | B | `[ ]` |
| 7.9 | Token Usage Dashboard | Theo dõi chi phí token theo Agent, theo query type | B | `[ ]` |

### 7C. Performance & Security

| # | Task | Chi tiết | Người | Status |
|---|------|----------|-------|--------|
| 7.10 | LLM Response Cache | Cache response cho cùng query + context | B | `[ ]` |
| 7.11 | Computed Metrics Cache | Lưu chỉ số tài chính đã tính vào DB | A | `[ ]` |
| 7.12 | Rate Limit Handling | Retry policy khi LLM API bị rate limit | B | `[ ]` |
| 7.13 | Data Privacy Review | Đánh giá data residency khi dùng cloud LLM API | A+B | `[ ]` |

---

## Tổng kết

| Phase | Số task | Ước tính thời gian (2 người) |
|-------|---------|------------------------------|
| Phase 0: Setup | 7 | 1 tuần |
| Phase 1: Data Ingestion | 10 | 2-3 tuần |
| Phase 2: Chunking & Storage | 10 | 2 tuần |
| Phase 3: Core Agents | 16 | 3-4 tuần |
| Phase 4: Advanced Agents | 15 | 3-4 tuần |
| Phase 5: Orchestration | 10 | 2-3 tuần |
| Phase 6: UI | 7 | 2 tuần |
| Phase 7: Quality & Ops | 13 | 2-3 tuần |
| **Tổng** | **88 tasks** | **~17-22 tuần (~4-5 tháng)** |

> [!TIP]
> **MVP khuyến nghị (8-10 tuần):** Phase 0 + Phase 1 + Phase 2 + Phase 3 + Phase 5 (minimal) + Phase 6.1 (CLI only). Đủ để chạy end-to-end trên 1 công ty thật, sau đó iterate thêm.
