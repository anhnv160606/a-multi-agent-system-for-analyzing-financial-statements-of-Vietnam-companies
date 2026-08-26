"""Hybrid retrieval engine: vector search + keyword search with RRF fusion."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Callable

from src.database.models import VectorSearchResult


TokenizeFn = Callable[[str], list[str]]


def _default_tokenize(text: str) -> list[str]:
	return re.findall(r"[A-Za-z0-9_]+", text.lower())


@dataclass
class HybridSearchHit:
	"""Normalized retrieval record for downstream reranking/agent use."""

	id: str
	content: str
	metadata: dict[str, Any]
	vector_score: float
	keyword_score: float
	hybrid_score: float
	vector_rank: int | None = None
	keyword_rank: int | None = None


class HybridSearch:
	"""Performs hybrid search by combining vector and lexical relevance signals."""

	def __init__(
		self,
		vector_store: Any,
		alpha: float = 0.7,
		rrf_k: int = 60,
		keyword_pool_size: int = 30,
		tokenize_fn: TokenizeFn | None = None,
	) -> None:
		if not 0.0 <= alpha <= 1.0:
			raise ValueError("alpha must be in [0, 1].")

		self.vector_store = vector_store
		self.alpha = alpha
		self.rrf_k = rrf_k
		self.keyword_pool_size = keyword_pool_size
		self.tokenize_fn = tokenize_fn or _default_tokenize

	def search(
		self,
		query: str,
		top_k: int = 8,
		alpha: float | None = None,
		filters: dict[str, Any] | None = None,
	) -> list[HybridSearchHit]:
		"""Run vector retrieval, lexical scoring, then merge by weighted RRF."""
		if not query or not query.strip():
			return []

		alpha_value = self.alpha if alpha is None else alpha
		if not 0.0 <= alpha_value <= 1.0:
			raise ValueError("alpha must be in [0, 1].")

		vector_hits = self._vector_search(query=query, top_k=top_k, filters=filters)
		keyword_hits = self._keyword_search(
			query=query,
			filters=filters,
			candidate_pool=max(top_k, self.keyword_pool_size),
		)
		return self._fuse_results(vector_hits, keyword_hits, top_k=top_k, alpha=alpha_value)

	def _vector_search(
		self,
		query: str,
		top_k: int,
		filters: dict[str, Any] | None,
	) -> list[VectorSearchResult]:
		where = self._normalize_filters(filters)
		results = self.vector_store.query(query_text=query, n_results=top_k, where=where)
		return results or []

	def _keyword_search(
		self,
		query: str,
		filters: dict[str, Any] | None,
		candidate_pool: int,
	) -> list[VectorSearchResult]:
		"""Build lexical ranking from an expanded candidate pool."""
		where = self._normalize_filters(filters)
		candidates = self.vector_store.query(
			query_text=query,
			n_results=candidate_pool,
			where=where,
		)
		if not candidates:
			return []

		query_tokens = self.tokenize_fn(query)
		if not query_tokens:
			return []

		docs_tokens = [self.tokenize_fn(candidate.document) for candidate in candidates]
		doc_freq: dict[str, int] = {}
		for tokens in docs_tokens:
			for token in set(tokens):
				doc_freq[token] = doc_freq.get(token, 0) + 1

		doc_count = len(docs_tokens)
		avg_doc_len = sum(len(tokens) for tokens in docs_tokens) / max(doc_count, 1)
		k1 = 1.5
		b = 0.75

		scored: list[tuple[float, VectorSearchResult]] = []
		for candidate, tokens in zip(candidates, docs_tokens):
			token_count: dict[str, int] = {}
			for token in tokens:
				token_count[token] = token_count.get(token, 0) + 1

			score = 0.0
			doc_len = max(len(tokens), 1)
			for query_token in query_tokens:
				tf = token_count.get(query_token, 0)
				if tf == 0:
					continue

				idf = math.log(
					1
					+ ((doc_count - doc_freq.get(query_token, 0) + 0.5)
					   / (doc_freq.get(query_token, 0) + 0.5))
				)
				numerator = tf * (k1 + 1)
				denominator = tf + k1 * (1 - b + b * (doc_len / max(avg_doc_len, 1)))
				score += idf * (numerator / denominator)

			scored.append((score, candidate))

		scored.sort(key=lambda item: item[0], reverse=True)
		return [candidate for score, candidate in scored if score > 0]

	def _fuse_results(
		self,
		vector_hits: list[VectorSearchResult],
		keyword_hits: list[VectorSearchResult],
		top_k: int,
		alpha: float,
	) -> list[HybridSearchHit]:
		by_id: dict[str, HybridSearchHit] = {}

		vector_rank_map = {hit.id: idx for idx, hit in enumerate(vector_hits, start=1)}
		keyword_rank_map = {hit.id: idx for idx, hit in enumerate(keyword_hits, start=1)}

		for hit in vector_hits:
			by_id[hit.id] = HybridSearchHit(
				id=hit.id,
				content=hit.document,
				metadata=hit.metadata or {},
				vector_score=max(0.0, hit.similarity),
				keyword_score=0.0,
				hybrid_score=0.0,
				vector_rank=vector_rank_map.get(hit.id),
				keyword_rank=keyword_rank_map.get(hit.id),
			)

		for hit in keyword_hits:
			current = by_id.get(hit.id)
			if current is None:
				current = HybridSearchHit(
					id=hit.id,
					content=hit.document,
					metadata=hit.metadata or {},
					vector_score=0.0,
					keyword_score=0.0,
					hybrid_score=0.0,
					vector_rank=vector_rank_map.get(hit.id),
					keyword_rank=keyword_rank_map.get(hit.id),
				)
				by_id[hit.id] = current

			keyword_rank = keyword_rank_map.get(hit.id)
			if keyword_rank is not None:
				current.keyword_rank = keyword_rank
				current.keyword_score = 1.0 / (self.rrf_k + keyword_rank)

		for hit_id, rank in vector_rank_map.items():
			current = by_id[hit_id]
			current.vector_rank = rank
			current.vector_score = 1.0 / (self.rrf_k + rank)

		for current in by_id.values():
			current.hybrid_score = (
				alpha * current.vector_score + (1.0 - alpha) * current.keyword_score
			)

		ranked = sorted(by_id.values(), key=lambda item: item.hybrid_score, reverse=True)
		return ranked[:top_k]

	def _normalize_filters(self, filters: dict[str, Any] | None) -> dict[str, Any] | None:
		"""Adapt multi-field metadata filters to the vector backend format."""
		if not filters:
			return None

		# Local fallback store expects a flat dict and evaluates key-by-key.
		if getattr(self.vector_store, "use_fallback", False):
			return filters

		if len(filters) == 1:
			return filters

		# Chroma validates where with explicit operator for multiple fields.
		return {"$and": [{key: value} for key, value in filters.items()]}

