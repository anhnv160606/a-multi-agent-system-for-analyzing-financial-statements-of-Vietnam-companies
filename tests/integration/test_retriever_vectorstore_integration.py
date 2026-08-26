from __future__ import annotations

from pathlib import Path
from typing import Any

from src.agents.retriever.agent import RetrieverAgent
from src.database.vector_store import VectorStore


class FakeMySQLLoader:
    def get_financial_data(
        self,
        ticker: str,
        fiscal_year: int | None = None,
        report_type: str | None = None,
        line_item_like: str | None = None,
    ):
        if ticker != "FPT":
            return []
        return [
            {
                "ticker": ticker,
                "fiscal_year": fiscal_year or 2024,
                "report_type": report_type or "income_statement",
                "line_item": "Doanh thu thuan",
                "value": 123.45,
                "line_item_like": line_item_like,
            }
        ]


def _build_temp_vector_config(tmp_path: Path) -> Path:
    cfg_path = tmp_path / "database.yaml"
    cfg_path.write_text(
        "vector_db:\n"
        "  mode: persistent\n"
        "  persist_directory: './vector_tmp'\n"
        "  collection:\n"
        "    default_name: 'integration_retriever_test'\n"
        "    distance_metric: 'cosine'\n"
        "  indexing:\n"
        "    batch_size: 16\n",
        encoding="utf-8",
    )
    return cfg_path


def test_retriever_agent_with_real_vectorstore_fallback(tmp_path: Path):
    cfg_path = _build_temp_vector_config(tmp_path)
    vector_store = VectorStore(collection_name="integration_retriever_test", config_path=cfg_path)
    vector_store.use_fallback = True
    vector_store._fallback_docs = {}

    vector_store.add_documents(
        documents=[
            "Tong hop doanh thu va loi nhuan 2024 cua FPT.",
            "| Chi tieu | Gia tri |\n|---|---|\n| Doanh thu thuan | 123.45 |",
            "Doanh thu tang trong nam 2024 o khoi cong nghe.",
        ],
        metadatas=[
            {
                "ticker": "FPT",
                "year": 2024,
                "chunk_type": "table_summary",
                "report_type": "income_statement",
                "source_file": "FPT_IS.pdf",
                "page": 10,
            },
            {
                "ticker": "FPT",
                "year": 2024,
                "chunk_type": "table",
                "report_type": "income_statement",
                "parent_id": "sum_1",
                "source_file": "FPT_IS.pdf",
                "page": 10,
            },
            {
                "ticker": "FPT",
                "year": 2024,
                "chunk_type": "text",
                "report_type": "income_statement",
                "source_file": "FPT_IS.pdf",
                "page": 8,
            },
        ],
        ids=["sum_1", "table_full_1", "txt_1"],
    )

    agent = RetrieverAgent(
        config={
            "top_k": 3,
            "min_results": 1,
            "reranker_strategy": "none",
            "hybrid_alpha": 0.7,
        },
        llm=None,
        prompt_template={"system_prompt": "s", "user_template": "u"},
        vector_store=vector_store,
        mysql_loader=FakeMySQLLoader(),
    )

    state: dict[str, Any] = {
        "query": "Cho toi bang doanh thu FPT 2024",
        "company_ticker": "FPT",
        "fiscal_years": [2024],
        "provenance": [],
    }

    updated = agent.invoke(state)

    assert len(updated.get("retrieved_chunks", [])) >= 1
    assert any(item["metadata"].get("chunk_type") == "table_summary" for item in updated["retrieved_chunks"])
    assert len(updated.get("table_data", [])) >= 1
    assert updated.get("retriever_filters", {}).get("ticker") == "FPT"
