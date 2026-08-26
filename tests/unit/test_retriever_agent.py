from __future__ import annotations

from typing import Any

from src.agents.retriever.agent import RetrieverAgent
from src.agents.retriever.hybrid_search import HybridSearch
from src.agents.retriever.reranker import RetrieverReranker
from src.database.models import VectorSearchResult


class FakeVectorStore:
    def __init__(self, results: list[VectorSearchResult]):
        self._results = results
        self.use_fallback = True
        self._fallback_docs = {
            "table_full_1": {
                "document": "| chi tieu | gia tri |\n|---|---|\n| Doanh thu | 100 |",
                "metadata": {
                    "parent_id": "sum_1",
                    "chunk_type": "table",
                    "ticker": "FPT",
                },
            }
        }

    def query(self, query_text: str, n_results: int = 5, where: dict[str, Any] | None = None):
        if not query_text:
            return []
        filtered = self._results
        if where:
            filtered = [
                item for item in filtered if all(item.metadata.get(key) == value for key, value in where.items())
            ]
        return filtered[:n_results]


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
                "value": 100.0,
                "line_item_like": line_item_like,
            }
        ]


class FakeLLM:
    def invoke(self, prompt: str):
        if "Reformulate" in prompt:
            return {"text": "doanh thu FPT 2024 income statement"}
        return {"scores": [{"id": "sum_1", "score": 0.95}, {"id": "txt_1", "score": 0.8}]}


class BatchCountingLLM:
    def __init__(self):
        self.calls = 0

    def invoke(self, prompt: str):
        self.calls += 1
        return {
            "scores": [
                {"id": "sum_1", "score": 0.91},
                {"id": "txt_1", "score": 0.87},
            ]
        }


def _build_hits() -> list[VectorSearchResult]:
    return [
        VectorSearchResult(
            id="sum_1",
            document="Tom tat bang doanh thu 2024 cua FPT.",
            metadata={
                "ticker": "FPT",
                "year": 2024,
                "chunk_type": "table_summary",
                "report_type": "income_statement",
                "source_file": "FPT_IS.pdf",
                "page": 12,
            },
            similarity=0.88,
            distance=0.12,
        ),
        VectorSearchResult(
            id="txt_1",
            document="Doanh thu tang truong manh trong nam 2024.",
            metadata={
                "ticker": "FPT",
                "year": 2024,
                "chunk_type": "text",
                "report_type": "income_statement",
                "source_file": "FPT_IS.pdf",
                "page": 8,
            },
            similarity=0.84,
            distance=0.16,
        ),
    ]


def test_hybrid_search_returns_ranked_hits():
    vector_store = FakeVectorStore(_build_hits())
    engine = HybridSearch(vector_store=vector_store, alpha=0.7, rrf_k=20)

    hits = engine.search(
        query="doanh thu FPT 2024",
        top_k=2,
        filters={"ticker": "FPT", "year": 2024},
    )

    assert len(hits) == 2
    assert hits[0].hybrid_score >= hits[1].hybrid_score
    assert hits[0].id in {"sum_1", "txt_1"}


def test_reranker_llm_mode_scores_candidates():
    vector_store = FakeVectorStore(_build_hits())
    engine = HybridSearch(vector_store=vector_store, alpha=0.6, rrf_k=20)
    candidates = engine.search("doanh thu FPT 2024", top_k=2, filters={"ticker": "FPT", "year": 2024})

    reranker = RetrieverReranker(llm=FakeLLM(), strategy="llm", top_n=2)
    reranked = reranker.rerank("doanh thu FPT 2024", candidates)

    assert len(reranked) == 2
    assert all(0.0 <= hit.rerank_score <= 1.0 for hit in reranked)


def test_reranker_llm_batch_uses_fewer_calls():
    vector_store = FakeVectorStore(_build_hits())
    engine = HybridSearch(vector_store=vector_store, alpha=0.6, rrf_k=20)
    candidates = engine.search("doanh thu FPT 2024", top_k=2, filters={"ticker": "FPT", "year": 2024})

    llm = BatchCountingLLM()
    reranker = RetrieverReranker(llm=llm, strategy="llm", top_n=2, batch_size=2)
    reranked = reranker.rerank("doanh thu FPT 2024", candidates)

    assert len(reranked) == 2
    assert llm.calls == 1


def test_retriever_agent_invoke_updates_state_with_chunks_and_tables():
    vector_store = FakeVectorStore(_build_hits())
    mysql_loader = FakeMySQLLoader()

    agent = RetrieverAgent(
        config={
            "top_k": 4,
            "min_results": 1,
            "max_retrieve_retries": 1,
            "reranker_strategy": "none",
            "confidence_warning_threshold": 0.3,
        },
        llm=FakeLLM(),
        prompt_template={"system_prompt": "s", "user_template": "u"},
        vector_store=vector_store,
        mysql_loader=mysql_loader,
    )

    state: dict[str, Any] = {
        "query": "Cho toi bang doanh thu FPT 2024",
        "company_ticker": "FPT",
        "fiscal_years": [2024],
        "provenance": [],
    }

    updated = agent.invoke(state)

    assert "retrieved_chunks" in updated
    assert len(updated["retrieved_chunks"]) >= 1
    assert "table_data" in updated
    assert len(updated["table_data"]) >= 1
    assert "retriever_filters" in updated
    assert updated["retriever_filters"]["ticker"] == "FPT"
    assert isinstance(updated.get("confidence_score"), float)
    assert len(updated.get("provenance", [])) >= 1
