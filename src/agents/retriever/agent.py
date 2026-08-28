"""Retriever agent: fetch relevant chunks and expand table context."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, MutableMapping
from typing import Any

from src.agents.base_agent import BaseAgent, track_tokens
from src.agents.retriever.hybrid_search import HybridSearch, HybridSearchHit
from src.agents.retriever.reranker import RetrieverReranker
from src.database.mysql_loader import MySQLLoader
from src.database.vector_store import VectorStore
from src.ingestion.vnstock_client import VNStockClient


class RetrieverAgent(BaseAgent):
	"""Retrieves relevant chunks from vector store, table data from SQL layer, and live market data from VNStock."""

	def __init__(
		self,
		config: Mapping[str, Any] | None,
		llm: Any,
		prompt_template: str | Mapping[str, Any] = "retriever",
		vector_store: VectorStore | None = None,
		mysql_loader: MySQLLoader | None = None,
		hybrid_search: HybridSearch | None = None,
		reranker: RetrieverReranker | None = None,
		vnstock_client: VNStockClient | None = None,
	) -> None:
		super().__init__(config=config, llm=llm, prompt_template=prompt_template)

		self._vector_store = vector_store
		self._mysql_loader = mysql_loader
		self.vnstock_client = vnstock_client or VNStockClient()
		self.hybrid_search = hybrid_search or HybridSearch(
			vector_store=self._get_vector_store(),
			alpha=float(self.config.get("hybrid_alpha", 0.7)),
			rrf_k=int(self.config.get("rrf_k", 60)),
			keyword_pool_size=int(self.config.get("keyword_pool_size", 30)),
		)
		self.reranker = reranker or RetrieverReranker(
			llm=llm,
			strategy=str(self.config.get("reranker_strategy", "none")),
			top_n=int(self.config.get("reranker_top_n", 10)),
			batch_size=int(self.config.get("reranker_batch_size", 5)),
		)

	def invoke(self, state: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
		query = str(state.get("query") or "").strip()
		if not query:
			self._append_error(state, "RetrieverAgent: state.query is required.")
			return state

		filters = self._extract_filters(query=query, state=state)
		top_k = int(self.config.get("top_k", 8))
		min_results = int(self.config.get("min_results", 3))
		max_retries = int(self.config.get("max_retrieve_retries", 1))

		search_query = query
		retries = 0
		hybrid_hits: list[HybridSearchHit] = []

		while retries <= max_retries:
			hybrid_hits = self.hybrid_search.search(
				query=search_query,
				top_k=top_k,
				alpha=float(self.config.get("hybrid_alpha", 0.7)),
				filters=filters or None,
			)

			if len(hybrid_hits) >= min_results or retries == max_retries:
				break

			reformulated = self.reformulate_query(query=search_query, filters=filters)
			if not reformulated or reformulated == search_query:
				break
			search_query = reformulated
			retries += 1

		reranked_hits = self.reranker.rerank(query=search_query, candidates=hybrid_hits)
		table_data = self._expand_table_data(reranked_hits, query=search_query, filters=filters)

		retrieved_chunks = [
			{
				"chunk_id": hit.id,
				"content": hit.content,
				"metadata": hit.metadata,
				"vector_score": hit.vector_score,
				"keyword_score": hit.keyword_score,
				"hybrid_score": hit.hybrid_score,
				"rerank_score": hit.rerank_score,
				"rerank_reason": hit.rerank_reason,
			}
			for hit in reranked_hits
		]

		confidence = self._estimate_confidence(reranked_hits)
		provenance_items = [
			{
				"agent": self.__class__.__name__,
				"chunk_id": hit.id,
				"score": hit.rerank_score,
				"source_file": hit.metadata.get("source_file"),
				"page": hit.metadata.get("page"),
				"ticker": hit.metadata.get("ticker"),
				"report_type": hit.metadata.get("report_type"),
			}
			for hit in reranked_hits
		]

		# Fetch real-time market data & company ratios from VNStock
		ticker = str(state.get("company_ticker") or filters.get("ticker") or "FPT").strip().upper()
		if ticker:
			try:
				stock_history = self.vnstock_client.get_stock_price(ticker, limit_days=5)
				ratios = self.vnstock_client.get_financial_ratios(ticker)
				news = self.vnstock_client.get_company_news(ticker, limit=2)
				overview = self.vnstock_client.get_company_info(ticker)

				state["market_data"] = stock_history.model_dump()
				state["market_ratios"] = ratios.model_dump()

				market_text_parts = [f"[DỮ LIỆU THỊ TRƯỜNG THỜI GIAN THỰC TỪ VNSTOCK - MÃ {ticker}]"]
				if stock_history.records:
					latest = stock_history.records[-1]
					market_text_parts.append(
						f"- Giá giao dịch gần nhất (ngày {latest.date}): {latest.close:,.0f} VND "
						f"(Mở cửa: {latest.open:,.0f}, Cao nhất: {latest.high:,.0f}, Thấp nhất: {latest.low:,.0f}).\n"
						f"- Khối lượng giao dịch: {latest.volume:,.0f} cổ phiếu."
					)
				if ratios.pe or ratios.pb:
					market_text_parts.append(
						f"- Chỉ số định giá thị trường: P/E = {ratios.pe}x, P/B = {ratios.pb}x, EPS = {ratios.eps:,.0f} VND.\n"
						f"- Doanh thu thị trường: {ratios.revenue:,.0f} VND, Lợi nhuận sau thuế: {ratios.net_profit:,.0f} VND."
					)
				if news:
					market_text_parts.append("- Tin tức mới nhất:")
					for item in news:
						market_text_parts.append(f"  + [{item.publish_date}] {item.title}")

				market_content = "\n".join(market_text_parts)
				retrieved_chunks.insert(0, {
					"chunk_id": f"vnstock_market_{ticker}",
					"content": market_content,
					"metadata": {"ticker": ticker, "source": "vnstock_api", "type": "market_realtime"},
					"vector_score": 1.0,
					"keyword_score": 1.0,
					"hybrid_score": 1.0,
					"rerank_score": 1.0,
					"rerank_reason": "Live market data from VNStock API",
				})
				provenance_items.append({
					"agent": "VNStockClient",
					"ticker": ticker,
					"source": "VNDirect / VNStock Market API",
					"records_count": len(stock_history.records),
				})
				confidence = max(confidence, 0.85)
			except Exception as e:
				pass

		state["retrieved_chunks"] = retrieved_chunks
		state["table_data"] = table_data
		state["retriever_filters"] = filters
		state["confidence_score"] = confidence
		state.setdefault("provenance", [])
		if isinstance(state["provenance"], list):
			state["provenance"].extend(provenance_items)

		self._log_step(
			input={"query": query, "filters": filters, "retry_count": retries},
			output={
				"run_id": state.get("run_id"),
				"trace_id": state.get("trace_id"),
				"ticker": state.get("company_ticker") or filters.get("ticker"),
				"retrieved_count": len(retrieved_chunks),
				"table_records": len(table_data),
			},
			confidence=confidence,
		)
		return state

	def reformulate_query(self, query: str, filters: Mapping[str, Any]) -> str:
		"""Reformulates user query when retrieval candidates are too sparse."""
		if self.llm is None:
			suffix = []
			if filters.get("ticker"):
				suffix.append(f"ticker {filters['ticker']}")
			if filters.get("year"):
				suffix.append(f"year {filters['year']}")
			return f"{query} {' '.join(suffix)}".strip()

		prompt = (
			"Reformulate this financial retrieval query to improve search recall. "
			"Keep it concise and preserve intent. Return only the reformulated query.\n\n"
			f"Original query: {query}\n"
			f"Metadata filters: {json.dumps(dict(filters), ensure_ascii=False)}"
		)
		response = self._call_reformulation_llm(prompt)
		reformulated = self._extract_text_response(response).strip()
		return reformulated or query

	@track_tokens
	def _call_reformulation_llm(self, prompt: str) -> Any:
		return self._invoke_llm(prompt)

	def _invoke_llm(self, prompt: str) -> Any:
		if hasattr(self.llm, "invoke"):
			return self.llm.invoke(prompt)
		if hasattr(self.llm, "generate_content"):
			return self.llm.generate_content(prompt)
		if callable(self.llm):
			return self.llm(prompt)
		raise ValueError("Provided llm object does not expose a supported call interface.")

	def _extract_text_response(self, response: Any) -> str:
		if response is None:
			return ""
		if isinstance(response, str):
			return response
		if isinstance(response, Mapping):
			if isinstance(response.get("text"), str):
				return response["text"]
			if isinstance(response.get("content"), str):
				return response["content"]
		return str(getattr(response, "text", None) or getattr(response, "content", None) or response)

	def _extract_filters(self, query: str, state: Mapping[str, Any]) -> dict[str, Any]:
		"""Extracts retrieval metadata filters from query/state."""
		filters: dict[str, Any] = {}

		ticker = state.get("company_ticker")
		if isinstance(ticker, str) and ticker.strip():
			filters["ticker"] = ticker.strip().upper()
		else:
			ticker_match = re.search(r"\b[A-Z]{3,5}\b", query)
			if ticker_match:
				filters["ticker"] = ticker_match.group(0).upper()

		year_match = re.search(r"\b(20\d{2})\b", query)
		if year_match:
			filters["year"] = int(year_match.group(1))
		elif isinstance(state.get("fiscal_years"), list) and state["fiscal_years"]:
			first_year = state["fiscal_years"][0]
			if isinstance(first_year, int):
				filters["year"] = first_year

		lowered = query.lower()
		if any(word in lowered for word in ("bảng", "table", "chỉ tiêu", "số liệu")):
			filters["chunk_type"] = "table_summary"

		if any(word in lowered for word in ("kết quả kinh doanh", "income statement", "doanh thu")):
			filters["report_type"] = "income_statement"
		elif any(word in lowered for word in ("cân đối kế toán", "balance sheet", "tài sản", "nguồn vốn")):
			filters["report_type"] = "balance_sheet"
		elif any(word in lowered for word in ("lưu chuyển tiền tệ", "cash flow")):
			filters["report_type"] = "cash_flow"

		return filters

	def _expand_table_data(
		self,
		hits: list[Any],
		query: str,
		filters: Mapping[str, Any],
	) -> list[dict[str, Any]]:
		"""Expands table summaries into original table chunks and SQL rows when possible."""
		expanded: list[dict[str, Any]] = []
		seen_ids: set[str] = set()

		for hit in hits:
			metadata = hit.metadata or {}
			if metadata.get("chunk_type") != "table_summary":
				continue

			summary_id = hit.id
			table_chunks = self._fetch_original_table_chunks(summary_id=summary_id)
			for table_chunk in table_chunks:
				table_id = table_chunk.get("chunk_id") or table_chunk.get("id")
				if table_id and table_id in seen_ids:
					continue
				if table_id:
					seen_ids.add(table_id)
				expanded.append(table_chunk)

			sql_rows = self._fetch_sql_table_rows(query=query, filters=filters)
			expanded.extend(sql_rows)

		return expanded

	def _fetch_original_table_chunks(self, summary_id: str) -> list[dict[str, Any]]:
		vector_store = self._get_vector_store()

		if getattr(vector_store, "use_fallback", False):
			results: list[dict[str, Any]] = []
			for chunk_id, item in getattr(vector_store, "_fallback_docs", {}).items():
				metadata = item.get("metadata", {})
				if metadata.get("parent_id") == summary_id and metadata.get("chunk_type") == "table":
					results.append(
						{
							"chunk_id": chunk_id,
							"content": item.get("document", ""),
							"metadata": metadata,
							"source": "vector_store",
						}
					)
			return results

		collection = getattr(vector_store, "collection", None)
		if collection is None:
			return []

		try:
			raw = collection.get(
				where={"parent_id": summary_id, "chunk_type": "table"},
				include=["documents", "metadatas"],
			)
		except Exception:
			return []

		ids = raw.get("ids", []) or []
		docs = raw.get("documents", []) or []
		metas = raw.get("metadatas", []) or []
		out: list[dict[str, Any]] = []
		for idx, doc_id in enumerate(ids):
			out.append(
				{
					"chunk_id": doc_id,
					"content": docs[idx] if idx < len(docs) else "",
					"metadata": metas[idx] if idx < len(metas) else {},
					"source": "vector_store",
				}
			)
		return out

	def _fetch_sql_table_rows(
		self,
		query: str,
		filters: Mapping[str, Any],
	) -> list[dict[str, Any]]:
		ticker = filters.get("ticker")
		if not ticker:
			return []

		line_item_like = self._extract_line_item_phrase(query)
		rows = self._get_mysql_loader().get_financial_data(
			ticker=ticker,
			fiscal_year=filters.get("year"),
			report_type=filters.get("report_type"),
			line_item_like=line_item_like,
		)

		if not rows:
			return []
		return [{"source": "mysql", "row": row} for row in rows[:20]]

	def _extract_line_item_phrase(self, query: str) -> str | None:
		terms = re.findall(r"[A-Za-z0-9_]+", query)
		if len(terms) < 2:
			return None
		# Use first 4 terms as a simple LIKE seed phrase.
		return " ".join(terms[:4])

	def _estimate_confidence(self, reranked_hits: list[Any]) -> float:
		if not reranked_hits:
			return 0.0
		top_scores = [float(hit.rerank_score) for hit in reranked_hits[:3]]
		return max(0.0, min(1.0, sum(top_scores) / max(len(top_scores), 1)))

	def _append_error(self, state: MutableMapping[str, Any], message: str) -> None:
		state.setdefault("errors", [])
		if isinstance(state["errors"], list):
			state["errors"].append(message)
		self.logger.error(message)

	def _get_vector_store(self) -> VectorStore:
		if self._vector_store is None:
			self._vector_store = VectorStore()
		return self._vector_store

	def _get_mysql_loader(self) -> MySQLLoader:
		if self._mysql_loader is None:
			self._mysql_loader = MySQLLoader()
		return self._mysql_loader

