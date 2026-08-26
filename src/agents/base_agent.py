"""Shared base abstractions for all workflow agents."""

from __future__ import annotations

import logging
import re
import time
from abc import ABC, abstractmethod
from collections.abc import Mapping, MutableMapping
from functools import wraps
from pathlib import Path
from typing import Any, Callable

import yaml

from src.utils.logger import get_logger


PromptPayload = dict[str, Any]
_TEMPLATE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]+(?:\\.yaml)?$")


def _safe_preview(value: Any, limit: int = 400) -> str:
	"""Return a bounded string preview for logging payloads."""
	text = str(value)
	if len(text) <= limit:
		return text
	return f"{text[:limit]}..."


def _extract_usage_payload(response: Any) -> dict[str, int] | None:
	"""Extract token usage metadata from common LLM response shapes."""
	usage: Any = None

	if isinstance(response, Mapping):
		usage = response.get("usage") or response.get("usage_metadata")
	else:
		usage = getattr(response, "usage", None) or getattr(
			response, "usage_metadata", None
		)

	if usage is None:
		return None

	if not isinstance(usage, Mapping):
		usage = {
			key: getattr(usage, key)
			for key in dir(usage)
			if not key.startswith("_") and hasattr(usage, key)
		}

	def _read_int(data: Mapping[str, Any], *keys: str) -> int | None:
		for key in keys:
			value = data.get(key)
			if value is None:
				continue
			try:
				return int(value)
			except (TypeError, ValueError):
				continue
		return None

	prompt_tokens = _read_int(usage, "prompt_tokens", "input_tokens")
	completion_tokens = _read_int(usage, "completion_tokens", "output_tokens")
	total_tokens = _read_int(usage, "total_tokens")

	if total_tokens is None and (prompt_tokens is not None or completion_tokens is not None):
		total_tokens = (prompt_tokens or 0) + (completion_tokens or 0)

	if prompt_tokens is None and completion_tokens is None and total_tokens is None:
		return None

	return {
		"prompt_tokens": prompt_tokens or 0,
		"completion_tokens": completion_tokens or 0,
		"total_tokens": total_tokens or 0,
	}


def track_tokens(func: Callable[..., Any]) -> Callable[..., Any]:
	"""Decorator to track token usage whenever a method calls an LLM."""

	@wraps(func)
	def wrapper(self: "BaseAgent", *args: Any, **kwargs: Any) -> Any:
		start = time.perf_counter()
		response = func(self, *args, **kwargs)
		latency_ms = round((time.perf_counter() - start) * 1000, 2)

		usage_payload = _extract_usage_payload(response)
		if usage_payload is None:
			self.logger.warning(
				"llm_token_usage_missing",
				extra={
					"event": "llm_token_tracking",
					"agent": self.__class__.__name__,
					"method": func.__name__,
					"latency_ms": latency_ms,
				},
			)
			return response

		self._token_usage["prompt_tokens"] += usage_payload["prompt_tokens"]
		self._token_usage["completion_tokens"] += usage_payload["completion_tokens"]
		self._token_usage["total_tokens"] += usage_payload["total_tokens"]

		self.logger.info(
			"llm_tokens_tracked",
			extra={
				"event": "llm_token_tracking",
				"agent": self.__class__.__name__,
				"method": func.__name__,
				"latency_ms": latency_ms,
				**usage_payload,
				"aggregate_total_tokens": self._token_usage["total_tokens"],
			},
		)
		return response

	return wrapper


class BaseAgent(ABC):
	"""Abstract shared base for all agents in the analysis workflow."""

	def __init__(
		self,
		config: Mapping[str, Any] | None,
		llm: Any,
		prompt_template: str | Mapping[str, Any],
	) -> None:
		self.config: dict[str, Any] = dict(config or {})
		self.llm = llm
		self.logger = get_logger(f"src.agents.{self.__class__.__name__.lower()}")
		self._token_usage: dict[str, int] = {
			"prompt_tokens": 0,
			"completion_tokens": 0,
			"total_tokens": 0,
		}

		if isinstance(prompt_template, str):
			self.prompt_template: PromptPayload = self._load_prompt(prompt_template)
		elif isinstance(prompt_template, Mapping):
			self.prompt_template = dict(prompt_template)
		else:
			raise ValueError("prompt_template must be a template name or a mapping.")

	@abstractmethod
	def invoke(self, state: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
		"""Main agent entrypoint. Subclasses must override this method."""

	def _get_prompts_dir(self) -> Path:
		"""Return the canonical prompts directory."""
		return Path(__file__).resolve().parents[2] / "prompts"

	def _load_prompt(self, template_name: str) -> PromptPayload:
		"""Load prompt payload from prompts directory with path-safety checks."""
		if not isinstance(template_name, str) or not template_name.strip():
			raise ValueError("template_name must be a non-empty string.")

		if not _TEMPLATE_NAME_PATTERN.fullmatch(template_name):
			raise ValueError(
				"template_name must use only letters, numbers, underscore, hyphen, optionally ending in .yaml."
			)

		prompt_file = template_name if template_name.endswith(".yaml") else f"{template_name}.yaml"
		prompts_dir = self._get_prompts_dir().resolve()
		prompt_path = (prompts_dir / prompt_file).resolve()

		try:
			prompt_path.relative_to(prompts_dir)
		except ValueError as exc:
			raise ValueError("template_name resolves outside prompts directory.") from exc

		if not prompt_path.exists() or not prompt_path.is_file():
			raise FileNotFoundError(f"Prompt template not found: {prompt_file}")

		with open(prompt_path, "r", encoding="utf-8") as handle:
			payload = yaml.safe_load(handle)

		if not isinstance(payload, Mapping):
			raise ValueError("Prompt template payload must be a mapping.")

		required_keys = ("system_prompt", "user_template")
		missing = [key for key in required_keys if not payload.get(key)]
		if missing:
			raise ValueError(f"Prompt template is missing required keys: {missing}")

		variables = payload.get("variables")
		if variables is not None and (
			not isinstance(variables, list)
			or any(not isinstance(variable, str) for variable in variables)
		):
			raise ValueError("Prompt template key 'variables' must be a list of strings.")

		return dict(payload)

	def _log_step(self, input: Any, output: Any, confidence: float) -> None:
		"""Emit a structured step log with provenance-friendly metadata."""
		input_preview = _safe_preview(input)
		output_preview = _safe_preview(output)
		confidence_threshold = float(self.config.get("confidence_warning_threshold", 0.5))

		provenance_source: Mapping[str, Any] = {}
		if isinstance(output, Mapping):
			provenance_source = output
		elif isinstance(input, Mapping):
			provenance_source = input

		extra_fields = {
			"event": "agent_step",
			"agent": self.__class__.__name__,
			"confidence": float(confidence),
			"input_preview": input_preview,
			"output_preview": output_preview,
			"input_chars": len(str(input)),
			"output_chars": len(str(output)),
			"run_id": provenance_source.get("run_id"),
			"trace_id": provenance_source.get("trace_id"),
			"ticker": provenance_source.get("ticker"),
			"report_type": provenance_source.get("report_type"),
			"source_file": provenance_source.get("source_file"),
			"page": provenance_source.get("page"),
		}

		log_level = logging.INFO
		message = "agent_step_completed"
		if confidence < confidence_threshold:
			log_level = logging.WARNING
			message = "agent_step_low_confidence"

		self.logger.log(log_level, message, extra=extra_fields)

