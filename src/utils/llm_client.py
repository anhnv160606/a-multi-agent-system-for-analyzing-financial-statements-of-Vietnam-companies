"""Unified Multi-Provider LLM Client with Smart Failover & Load Balancing (Task 0.5).

Supports 100% Free Tiers across multiple AI Providers:
  1. Google Gemini (GEMINI_API_KEY / GOOGLE_API_KEY)
  2. Groq (GROQ_API_KEY: Llama-3.3-70b, DeepSeek-R1, Llama-3.1-8b)
  3. OpenRouter / OpenAI Compatible (OPENROUTER_API_KEY / OPENAI_API_KEY)

Features:
  - Per-agent provider routing (configure in configs/models.yaml)
  - Automatic Rate-Limit Failover (switches to another provider if 429 quota is hit)
  - Zero-Hallucination Fallback if all API keys are exhausted
"""

from __future__ import annotations

import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional
import warnings
import yaml

# Suppress google.generativeai deprecation warning for clean output
warnings.filterwarnings("ignore", category=FutureWarning, module="google.generativeai")
warnings.filterwarnings("ignore", message=".*All support for the `google.generativeai` package has ended.*")

from src.utils.logger import get_logger

logger = get_logger("src.utils.llm_client")


def _load_env_file():
    """Loads environment variables from .env if present."""
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    if k and v and k not in os.environ:
                        os.environ[k] = v


_load_env_file()


class LLMResponse:
    """Standard response object compatible across all agents."""

    def __init__(self, content: str, model: str = "", provider: str = "", raw: Any = None):
        self.content = content
        self.model = model
        self.provider = provider
        self.raw = raw
        self.usage_metadata = {"total_tokens": len(content.split()) * 2}

    def __str__(self) -> str:
        return self.content


class MultiProviderLLM:
    """Multi-Provider LLM Wrapper with auto-failover across Gemini, Groq, OpenRouter."""

    def __init__(
        self,
        provider: str = "gemini",
        model_name: str = "gemini-flash-latest",
        temperature: float = 0.2,
    ):
        self.provider = provider.lower()
        self.model_name = model_name
        self.temperature = temperature
        self._gemini_client = None
        self._openai_client = None

    def _call_gemini(self, prompt: str, model_override: Optional[str] = None) -> str:
        """Invokes Google Gemini API."""
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set.")

        import google.generativeai as genai
        genai.configure(api_key=api_key)
        target_model = model_override or self.model_name or "gemini-flash-latest"
        model = genai.GenerativeModel(
            model_name=target_model,
            generation_config=genai.types.GenerationConfig(temperature=self.temperature),
        )
        resp = model.generate_content(prompt)
        return resp.text if hasattr(resp, "text") else str(resp)

    def _call_groq(self, prompt: str, model_override: Optional[str] = None) -> str:
        """Invokes Groq API via OpenAI-compatible endpoint."""
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY is not set.")

        from openai import OpenAI
        client = OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=api_key,
        )
        target_model = model_override or self.model_name
        if "gemini" in target_model:
            target_model = "llama-3.3-70b-versatile"

        resp = client.chat.completions.create(
            model=target_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=self.temperature,
        )
        return resp.choices[0].message.content or ""

    def _call_openrouter(self, prompt: str, model_override: Optional[str] = None) -> str:
        """Invokes OpenRouter API."""
        api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY is not set.")

        from openai import OpenAI
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            max_retries=0,
            timeout=10.0,
        )
        target_model = model_override or self.model_name
        if "meta-llama" in target_model or "llama" in target_model or not target_model:
            target_model = "minimax/minimax-m3:free"

        resp = client.chat.completions.create(
            model=target_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=self.temperature,
        )
        return resp.choices[0].message.content or ""

    def invoke(self, prompt: str) -> LLMResponse:
        """
        Calls primary provider with automatic multi-provider failover on error/quota.
        """
        _load_env_file()
        errors: List[str] = []

        # Build prioritized provider sequence
        candidate_providers = [self.provider]
        for p in ["groq", "gemini", "openrouter"]:
            if p not in candidate_providers:
                candidate_providers.append(p)

        for prov in candidate_providers:
            try:
                if prov == "groq" and os.environ.get("GROQ_API_KEY"):
                    model = self.model_name if "qwen" in self.model_name or "groq" in self.model_name or "gpt" in self.model_name else "qwen/qwen3.8-27b"
                    content = self._call_groq(prompt, model_override=model)
                    return LLMResponse(content=content, model=model, provider="groq")

                elif prov == "gemini" and (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
                    model = self.model_name if "gemini" in self.model_name else "gemini-3.1-flash-lite"
                    content = self._call_gemini(prompt, model_override=model)
                    return LLMResponse(content=content, model=model, provider="gemini")

                elif prov == "openrouter" and os.environ.get("OPENROUTER_API_KEY"):
                    content = self._call_openrouter(prompt)
                    return LLMResponse(content=content, model="openrouter-free", provider="openrouter")

            except Exception as e:
                err_msg = f"Provider '{prov}' failed: {e}"
                logger.warning(err_msg)
                errors.append(err_msg)

        raise RuntimeError(f"All LLM Providers failed. Errors: {'; '.join(errors)}")


def get_default_llm(agent_type: str = "default") -> Optional[MultiProviderLLM]:
    """Loads model and provider routing configuration from configs/models.yaml."""
    _load_env_file()

    # Check if at least one API key exists
    has_any_key = any([
        os.environ.get("GEMINI_API_KEY"),
        os.environ.get("GOOGLE_API_KEY"),
        os.environ.get("GROQ_API_KEY"),
        os.environ.get("OPENROUTER_API_KEY"),
        os.environ.get("OPENAI_API_KEY"),
    ])
    if not has_any_key:
        return None

    config_path = Path(__file__).resolve().parents[2] / "configs" / "models.yaml"
    provider = "gemini"
    model_name = "gemini-flash-latest"
    temperature = 0.2

    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
                agent_cfg = {}
                if agent_type == "router" and "router" in cfg:
                    agent_cfg = cfg["router"]
                elif "agents" in cfg and agent_type in cfg["agents"]:
                    agent_cfg = cfg["agents"][agent_type]

                provider = agent_cfg.get("provider", "groq" if os.environ.get("GROQ_API_KEY") else "gemini")
                model_name = agent_cfg.get("model", model_name)
                temperature = float(agent_cfg.get("temperature", temperature))
        except Exception as e:
            logger.warning(f"Could not load models.yaml: {e}")

    return MultiProviderLLM(provider=provider, model_name=model_name, temperature=temperature)
