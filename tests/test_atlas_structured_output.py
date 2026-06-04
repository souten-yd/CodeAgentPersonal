from __future__ import annotations

from typing import Any

from agent.atlas_llm_output_models import PlanGenerationOutput
from agent.atlas_structured_output import generate_structured


class _CountingLLM:
    """2-arg callable (the historical llm_json_fn shape) that records call count and replays a script."""

    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)
        self.calls = 0

    def __call__(self, _system: str, _user: str) -> Any:
        self.calls += 1
        idx = min(self.calls - 1, len(self._responses) - 1)
        return self._responses[idx]


_PLAN_SCHEMA = {"type": "object", "properties": {"implementation_steps": {"type": "array"}}, "required": []}


def test_valid_payload_passes_without_retry() -> None:
    llm = _CountingLLM([{"implementation_steps": [{"title": "step 1"}]}])
    result = generate_structured(llm, "sys", "user", json_schema=_PLAN_SCHEMA, model=PlanGenerationOutput)
    assert result.ok is True
    assert result.attempts == 1
    assert llm.calls == 1
    assert result.model is not None
    assert result.data == {"implementation_steps": [{"title": "step 1"}]}


def test_empty_steps_triggers_bounded_retry_then_best_effort_data() -> None:
    # Empty implementation_steps fails validation (min_length=1) so the helper retries once, then
    # surfaces ok=False while still returning the last raw dict for the caller's graceful fallback.
    llm = _CountingLLM([{"implementation_steps": []}])
    result = generate_structured(llm, "sys", "user", json_schema=_PLAN_SCHEMA, model=PlanGenerationOutput)
    assert result.ok is False
    assert result.attempts == 2
    assert llm.calls == 2
    assert result.data == {"implementation_steps": []}
    assert any("validation_failed" in w for w in result.warnings)


def test_retry_recovers_when_second_response_is_valid() -> None:
    llm = _CountingLLM([{"implementation_steps": []}, {"implementation_steps": [{"title": "ok"}]}])
    result = generate_structured(llm, "sys", "user", json_schema=_PLAN_SCHEMA, model=PlanGenerationOutput)
    assert result.ok is True
    assert result.attempts == 2
    assert llm.calls == 2


def test_unparseable_output_returns_none_data() -> None:
    llm = _CountingLLM([None])
    result = generate_structured(llm, "sys", "user", json_schema=_PLAN_SCHEMA, model=PlanGenerationOutput)
    assert result.ok is False
    assert result.data is None
    assert any("parse_failed" in w for w in result.warnings)


def test_none_llm_is_safe() -> None:
    result = generate_structured(None, "sys", "user", json_schema=_PLAN_SCHEMA, model=PlanGenerationOutput)
    assert result.ok is False
    assert result.data is None
