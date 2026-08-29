import os
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate

# 1. Khởi tạo LLM với cấu hình từ file yaml
llm = ChatGroq(
    model="qwen/qwen3.8-27b",
    temperature=0.2,
    max_tokens=4096,
    api_key=os.environ.get("GROQ_API_KEY")
)

# 2. Tạo Prompt (Có thể tích hợp file synthesis.yaml ở bước trước vào đây)
prompt = ChatPromptTemplate.from_messages([
    ("system", "Bạn là trợ lý ảo hỗ trợ tính toán tài chính."),
    ("human", "{query}")
])

# 3. Tạo Chain và thực thi
chain = prompt | llm
result = chain.invoke({"query": "Giải thích chỉ số ROE là gì?"})

print(result.content)