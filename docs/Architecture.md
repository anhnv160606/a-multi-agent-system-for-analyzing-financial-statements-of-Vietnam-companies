## Dataset

Dữ liệu phân tích báo cáo tài chính cho một công ty bao gồm:

* Báo cáo tài chính (pdf scan) (chứa bảng số liệu và phần văn bản thuyết minh)

* Báo cáo thường niên (pdf) (chứa bảng số liệu, hình ảnh và văn bản)

* Tài liệu họp đại hội cổ đông (pdf scan) (Chứa bảng và văn bản)

* Tin tức về doanh nghiệp (api vnstock)

==> Xử lí dữ liệu bằng các thư viện như Docling, pdfplumber, Llmaparse và một số kĩ thuật nâng cao. Mục tiêu là chia tài liệu thành 2 luồng riêng biệt: Text, Table, Images.

## Chunking (cấy ni t lấy theo gemini còn dự án FinRobot không mần kiểu ri)

Chiến lược Table-aware chunking (Phân mảnh nhận thức bảng). Văn bản tường thuật được chia nhỏ theo ranh giới ngữ nghĩa của đoạn văn. Trong khi đó, các bảng biểu được bảo tồn nguyên vẹn dưới dạng đối tượng độc lập. Đối với các bảng quá lớn vượt quá giới hạn ngữ cảnh của mô hình nhúng, hệ thống sẽ sử dụng một LLM để tạo ra bản tóm tắt mô tả (Ví dụ: "Bảng trình bày chi phí hoạt động theo từng quý của năm 2023"). Bản tóm tắt này sẽ được nhúng vector, nhưng khi Agent Truy xuất tìm thấy nó, hệ thống sẽ tự động gọi ra toàn bộ dữ liệu bảng gốc (định dạng Markdown hoặc HTML) để bàn giao cho Agent SQL hoặc Agent Lập luận

## Orchestration pattern (Cách các Agent giao tiếp với nhau)

Có một số lựa chọn cơ bản đối với Orchestration Pattern:

* Sequential pipeline: Output of previous agent is the input of the current agent. Dễ triển khai nhưng dễ gặp hiện tượng Cascading errors (lỗi một agent là lỗi luôn mấy con phía sau)

* Parallel fanout: Phân tách một nhiệm vụ thành nhiều nhánh độc lập, thực thi song song và sau đó hợp nhất kết quả ở cuối chu trình.

* Hierarchical Supervisor-Worker (Phân cấp): Một Agent Quản lý phân tích yêu cầu, cấp phát nhiệm vụ, và đánh giá chất lượng của các agent Công nhân bên dưới. Ngon nhất so với chi phí token

* Reflexive Self-Correcting Loop (Vòng lặp Phản xạ): Các tác tử liên tục kiểm tra kết quả của nhau, tranh biện và lặp lại quá trình trích xuất cho đến khi đạt ngưỡng tin cậy. Độ chính xác cao nhưng cực tốn token

Có thể cân nhắc kết hợp các patterns khác nhau. Pattern của dự án FinRobot là:

User Research Request

↓

Lead Agent / Orchestrator

↓

Data Agent → Analysis Agent → Modeling Agent → Synthesis Agent → Report Agent

↓

Bull Agent ↔ Bear Agent → Judge Agent

↓

Traceable Investment Research Output

Tuy nhiên pattern này không thấy có Agent Evaluator

==> Cân nhắc chỉnh sửa, thử nghiệm các pattern khác nhau, SOTA hiện tại là Reflexive nhưng mà tốn token, cái ngon nhất vẫn là Hierachical

## Framework

2 framework phổ biến là: AutoGen và LangGraph. Điểm khác nhau của 2 framework này là:

* AutoGen thì đại khái là mặc cho agent tự giao tiếp, thảo luận với nhau, output sẽ rất linh hoạt nên human không thể kiểm soát được output đầu ra. Và khi xảy ra lỗi cũng không biết rà soát lỗi ở đâu? do Agent nào?

* LangGraph thì kiểm soát hơn. Khi lỗi có thể truy vết để tìm lỗi được nhưng vì hoạt động theo lý thuyết đồ thị nên phải tự thiết kế đồ thị, khó làm hơn.

## Thuật toán riêng cho mỗi Agent

### Agent tính toán: 
Dùng Program of Thought

### Agent retrieve chunk: 
Vì trong báo cáo tài chính có một số cụm gần giống nhau như: lợi nhuận gộp, lợi nhuận thuần,... nhưng bản chất khác nhau. Nếu dùng Cosine Similarity bình thường thì rất dễ retrieve nhầm chunk. Kĩ thuật đề xuất là finetune mô hình embedding để tách biệt các từ gần giống nhau ra xa nhau. Gọi là kĩ thuật Contrastive Financial Retriever. Ngoài ra, kết hợp thêm search theo metadata.

### Analysis Agent (Agent phân tích cơ bản)

### Modeling Agent (Agent định giá cổ phiếu, prompt trước các mô hình định giá)

### Synthesis Agent (Agent tổng hợp)

### Report Agent (Agent viết report)

**(copy các Agent của dự án FinRobot)**

## Tối ưu hóa Tài nguyên:

Định tuyến Chiến lược Thích ứng (Adaptive Strategy Router)Việc chạy toàn bộ chu trình truy xuất đa bước, sinh mã PoT và tranh biện cho mọi câu hỏi sẽ gây lãng phí tài nguyên máy tính khổng lồ. Để giải quyết bài toán kinh tế, hệ thống FinAgent-RAG đề xuất Adaptive Strategy Router (Bộ định tuyến chiến lược thích ứng).Trước khi thực thi, một mô hình định tuyến nhỏ sẽ đánh giá độ phức tạp của truy vấn. Đối với các yêu cầu tra cứu đơn giản (ví dụ: "Tổng tài sản của công ty A năm 2023 là bao nhiêu?"), hệ thống sẽ định tuyến thẳng qua một vòng RAG duy nhất mà không cần sinh mã PoT hay kích hoạt toàn bộ mạng lưới tác tử. Ngược lại, đối với các câu hỏi phân tích đa bước (ví dụ: "Tính toán tốc độ tăng trưởng kép hàng năm của chi phí hoạt động từ 2018 đến 2023"), bộ định tuyến sẽ kích hoạt toàn bộ quy trình lặp lại.

## MLOps, LLMOps

(Phần ni có trong dự án FinRobot nớ, t cụng chưa biết mần mấy cấy ni)

## Data Flow

User Input (PDF + Ticker) → [Phân tách Dữ liệu]

├─> (Luồng Text/News) → Chunking → Vector DB

└─> (Luồng Bảng biểu) → Table Extraction → MySQL DB

↓

[Hệ thống Multi-Agent chủ động dùng Tools truy vấn cả 2 DB]

↕

(Vòng lặp tự sửa lỗi/Reflection)

Final Report
