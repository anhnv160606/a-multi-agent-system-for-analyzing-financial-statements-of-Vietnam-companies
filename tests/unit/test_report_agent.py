import os
import json
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

# Import ReportAgent từ source code của bạn (điều chỉnh đường dẫn import nếu cần)
from src.agents.report import ReportAgent 

def test_report_agent():
    # 1. Nạp biến môi trường (chứa GOOGLE_API_KEY)
    load_dotenv()

    # 2. Khởi tạo LLM theo yêu cầu
    # Lưu ý: Đảm bảo model "gemini-3.1-flash-lite" đã khả dụng trên API của Google. 
    # Nếu báo lỗi không tìm thấy model, hãy thử đổi tạm thành "gemini-1.5-flash".
    llm = ChatGoogleGenerativeAI(
        model="gemini-3.1-flash-lite", 
        temperature=0.4,
        max_tokens=8192,
        api_key=os.environ.get("GOOGLE_API_KEY")
    )

    # 3. Giả lập Prompt Template (Vì test độc lập nên ta truyền thẳng dict thay vì đọc file YAML)
    mock_prompt_template = {
        "system_prompt": "Bạn là chuyên gia viết báo cáo tài chính cấp cao.",
        "user_template": """
Dựa vào dữ liệu sau: {synthesis_json}
Hãy viết báo cáo phân tích mã {ticker} năm {years}.
Yêu cầu trả về CẤU TRÚC MARKDOWN y hệt dưới đây, tuyệt đối GIỮ NGUYÊN các placeholder {{...}}:

# Báo cáo Phân tích Tài chính — {ticker} ({years})
*Ngày tạo: {generated_at}*

---

## 1. Tóm tắt Điều hành
(Viết 1 đoạn văn tóm tắt executive_summary tại đây, không dùng placeholder CONTENT_1)

---

## 2. Thông tin Doanh nghiệp
(Viết thông tin tổng quan về doanh nghiệp, vị thế ngành)

---

## 3. Phân tích Tài chính
### 3.1. Bảng Chỉ số Tài chính Chính
{{METRICS_TABLE}}

### 3.2. Phân tích DuPont
(Tóm tắt phân tích DuPont)

### 3.3. Phân tích Xu hướng
(Tóm tắt xu hướng)

### 3.4. Cơ cấu Tài chính (Common-size)
(Tóm tắt cơ cấu)

### 3.5. So sánh cùng ngành
(Tóm tắt so sánh)

---

## 4. Điểm mạnh và Rủi ro
### Điểm mạnh
{{STRENGTHS_LIST}}

### Rủi ro
{{RISKS_LIST}}

---

## 5. Nhận định Tổng quát
(Viết nhận định tổng quát chốt lại vấn đề)

---

## 6. Lưu ý và Giới hạn Báo cáo
{{DISCLAIMER}}
"""
    }

    # 4. Giả lập dữ liệu SynthesisResult (Output từ SynthesisAgent)
    mock_synthesis_results = {
        "ticker": "FPT",
        "company_name": "Công ty Cổ phần FPT",
        "fiscal_years": [2021, 2022, 2023],
        "generated_at": "2026-08-29T10:00:00Z",
        "executive_summary": "FPT duy trì đà tăng trưởng mạnh mẽ trong 3 năm liên tiếp nhờ mảng Xuất khẩu phần mềm và Viễn thông. Cấu trúc vốn an toàn, hiệu quả sinh lời trên vốn chủ sở hữu (ROE) luôn duy trì trên 25%.",
        "key_metrics": {
            "2021": {"roe": 25.4, "roa": 12.1, "net_margin": 15.2, "gross_margin": 39.5, "revenue": 34678, "net_income": 5342, "total_assets": 53698, "equity": 21456},
            "2022": {"roe": 27.6, "roa": 12.8, "net_margin": 15.8, "gross_margin": 39.9, "revenue": 44010, "net_income": 6489, "total_assets": 60524, "equity": 25340},
            "2023": {"roe": 28.1, "roa": 13.5, "net_margin": 16.1, "gross_margin": 40.2, "revenue": 52618, "net_income": 7788, "total_assets": 68450, "equity": 29850}
        },
        "analysis_highlights": {
            "dupont_summary": "ROE tăng trưởng đều đặn chủ yếu do vòng quay tài sản cải thiện và biên lợi nhuận ròng nhích nhẹ. Tỷ lệ đòn bẩy tài chính duy trì ở mức an toàn.",
            "trend_summary": "Doanh thu tăng trưởng kép (CAGR) đạt xấp xỉ 23% trong giai đoạn 2021-2023.",
            "common_size_summary": "Tài sản ngắn hạn chiếm tỷ trọng lớn (~60%), chủ yếu là tiền gửi và khoản phải thu ngắn hạn.",
            "peer_summary": "Biên lợi nhuận của FPT vượt trội so với trung bình nhóm ngành công nghệ tại Việt Nam."
        },
        "strengths": [
            "Biên lợi nhuận gộp duy trì ổn định ở mức 40% trong suốt 3 năm.",
            "Tăng trưởng doanh thu mảng Công nghệ đạt 25% YoY bất chấp kinh tế khó khăn.",
            "Lượng tiền mặt dồi dào, đáp ứng tốt nghĩa vụ nợ ngắn hạn."
        ],
        "risks": [
            "Biến động tỷ giá có thể ảnh hưởng nhẹ đến biên lợi nhuận khi xuất khẩu phần mềm chiếm tỷ trọng lớn.",
            "Chi phí nhân sự IT tăng cao gây áp lực lên chi phí quản lý doanh nghiệp."
        ],
        "data_quality": {
            "data_gaps": ["Thiếu chi tiết thuyết minh chi phí R&D năm 2023."],
            "confidence": 0.95,
            "completeness_score": 0.98
        },
        "overall_assessment": "FPT là doanh nghiệp có nền tảng tài chính cực kỳ vững chắc, khả năng tạo tiền tốt và ít rủi ro về thanh khoản. Phù hợp cho chiến lược nắm giữ dài hạn."
    }

    # 5. Khởi tạo State giả lập
    state = {
        "run_id": "test_run_001",
        "company_ticker": "FPT",
        "query": "Đánh giá sức khỏe tài chính và rủi ro đầu tư của FPT trong 3 năm qua.",
        "fiscal_years": [2021, 2022, 2023],
        "synthesis_results": mock_synthesis_results,
    }

    # 6. Chạy Agent
    print("🚀 Đang khởi tạo ReportAgent...")
    agent = ReportAgent(llm=llm, prompt_template=mock_prompt_template)
    
    print("⏳ Đang gọi LLM (Gemini) để sinh báo cáo...")
    result_state = agent.invoke(state)

    # 7. In kết quả
    print("\n" + "="*60)
    print("🎯 KẾT QUẢ BÁO CÁO (FINAL REPORT):")
    print("="*60 + "\n")
    
    final_report = result_state.get("final_report")
    if final_report:
        print(final_report)
    else:
        print("❌ Lỗi: Không sinh được báo cáo.")
        print("Chi tiết lỗi:", result_state.get("errors"))

if __name__ == "__main__":
    test_report_agent()