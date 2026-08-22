# Gợi ý & Lời khuyên cho Thiết kế Kiến trúc

> [!NOTE]
> File này **bổ sung** cho [Architecture.md](file:///c:/Users/Lenovo/OneDrive/Desktop/AI%20AGENT/a-multi-agent-system-for-analyzing-financial-statements-of-Vietnam-companies/Architecture.md) — không sửa đổi file gốc.

---

## 1. Dataset & Xử lý Dữ liệu — Các điểm còn mơ hồ

### 1.1. PDF Scan vs PDF Native — cần phân biệt rõ pipeline

Architecture.md ghi nhận cả "pdf scan" (BCTC, tài liệu ĐHCĐ) và "pdf" (báo cáo thường niên). Đây là 2 luồng xử lý **hoàn toàn khác nhau**:

| Loại PDF | Đặc điểm | Pipeline đề xuất |
|---|---|---|
| PDF scan (hình ảnh) | Không có text layer, bảng số liệu là ảnh | OCR trước (Tesseract / PaddleOCR / Google Vision API) → rồi mới tới Docling/pdfplumber |
| PDF native (text-based) | Có text layer sẵn | Trực tiếp dùng pdfplumber / LlamaParse |

> [!IMPORTANT]
> **Gợi ý:** Nên thêm một bước **PDF Classification** ở đầu pipeline để tự động phân loại loại PDF (scan vs native) trước khi chọn pipeline xử lý. Có thể dùng heuristic đơn giản: thử extract text bằng pdfplumber, nếu trả về rỗng → là scan → chuyển sang OCR pipeline.

### 1.2. Luồng Images chưa được mô tả chi tiết

Architecture.md đề cập chia tài liệu thành 3 luồng: **Text, Table, Images** — nhưng chỉ mô tả chi tiết cho Text và Table. Luồng Images cần làm rõ:

- **Loại hình ảnh nào cần xử lý?** Biểu đồ (chart), sơ đồ tổ chức, ảnh minh hoạ?
- **Kỹ thuật xử lý:** Dùng VLM (Vision Language Model) để mô tả hình ảnh (image captioning) → lưu caption vào Vector DB? Hay dùng chart-to-table extraction (DePlot, ChartOCR)?
- **Hình ảnh có cần lưu riêng không?** Nếu có → cần thêm một storage layer (object storage / file system).

> [!TIP]
> **Gợi ý:** Đối với báo cáo thường niên Việt Nam, phần lớn hình ảnh là biểu đồ cột/tròn. Nên ưu tiên **chart-to-data extraction** (chuyển biểu đồ thành bảng số liệu) rồi merge vào luồng Table. Ảnh minh hoạ (ảnh ban lãnh đạo, ảnh nhà máy) có thể bỏ qua hoặc chỉ lưu caption.

### 1.3. Nguồn dữ liệu VNStock API — cần xác định scope

Bạn ghi "Tin tức về doanh nghiệp (api vnstock)" nhưng VNStock cung cấp nhiều hơn tin tức:
- Giá lịch sử (OHLCV)
- Thông tin cơ bản doanh nghiệp (vốn điều lệ, ngành, sàn niêm yết)
- Chỉ số tài chính cơ bản
- Tin tức

> **Gợi ý:** Xác định rõ sẽ lấy **những endpoint nào** của VNStock. Nếu đã extract bảng số liệu từ BCTC thì dữ liệu chỉ số tài chính từ API có thể **dùng để cross-validate** (đối chiếu) kết quả extract.

---

## 2. Chunking Strategy — Gợi ý bổ sung

### 2.1. Chiến lược Table-aware chunking rất tốt, nhưng thiếu chi tiết triển khai

Mô tả hiện tại rất chặt chẽ về mặt lý thuyết. Tuy nhiên cần làm rõ:

- **Ngưỡng kích thước bảng** để quyết định khi nào cần tóm tắt (ví dụ: > 2000 tokens → tạo summary).
- **Metadata gắn kèm mỗi chunk:** Nên include `{source_file, page_number, table_id, fiscal_year, company_ticker, section_name}` để tăng độ chính xác khi retrieve.
- **Liên kết cross-reference:** Khi một đoạn văn bản tham chiếu tới một bảng ("Xem Bảng 5"), cần lưu relationship giữa text chunk và table chunk.

### 2.2. Đề xuất thêm: Hierarchical Chunking cho văn bản

Báo cáo tài chính có cấu trúc phân cấp rõ ràng (Phần → Mục → Đoạn). Nên xem xét **Parent-Child chunking**:

```
Level 0: Toàn bộ section summary  
Level 1: Từng mục con  
Level 2: Từng đoạn chi tiết  
```

Khi retrieve, trả về child chunk + kèm context của parent chunk → giúp Agent hiểu ngữ cảnh tổng thể.

---

## 3. Orchestration Pattern — Phân tích & Đề xuất

### 3.1. Nhận xét về pattern FinRobot hiện tại

Bạn đúng khi nhận xét "không thấy có Agent Evaluator". Pattern hiện tại là **Sequential Pipeline thuần tuý** (Data → Analysis → Modeling → Synthesis → Report), có thêm **Parallel Fanout** (Bull ↔ Bear → Judge) ở cuối.

**Điểm yếu chính:**
- Không có cơ chế **fallback/retry** khi một Agent cho kết quả sai.
- Không có bước **human-in-the-loop** để người dùng can thiệp/xác nhận kết quả trung gian.
- Judge Agent chỉ đánh giá Bull vs Bear, không đánh giá **chất lượng dữ liệu đầu vào**.

### 3.2. Đề xuất: Hybrid Pattern (Hierarchical + Selective Reflection)

```
User Query
    ↓
┌─────────────────────────────┐
│   Orchestrator / Supervisor │  ← Phân tích query, lập kế hoạch
│   (Adaptive Strategy Router)│  ← Định tuyến simple/complex
└───────────┬─────────────────┘
            ↓
    ┌───────┴────────┐
    │  Simple Query   │  → Single RAG pass → Response
    │  Complex Query  │
    └───────┬────────┘
            ↓
┌───────────────────────────────────────────┐
│           Execution Layer                  │
│  ┌─────────┐ ┌──────────┐ ┌────────────┐ │
│  │Retriever│ │Calculator│ │Analysis    │ │
│  │Agent    │ │Agent(PoT)│ │Agent       │ │
│  └────┬────┘ └─────┬────┘ └─────┬──────┘ │
│       └─────────────┼───────────┘         │
└───────────────────────────────────────────┘
            ↓
┌───────────────────────────┐
│   Evaluator Agent          │  ← Kiểm tra tính nhất quán, 
│   (Selective Reflection)   │     chỉ trigger khi confidence < threshold
└───────────┬───────────────┘
            ↓ (pass/retry)
┌───────────────────────────────┐
│  Synthesis → Bull/Bear/Judge  │
└───────────┬───────────────────┘
            ↓
┌───────────────────────────┐
│   Report Agent             │
└───────────────────────────┘
```

**Ưu điểm của pattern này:**
- Orchestrator kiểm soát flow → dễ debug (ưu điểm Hierarchical)
- Evaluator chỉ chạy khi cần → tiết kiệm token (so với full Reflexive)
- Adaptive Router ở ngay đầu vào → simple query không cần chạy toàn bộ pipeline

### 3.3. Khi nào nên trigger Reflection loop?

| Tín hiệu | Hành động |
|---|---|
| Agent Retriever trả về < 2 chunks relevant | Retry với query reformulation |
| Agent Calculator cho kết quả âm bất thường hoặc thay đổi > 500% YoY | Gọi Evaluator kiểm tra lại input data |
| Bull Agent và Bear Agent đồng ý 100% | Flag cảnh báo (có thể cả 2 đều sai cùng hướng) |
| Confidence score của Judge < threshold | Yêu cầu thêm dữ liệu hoặc human review |

---

## 4. Framework (AutoGen vs LangGraph) — Lời khuyên

### 4.1. Đề xuất: LangGraph

Với bối cảnh dự án phân tích tài chính, **LangGraph là lựa chọn phù hợp hơn** vì:

- **Truy vết lỗi (Traceability):** Khi một con số tài chính sai, bạn **phải** biết Agent nào đã sai ở bước nào. AutoGen không cho phép điều này dễ dàng.
- **Deterministic flow:** Phân tích tài chính cần output **nhất quán, có thể tái tạo** (reproducible). AutoGen quá linh hoạt → output biến đổi giữa các lần chạy.
- **Kiểm soát chi phí:** LangGraph cho phép kiểm soát chính xác khi nào gọi LLM, bao nhiêu lần retry → dễ quản lý budget token.

> [!WARNING]
> AutoGen v0.4+ (AG2) đã thay đổi rất nhiều so với v0.2. Nếu tham khảo code FinRobot, cần kiểm tra version compatibility.

### 4.2. Nếu dùng LangGraph — Gợi ý thiết kế State

```python
# Ví dụ TypedDict cho Graph State
class FinancialAnalysisState(TypedDict):
    query: str                          # Câu hỏi gốc của user
    query_type: str                     # "simple" | "complex"
    company_ticker: str                 # Mã CK: VNM, FPT, ...
    fiscal_years: list[int]             # Các năm cần phân tích
    retrieved_chunks: list[Document]    # Chunks từ Vector DB
    table_data: dict                    # Data từ MySQL
    calculation_results: dict           # Kết quả tính toán (PoT)
    analysis: str                       # Phân tích cơ bản
    bull_thesis: str                    # Luận điểm tích cực
    bear_thesis: str                    # Luận điểm tiêu cực
    judge_verdict: str                  # Phán quyết
    confidence_score: float             # Độ tin cậy
    retry_count: int                    # Số lần retry
    final_report: str                   # Báo cáo cuối
    provenance: list[dict]              # Truy vết nguồn gốc dữ liệu
```

---

## 5. Agent-Level Algorithms — Các phần còn thiếu

### 5.1. Agent Retriever — Contrastive Financial Retriever ✅ (ý tưởng rất tốt)

Ý tưởng fine-tune embedding model để phân biệt "lợi nhuận gộp" vs "lợi nhuận thuần" rất đúng hướng. Gợi ý thêm:

- **Training data:** Tạo bộ triplets `(anchor, positive, hard_negative)` từ chính BCTC Việt Nam. Ví dụ:
  - anchor: "Lợi nhuận gộp về bán hàng năm 2023"
  - positive: chunk chứa dòng "Lợi nhuận gộp" trong Báo cáo KQKD
  - hard_negative: chunk chứa dòng "Lợi nhuận thuần" trong cùng báo cáo
- **Base model:** Nên dùng `bge-m3` hoặc `multilingual-e5-large` làm base vì hỗ trợ tiếng Việt tốt.
- **Kết hợp Hybrid Search:** Embedding search + BM25 keyword search (đặc biệt hữu ích cho các mã chỉ tiêu tài chính chuẩn: mã số 10, 11, 20, ...).

### 5.2. Agent Calculator (PoT) — Cần bổ sung

- **Sandbox execution:** Code sinh ra bởi LLM **phải** chạy trong sandbox (Docker container / restricted Python). Không bao giờ chạy trực tiếp trên host.
- **Validation layer:** Kết quả tính toán cần được validate (ví dụ: Tổng Tài sản = Tổng Nợ + Vốn CSH). Nếu không cân → flag lỗi.
- **Thư viện tài chính:** Nên có sẵn một bộ hàm Python cho các công thức phổ biến (ROE, ROA, CAGR, P/E, EV/EBITDA...) thay vì để LLM tự sinh code mỗi lần.

### 5.3. Analysis Agent — Chưa mô tả

Gợi ý nội dung cần thiết kế:
- **Input:** Các chỉ số tài chính đã tính + chunks văn bản liên quan
- **Output:** Structured analysis theo framework chuẩn (DuPont analysis, Common-size analysis, Trend analysis)
- **Prompt template:** Nên prompt theo framework phân tích cụ thể, không để Agent tự do phân tích → output nhất quán hơn.

### 5.4. Modeling Agent — Chưa mô tả chi tiết

Từ sơ đồ image.png, các mô hình định giá bao gồm: DCF, DDM, LBO, WACC, Comparable Analysis, Monte Carlo. Cần làm rõ:
- Mỗi model nên là **deterministic code** (pure Python functions), LLM chỉ chọn model phù hợp và điền tham số.
- **Input assumptions:** Ai cung cấp? LLM đề xuất → human xác nhận? Hay hoàn toàn tự động?
- **Sensitivity analysis:** Monte Carlo cần range input → lấy từ đâu?

### 5.5. Synthesis Agent & Report Agent — Chưa mô tả

- **Synthesis Agent:** Cần quy định rõ format output (structured JSON? prose?). Nên output structured data trước, rồi Report Agent mới chuyển thành prose.
- **Report Agent:** Nên hỗ trợ nhiều format output (Markdown, PDF, DOCX). Xem xét dùng template (Jinja2) + LLM fill content.

### 5.6. Bull/Bear/Judge — Cần thêm chi tiết

- Bull/Bear nên nhận **cùng input** nhưng với **system prompt khác nhau** (bias confirmation khác nhau).
- Judge Agent nên có **rubric scoring** cụ thể (data quality, logic consistency, assumption reasonableness) thay vì chỉ đọc 2 luận điểm rồi chọn.

---

## 6. Phần còn thiếu hoàn toàn trong Architecture

### 6.1. 🔴 Database Schema Design

Chưa thấy thiết kế schema cho MySQL (lưu bảng biểu) và Vector DB (lưu chunks).

**Gợi ý MySQL schema:**
```sql
-- Bảng metadata công ty
companies (ticker, name, industry, exchange, ...)

-- Bảng số liệu tài chính (EAV model hoặc wide table)
financial_data (
    id, company_id, fiscal_year, fiscal_quarter,
    report_type,    -- 'balance_sheet' | 'income_statement' | 'cashflow'
    line_item,      -- 'total_assets' | 'net_revenue' | ...
    value,
    unit,           -- 'VND' | 'triệu VND' | '%'
    source_file,    -- Truy vết nguồn
    page_number
)
```

**Gợi ý Vector DB metadata:**
```python
{
    "company_ticker": "VNM",
    "fiscal_year": 2023,
    "report_type": "annual_report",
    "section": "thuyết minh báo cáo tài chính",
    "page_number": 45,
    "chunk_type": "text" | "table_summary",
    "source_file": "VNM_BCTC_2023.pdf"
}
```

### 6.2. 🔴 Error Handling & Fallback Strategy

Chưa có thiết kế cho:
- Khi OCR không đọc được PDF scan → fallback là gì?
- Khi retrieve không tìm được chunk liên quan → trả lời "không có dữ liệu" hay retry?
- Khi API VNStock không khả dụng → cache? fallback data source?
- Khi LLM bị rate limit / timeout → retry policy?

### 6.3. 🔴 User Interface / Interaction Design

Chưa mô tả:
- User tương tác qua gì? Chat interface? Web app? CLI?
- User upload PDF ở đâu?
- Kết quả hiển thị như thế nào? (realtime streaming? batch report?)
- Có cần authentication/multi-user không?

### 6.4. 🟡 Evaluation & Testing Strategy

- Làm sao đo chất lượng hệ thống?
- Cần xây dựng **golden test set** (bộ câu hỏi + đáp án chuẩn từ BCTC thật) để benchmark.
- Metrics đề xuất: Retrieval Accuracy, Calculation Correctness, Report Quality (human eval).

### 6.5. 🟡 Caching Strategy

Rất quan trọng để tiết kiệm token:
- **Embedding cache:** Cùng một BCTC không cần embed lại.
- **LLM response cache:** Cùng query + cùng context → trả kết quả cached.
- **Computed metrics cache:** Các chỉ số tài chính đã tính → lưu vào DB, không tính lại.

### 6.6. 🟡 Security & Data Privacy

- BCTC có thể chứa thông tin nhạy cảm (chưa công bố).
- Nếu dùng OpenAI/Gemini API → dữ liệu gửi lên cloud → cần cân nhắc data residency.
- Xem xét dùng **local LLM** (Qwen2.5, Llama 3.1) cho dữ liệu nhạy cảm.

### 6.7. 🟡 Provenance Tracking (Truy vết nguồn gốc)

Từ sơ đồ image.png, dự án FinRobot nhấn mạnh "provenance-tracked". Cần thiết kế:
- Mỗi con số trong report cuối phải link ngược về: trang nào, file PDF nào, chunk nào.
- Mỗi bước reasoning phải ghi log: Agent nào, input gì, output gì, confidence bao nhiêu.

### 6.8. 🟢 Monitoring & Observability

- **Token usage tracking:** Theo dõi chi phí mỗi query, mỗi Agent.
- **Latency tracking:** Thời gian xử lý từng bước.
- **Logging:** Nên dùng structured logging (JSON) để dễ query.
- Xem xét tích hợp **LangSmith** (nếu dùng LangGraph) hoặc **Weights & Biases** cho MLOps.

---

## 7. Adaptive Strategy Router — Gợi ý triển khai

Ý tưởng trong Architecture.md rất hay. Gợi ý triển khai cụ thể:

### 7.1. Classification model

Có thể dùng một LLM nhỏ (hoặc prompt Gemini Flash) để classify query:

```
Tier 1 - Lookup:      "Doanh thu VNM 2023?"          → Single RAG
Tier 2 - Calculate:   "ROE của FPT 3 năm gần nhất?"  → RAG + PoT
Tier 3 - Analysis:    "So sánh hiệu quả VNM vs VCB"  → Full pipeline
Tier 4 - Valuation:   "Định giá FPT bằng DCF"        → Full pipeline + Modeling
```

### 7.2. Ước tính token cost

| Tier | Ước tính token/query | Ước tính cost (GPT-4o) |
|------|---------------------|----------------------|
| 1 | ~2,000 | ~$0.01 |
| 2 | ~5,000 | ~$0.03 |
| 3 | ~15,000 | ~$0.10 |
| 4 | ~30,000+ | ~$0.20+ |

---

## 8. MLOps / LLMOps — Gợi ý cho phần "chưa biết làm"

### 8.1. Minimum Viable MLOps cho dự án 2 người

Không cần quá phức tạp, focus vào:

1. **Version control prompts:** Lưu tất cả prompt templates vào Git, đánh version.
2. **Experiment tracking:** Dùng **MLflow** (free, self-hosted) hoặc W&B (free tier) để track:
   - Prompt version + kết quả
   - Token usage
   - Accuracy trên test set
3. **CI/CD đơn giản:** GitHub Actions chạy test set tự động khi merge PR.
4. **Config management:** Tất cả tham số (model name, temperature, max_tokens, chunk_size, ...) lưu vào file config (YAML), không hardcode.

### 8.2. Các công cụ phù hợp scale nhỏ

| Chức năng | Tool đề xuất | Lý do |
|-----------|-------------|-------|
| Prompt management | Git + YAML files | Đơn giản, đủ cho 2 người |
| Experiment tracking | MLflow / W&B Free | Track prompt versions + metrics |
| LLM Observability | LangSmith (free tier) | Tích hợp tốt với LangGraph |
| Vector DB | ChromaDB (dev) / Qdrant (prod) | ChromaDB dễ setup, Qdrant scale tốt hơn |
| Deployment | Docker Compose | Gom tất cả services vào 1 file |

---

## 9. Các câu hỏi cần team tự trả lời

> [!IMPORTANT]
> Đây là các quyết định thiết kế mà chỉ team mới có thể trả lời, vì phụ thuộc vào mục tiêu và ràng buộc cụ thể.

1. **Scope công ty:** Hệ thống hỗ trợ tất cả công ty niêm yết (~1,700) hay chỉ tập trung vào top 100 VN30/VN100?
2. **Scope thời gian:** Phân tích bao nhiêu năm lịch sử? 3 năm? 5 năm? 10 năm?
3. **Ngôn ngữ output:** Report bằng tiếng Việt hay tiếng Anh? Hay cả hai?
4. **LLM budget:** Budget hàng tháng cho API calls là bao nhiêu? Điều này ảnh hưởng trực tiếp đến việc chọn Reflexive hay Hierarchical.
5. **Real-time vs Batch:** User cần kết quả ngay (interactive) hay chấp nhận đợi (batch processing)?
6. **Mục tiêu cuối cùng:** Đây là research project (publication) hay product (deploy cho người dùng thật)?
7. **Deterministic Compute:** Có áp dụng nguyên tắc "Numbers are code-calculated" của FinRobot không? (Nên áp dụng)
8. **Human-in-the-loop:** Có bước nào cần user xác nhận không? (Ví dụ: xác nhận assumptions cho DCF model)

---

## 10. Tóm tắt ưu tiên triển khai

| Ưu tiên | Hạng mục | Lý do |
|---------|----------|-------|
| 🔴 P0 | Database Schema Design | Không có schema → không code được |
| 🔴 P0 | Chọn Framework (LangGraph) | Ảnh hưởng toàn bộ codebase |
| 🔴 P0 | PDF Processing Pipeline | Đầu vào sai → tất cả sai |
| 🟡 P1 | Agent Retriever + Embedding | Core retrieval quality |
| 🟡 P1 | Agent Calculator (PoT + Sandbox) | Core computation |
| 🟡 P1 | Orchestration Pattern | Cách các Agent phối hợp |
| 🟢 P2 | Bull/Bear/Judge | Enhancement |
| 🟢 P2 | Adaptive Router | Optimization |
| 🟢 P2 | UI/UX | Có thể dùng CLI trước |
| ⚪ P3 | MLOps pipeline | Sau khi hệ thống chạy ổn |
| ⚪ P3 | Caching & Performance | Optimization sau |
