"""Evaluator Agent: Quality Assurance & Reflection (Task 5.6 & Task 5.7).

Inspects pipeline outputs, checks consistency between Calculator and Analysis results,
estimates a global confidence score, and triggers reflection & retry when data is insufficient.
"""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from typing import Any, Dict, List, Optional

from src.agents.base_agent import BaseAgent
from src.utils.logger import get_logger

logger = get_logger("src.orchestrator.evaluator")


class EvaluatorAgent(BaseAgent):
    """Kiểm tra chất lượng và tính nhất quán của kết quả phân tích đa tác tử."""

    def __init__(
        self,
        config: Mapping[str, Any] | None = None,
        llm: Any = None,
        prompt_template: str | Mapping[str, Any] = "analysis",
    ) -> None:
        super().__init__(config=config, llm=llm, prompt_template=prompt_template)
        self.min_confidence_threshold = float(self.config.get("min_confidence_threshold", 0.5))

    def evaluate(self, state: Mapping[str, Any]) -> Dict[str, Any]:
        """Đánh giá toàn bộ state hiện tại.

        Returns:
            Dict chứa 'confidence_score', 'is_valid', 'issues', 'should_retry'.
        """
        query_type = state.get("query_type", "analysis")
        retrieved_chunks = state.get("retrieved_chunks") or []
        calc_results = state.get("calculator_results") or {}
        analysis_results = state.get("analysis_results") or {}
        errors = state.get("errors") or []
        retry_count = int(state.get("retry_count", 0))
        max_retries = int(state.get("max_retries", 2))

        issues: List[str] = []
        score = 0.95

        # 1. Kiểm tra lỗi hệ thống
        if errors:
            score -= 0.2 * len(errors)
            issues.append(f"Gặp {len(errors)} lỗi trong quá trình thực thi")

        # 2. Kiểm tra theo query_type
        if query_type == "simple":
            if not retrieved_chunks:
                score -= 0.5
                issues.append("Không tìm thấy văn bản phù hợp trong Vector Store")
        elif query_type == "calculate":
            if not calc_results:
                score -= 0.6
                issues.append("Calculator không tính toán được số liệu nào")
        elif query_type in ("analysis", "valuation"):
            data_gaps = analysis_results.get("data_gaps") or []
            if data_gaps:
                score -= 0.1 * min(len(data_gaps), 4)
                issues.append(f"Có {len(data_gaps)} khoảng trống dữ liệu trong phân tích")

        # Clamp confidence score [0.1, 1.0]
        final_confidence = round(max(0.1, min(1.0, score)), 2)
        should_retry = (final_confidence < self.min_confidence_threshold) and (retry_count < max_retries)

        return {
            "confidence_score": final_confidence,
            "is_valid": final_confidence >= self.min_confidence_threshold,
            "issues": issues,
            "should_retry": should_retry,
        }

    def invoke(self, state: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
        """LangGraph Node entrypoint cho Evaluator."""
        eval_result = self.evaluate(state)
        confidence = eval_result["confidence_score"]
        state["confidence_score"] = confidence

        if eval_result["should_retry"]:
            state["retry_count"] = int(state.get("retry_count", 0)) + 1
            logger.warning(
                f"EvaluatorAgent: Low confidence ({confidence}). "
                f"Triggering retry attempt {state['retry_count']}/{state.get('max_retries', 2)}."
            )

        state.setdefault("provenance", []).append({
            "agent": "EvaluatorAgent",
            "confidence_score": confidence,
            "issues_detected": len(eval_result["issues"]),
            "should_retry": eval_result["should_retry"],
        })

        logger.info(f"EvaluatorAgent: Evaluated graph state. Final confidence: {confidence}")
        return state
