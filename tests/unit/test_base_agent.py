import logging
from collections.abc import Mapping, MutableMapping
from pathlib import Path
from typing import Any

import pytest

from src.agents.base_agent import BaseAgent, track_tokens


class DummyAgent(BaseAgent):
    def __init__(self, config: Mapping[str, Any] | None, llm: Any, prompt_template: Any):
        super().__init__(config=config, llm=llm, prompt_template=prompt_template)

    def invoke(self, state: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
        state["handled_by"] = self.__class__.__name__
        return state


class PromptDirAgent(DummyAgent):
    def __init__(
        self,
        config: Mapping[str, Any] | None,
        llm: Any,
        prompt_template: Any,
        prompts_dir: Path,
    ):
        self._test_prompts_dir = prompts_dir
        super().__init__(config=config, llm=llm, prompt_template=prompt_template)

    def _get_prompts_dir(self) -> Path:
        return self._test_prompts_dir


class TokenAgent(DummyAgent):
    @track_tokens
    def call_llm(self, response: Any) -> Any:
        return response


@pytest.fixture
def valid_prompt_payload() -> dict[str, Any]:
    return {
        "system_prompt": "You are a finance assistant.",
        "user_template": "Summarize {{ticker}}.",
        "variables": ["ticker"],
    }


def test_load_prompt_success(tmp_path: Path, valid_prompt_payload: dict[str, Any]) -> None:
    prompt_file = tmp_path / "retriever.yaml"
    prompt_file.write_text(
        "system_prompt: You are a finance assistant.\n"
        "user_template: Summarize {{ticker}}.\n"
        "variables:\n"
        "  - ticker\n",
        encoding="utf-8",
    )

    agent = PromptDirAgent(
        config={},
        llm=None,
        prompt_template="retriever",
        prompts_dir=tmp_path,
    )

    assert agent.prompt_template == valid_prompt_payload


def test_load_prompt_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        PromptDirAgent(
            config={},
            llm=None,
            prompt_template="does_not_exist",
            prompts_dir=tmp_path,
        )


def test_load_prompt_rejects_invalid_template_name(tmp_path: Path) -> None:
    agent = PromptDirAgent(
        config={},
        llm=None,
        prompt_template={"system_prompt": "s", "user_template": "u"},
        prompts_dir=tmp_path,
    )

    with pytest.raises(ValueError):
        agent._load_prompt("../secrets")


def test_load_prompt_rejects_invalid_schema(tmp_path: Path) -> None:
    invalid_prompt = tmp_path / "invalid.yaml"
    invalid_prompt.write_text("system_prompt: hi\n", encoding="utf-8")

    with pytest.raises(ValueError):
        PromptDirAgent(
            config={},
            llm=None,
            prompt_template="invalid",
            prompts_dir=tmp_path,
        )


def test_log_step_emits_structured_fields(caplog: pytest.LogCaptureFixture) -> None:
    agent = DummyAgent(
        config={"confidence_warning_threshold": 0.6},
        llm=None,
        prompt_template={"system_prompt": "s", "user_template": "u"},
    )
    agent.logger = logging.getLogger("tests.base_agent")

    with caplog.at_level(logging.INFO, logger="tests.base_agent"):
        agent._log_step(
            input={"run_id": "r1", "trace_id": "t1", "ticker": "FPT"},
            output={"result": "ok", "source_file": "f.pdf", "page": 3},
            confidence=0.9,
        )

    assert any(record.message == "agent_step_completed" for record in caplog.records)
    record = next(record for record in caplog.records if record.message == "agent_step_completed")
    assert record.__dict__["event"] == "agent_step"
    assert record.__dict__["agent"] == "DummyAgent"
    assert record.__dict__["confidence"] == 0.9
    assert record.__dict__["source_file"] == "f.pdf"


def test_log_step_warns_on_low_confidence(caplog: pytest.LogCaptureFixture) -> None:
    agent = DummyAgent(
        config={"confidence_warning_threshold": 0.6},
        llm=None,
        prompt_template={"system_prompt": "s", "user_template": "u"},
    )
    agent.logger = logging.getLogger("tests.base_agent_low_conf")

    with caplog.at_level(logging.WARNING, logger="tests.base_agent_low_conf"):
        agent._log_step(input={"run_id": "r1"}, output={"result": "weak"}, confidence=0.2)

    assert any(record.message == "agent_step_low_confidence" for record in caplog.records)


def test_track_tokens_uses_response_usage(caplog: pytest.LogCaptureFixture) -> None:
    agent = TokenAgent(
        config={},
        llm=None,
        prompt_template={"system_prompt": "s", "user_template": "u"},
    )
    agent.logger = logging.getLogger("tests.base_agent_tokens")

    with caplog.at_level(logging.INFO, logger="tests.base_agent_tokens"):
        response = {"usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14}}
        result = agent.call_llm(response)

    assert result == response
    assert agent._token_usage["prompt_tokens"] == 10
    assert agent._token_usage["completion_tokens"] == 4
    assert agent._token_usage["total_tokens"] == 14
    assert any(record.message == "llm_tokens_tracked" for record in caplog.records)


def test_track_tokens_warns_when_usage_missing(caplog: pytest.LogCaptureFixture) -> None:
    agent = TokenAgent(
        config={},
        llm=None,
        prompt_template={"system_prompt": "s", "user_template": "u"},
    )
    agent.logger = logging.getLogger("tests.base_agent_no_usage")

    with caplog.at_level(logging.WARNING, logger="tests.base_agent_no_usage"):
        response = {"text": "no usage payload"}
        result = agent.call_llm(response)

    assert result == response
    assert agent._token_usage["total_tokens"] == 0
    assert any(record.message == "llm_token_usage_missing" for record in caplog.records)
