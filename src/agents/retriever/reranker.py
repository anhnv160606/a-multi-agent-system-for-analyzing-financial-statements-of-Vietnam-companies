"""Reranker utilities for post-retrieval precision improvements."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from src.agents.retriever.hybrid_search import HybridSearchHit


@dataclass
class RerankedHit(HybridSearchHit):
	"""Hybrid hit extended with reranking signals."""

	rerank_score: float = 0.0
	rerank_reason: str = ""


class RetrieverReranker:
	"""Rerank candidate chunks using either heuristic or LLM relevance scoring."""

	def __init__(
		self,
		llm: Any | None = None,
		strategy: str = "none",
		top_n: int = 10,
		batch_size: int = 5,
	) -> None:
		self.llm = llm
		self.strategy = strategy
		self.top_n = top_n
		self.batch_size = max(1, batch_size)

	def rerank(self, query: str, candidates: list[HybridSearchHit]) -> list[RerankedHit]:
		if not candidates:
			return []

		if self.strategy == "none" or self.llm is None:
			return self._heuristic_rerank(query=query, candidates=candidates)

		if self.strategy == "llm":
			return self._llm_rerank(query=query, candidates=candidates)

		raise ValueError(f"Unsupported reranker strategy: {self.strategy}")

	def _heuristic_rerank(self, query: str, candidates: list[HybridSearchHit]) -> list[RerankedHit]:
		query_tokens = set(re.findall(r"[A-Za-z0-9_]+", query.lower()))
		reranked: list[RerankedHit] = []

		for candidate in candidates:
			content_tokens = set(re.findall(r"[A-Za-z0-9_]+", candidate.content.lower()))
			overlap = len(query_tokens.intersection(content_tokens))
			lexical_score = overlap / max(len(query_tokens), 1)
			score = 0.7 * candidate.hybrid_score + 0.3 * lexical_score

			reranked.append(
				RerankedHit(
					**candidate.__dict__,
					rerank_score=score,
					rerank_reason="heuristic_overlap",
				)
			)

		reranked.sort(key=lambda item: item.rerank_score, reverse=True)
		return reranked[: self.top_n]

	def _llm_rerank(self, query: str, candidates: list[HybridSearchHit]) -> list[RerankedHit]:
		reranked: list[RerankedHit] = []
		scoped = candidates[: self.top_n]
		score_map = self._score_candidates_with_llm_batch(query=query, candidates=scoped)

		for candidate in scoped:
			score = score_map.get(candidate.id)
			if score is None:
				score = candidate.hybrid_score
				reason = "fallback_hybrid_score"
			else:
				reason = "llm_relevance"

			reranked.append(
				RerankedHit(
					**candidate.__dict__,
					rerank_score=score,
					rerank_reason=reason,
				)
			)

		reranked.sort(key=lambda item: item.rerank_score, reverse=True)
		return reranked

	def _score_candidates_with_llm_batch(
		self,
		query: str,
		candidates: list[HybridSearchHit],
	) -> dict[str, float]:
		"""Ask the model to score a batch of candidates in one request."""
		if not candidates:
			return {}

		scores: dict[str, float] = {}
		for start in range(0, len(candidates), self.batch_size):
			batch = candidates[start : start + self.batch_size]
			prompt = self._build_batch_prompt(query=query, candidates=batch)
			response = self._invoke_llm(prompt)
			batch_scores = self._parse_score_batch(response)
			scores.update(batch_scores)
		return scores

	def _build_batch_prompt(self, query: str, candidates: list[HybridSearchHit]) -> str:
		payload = []
		for candidate in candidates:
			payload.append(
				{
					"id": candidate.id,
					"metadata": candidate.metadata,
					"content": candidate.content[:1200],
				}
			)

		return (
			"You are a retrieval relevance grader. For each candidate, return a score from 0..1 "
			"that reflects how useful the candidate is for answering the query. "
			"Return only JSON object with shape {\"scores\": [{\"id\": str, \"score\": float}]}.\n\n"
			f"Query: {query}\n"
			f"Candidates: {json.dumps(payload, ensure_ascii=False)}"
		)

	def _parse_score_batch(self, response: Any) -> dict[str, float]:
		if response is None:
			return {}

		if isinstance(response, dict):
			payload = response
		else:
			content = getattr(response, "text", None) or getattr(response, "content", None) or str(response)
			try:
				payload = json.loads(content)
			except Exception:
				return {}

		scores_raw = payload.get("scores")
		if not isinstance(scores_raw, list):
			return {}

		scores: dict[str, float] = {}
		for item in scores_raw:
			if not isinstance(item, dict):
				continue
			item_id = item.get("id")
			if not isinstance(item_id, str):
				continue
			try:
				score = float(item.get("score"))
			except (TypeError, ValueError):
				continue
			scores[item_id] = max(0.0, min(1.0, score))

		return scores

	def _score_candidate_with_llm(
		self,
		query: str,
		candidate: HybridSearchHit,
	) -> tuple[float, str]:
		prompt = (
			"You are a retrieval relevance grader. "
			"Score the following candidate chunk for the user query on a scale 0..1. "
			"Return only JSON with keys score and reason.\n\n"
			f"Query: {query}\n"
			f"Candidate metadata: {json.dumps(candidate.metadata, ensure_ascii=False)}\n"
			f"Candidate content:\n{candidate.content[:1500]}"
		)

		response = self._invoke_llm(prompt)
		score = self._parse_score(response)
		if score is None:
			return candidate.hybrid_score, "fallback_hybrid_score"
		return score, "llm_relevance"

	def _invoke_llm(self, prompt: str) -> Any:
		if self.llm is None:
			return None

		if hasattr(self.llm, "invoke"):
			return self.llm.invoke(prompt)
		if hasattr(self.llm, "generate_content"):
			return self.llm.generate_content(prompt)
		if callable(self.llm):
			return self.llm(prompt)
		raise ValueError("Provided llm object does not expose a supported call interface.")

	def _parse_score(self, response: Any) -> float | None:
		if response is None:
			return None

		content: str
		if isinstance(response, dict):
			if "score" in response:
				try:
					return max(0.0, min(1.0, float(response["score"])))
				except (TypeError, ValueError):
					return None
			content = json.dumps(response, ensure_ascii=False)
		else:
			content = getattr(response, "text", None) or getattr(response, "content", None) or str(response)

		# JSON-first parsing
		try:
			payload = json.loads(content)
			if isinstance(payload, dict) and "score" in payload:
				return max(0.0, min(1.0, float(payload["score"])))
		except Exception:
			pass

		# Fallback to first decimal in response text
		match = re.search(r"([01](?:\.\d+)?)", content)
		if not match:
			return None

		try:
			return max(0.0, min(1.0, float(match.group(1))))
		except (TypeError, ValueError):
			return None

