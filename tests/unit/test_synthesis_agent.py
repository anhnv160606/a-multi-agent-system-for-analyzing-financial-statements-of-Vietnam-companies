import json
import os
from src.agents.synthesis import SynthesisAgent
import yaml
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv

load_dotenv()  

with open("prompts/synthesis.yaml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

system_prompt = config.get("system_prompt")
user_prompt = config.get("user_template")

PROMPT_TEMPLATE = {"system_prompt": system_prompt, "user_prompt": user_prompt}

with open("configs/models.yaml", "r", encoding="utf-8") as f:
    model_config = yaml.safe_load(f)

default_agent_config = model_config['agents']['default']

# Gọi từng biến cụ thể
provider = default_agent_config['provider']
model_name = default_agent_config['model']
temperature = default_agent_config['temperature']
max_tokens = default_agent_config['max_tokens']

# Input giả lập — như thể do RetrieverAgent, CalculatorAgent, AnalysisAgent trả về
FAKE_STATE = {
    "query": "Phân tích ROE của FPT giai đoạn 2022-2023",
    "company_ticker": "FPT",
    "fiscal_years": [2022, 2023],
    "run_id": "manual-run-001",
    "retrieved_chunks": [
        {
            "content": "FPT ghi nhận doanh thu tăng trưởng 20% trong năm 2023, chủ yếu nhờ mảng CNTT nước ngoài.",
            "hybrid_score": 0.9,
            "metadata": {"company_name": "CTCP FPT"},
        }
    ],
    "table_data": [{"revenue": 50000}],
    "calculator_results": {
        "roe": 0.25,
        "roa": 0.12,
        "net_margin": 0.15,
        "revenue": 50000.0,
        "net_income": 7500.0,
    },
    "analysis_results": {
        "dupont": {
            "dupont_3step": {"2022": {"roe": 0.22}, "2023": {"roe": 0.25}},
            "interpretation": "ROE cải thiện nhờ biên lợi nhuận ròng tăng.",
        },
        "trend": {
            "trend_direction": {"revenue": "up"},
            "cagr": {"revenue": 0.20},
            "interpretation": "Doanh thu tăng trưởng ổn định qua các năm.",
        },
        "common_size": {"interpretation": "Chi phí vốn hàng bán ổn định qua các năm."},
        "peer_comparison": {
            "has_peer_data": True,
            "company_position": {"roe_rank": 2},
            "interpretation": "FPT đứng thứ 2 ngành CNTT về ROE.",
        },
        "data_gaps": [],
        "confidence": 0.8,
    },
}


def main() -> None:
    api_key = os.environ.get("GROQ_API_KEY")    
    llm = ChatGroq(
        model=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
        api_key=api_key
    )   

    agent = SynthesisAgent(config={}, llm=llm, prompt_template=PROMPT_TEMPLATE)
 
    # Bắt raw response thật từ Gemini để chẩn đoán, không đổi logic gốc của agent
    original_call = agent._call_synthesis_llm
    captured = {"raw": None}

    def spy(*args, **kwargs):
        raw = original_call(*args, **kwargs)
        captured["raw"] = raw
        return raw

    agent._call_synthesis_llm = spy

    result = agent.invoke(dict(FAKE_STATE))

    raw = captured["raw"]
    print("=== 1. API LLM có hoạt động không? ===")
    if raw is None:
        print("Không được gọi (thiếu analysis_results/calculator_results -> agent bỏ qua sớm)")
    elif raw == "":
        print("LLM được gọi nhưng LỖI hoặc trả rỗng (xem log cảnh báo 'llm_error' ở trên)")
    else:
        print("OK — Gemini trả về response")
        print("--- raw response (preview 500 ký tự) ---")
        print(raw[:500])

    is_valid_json = False
    if raw:
        cleaned = raw.replace("```json", "").replace("```", "").strip()
        try:
            json.loads(cleaned)
            is_valid_json = True
        except (json.JSONDecodeError, ValueError):
            is_valid_json = False

    print("\n=== 2. Có ra output không? ===")
    print("Có" if "synthesis_results" in result else "KHÔNG")

    print("\n=== 3. Có dùng fallback không? ===")
    if raw is None:
        print("N/A — agent dừng sớm, chưa tới bước gọi LLM")
    elif not is_valid_json:
        print("CÓ — raw rỗng hoặc parse JSON thất bại -> dùng placeholder fallback trong code")
    else:
        print("KHÔNG — parse JSON từ Gemini thành công, dùng thẳng kết quả LLM")

    print("\n=== Output cuối cùng (synthesis_results) ===")
    print(json.dumps(result.get("synthesis_results"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()