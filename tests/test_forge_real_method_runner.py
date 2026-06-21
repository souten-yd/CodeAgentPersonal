from __future__ import annotations

import json

from agent.model_forge.candidate_evaluator import EvaluatorOutcome
from agent.model_forge.eval_packs import pack_for_dimension
from agent.model_forge.real_method_runner import RealMethodRunner


def test_real_runner_records_usage_latency_and_raw_evidence(tmp_path):
    def fake_post(_url, payload, headers, _timeout):
        assert headers == {}
        assert payload["stream"] is False
        return 200, json.dumps({
            "id": "chatcmpl-test",
            "choices": [{"message": {"content": json.dumps({
                "intents": [{"path": "eval_target.txt", "old_text": "old", "new_text": "new"}]
            })}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        })

    case = pack_for_dimension("edit_intent_quality").cases[0]
    result = RealMethodRunner(tmp_path, http_post=fake_post).run_cases(
        provider_id="local_openai_compatible",
        model_id="model",
        base_url="http://127.0.0.1:8080",
        cases=[case],
    )[0]
    assert result.outcome == EvaluatorOutcome.PASSED
    evidence = json.loads(open(result.evidence_refs[0], encoding="utf-8").read())
    assert evidence["usage"]["total_tokens"] == 30
    assert evidence["response_id"] == "chatcmpl-test"
    assert evidence["base_url"] == "http://127.0.0.1:8080"
    assert evidence["latency_ms"] >= 0
    assert open(evidence["raw_output_ref"], encoding="utf-8").read()


def test_transport_failure_is_unavailable_with_evidence(tmp_path):
    def unavailable(*_args):
        raise ConnectionError("offline")

    case = pack_for_dimension("structured_output_fidelity").cases[0]
    result = RealMethodRunner(tmp_path, http_post=unavailable).run_cases(
        provider_id="anvil",
        model_id="model",
        base_url="http://127.0.0.1:1",
        cases=[case],
    )[0]
    assert result.outcome == EvaluatorOutcome.UNAVAILABLE
    assert result.outcome != EvaluatorOutcome.PASSED
    assert result.evidence_refs


def test_external_provider_is_blocked_in_local_only_without_call(tmp_path):
    called = False

    def forbidden(*_args):
        nonlocal called
        called = True
        raise AssertionError("must not call external provider")

    case = pack_for_dimension("structured_output_fidelity").cases[0]
    result = RealMethodRunner(tmp_path, http_post=forbidden).run_cases(
        provider_id="openrouter",
        model_id="external",
        base_url="https://openrouter.ai/api",
        cases=[case],
        source_mode="local_only",
    )[0]
    assert result.outcome == EvaluatorOutcome.UNAVAILABLE
    assert result.detail == "external_provider_blocked_in_local_only"
    assert called is False


def test_unsupported_semantic_dimension_is_unavailable(tmp_path):
    case = pack_for_dimension("fallback_recovery").cases[0]
    result = RealMethodRunner(tmp_path).run_cases(
        provider_id="local_openai_compatible",
        model_id="model",
        base_url="http://127.0.0.1:8080",
        cases=[case],
    )[0]
    assert result.outcome == EvaluatorOutcome.UNAVAILABLE
    assert result.detail == "mechanical_evaluator_unavailable"
