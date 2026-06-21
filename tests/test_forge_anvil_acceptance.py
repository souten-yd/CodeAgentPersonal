"""PR16: Anvil real-evaluation acceptance with natural fallback evidence."""
from __future__ import annotations

import json

from agent.model_forge.anvil_acceptance import (
    NATURAL_FALLBACK_TRIGGERS,
    AnvilAcceptanceRunner,
    check_anvil_ready,
    default_scenarios,
)

MODEL = "Qwen3.6-35B-A3B-UD-IQ4_XS.gguf"
BASE = "http://127.0.0.1:8080"


def _models_response(*ids: str) -> tuple[int, str]:
    return 200, json.dumps({"object": "list", "data": [{"id": i} for i in ids]})


def _served_get(_url: str, _timeout: float) -> tuple[int, str]:
    return _models_response(MODEL)


def _absent_get(_url: str, _timeout: float) -> tuple[int, str]:
    return _models_response("some-other-model")


def _scripted_post(_url, payload, _headers, _timeout) -> tuple[int, str]:
    """Weak-model stand-in: every structured/edit/anchored method fails the contract;
    only the review-only terminal returns usable prose."""
    user = payload["messages"][1]["content"]
    if "review findings" in user:
        content = "Severity: low. The change looks safe; no patch produced."
    else:
        content = "Sure! I think you should just edit the file. (no structured output)"
    return 200, json.dumps({
        "id": "chatcmpl-stub",
        "choices": [{"message": {"content": content}}],
    })


def test_readiness_confirms_served_model() -> None:
    readiness = check_anvil_ready(BASE, MODEL, http_get=_served_get)
    assert readiness.ready is True
    assert readiness.detail == "model_served"
    assert MODEL in readiness.served_models


def test_readiness_pending_when_model_not_served() -> None:
    readiness = check_anvil_ready(BASE, MODEL, http_get=_absent_get)
    assert readiness.ready is False
    assert readiness.detail == "model_not_served"


def test_pending_when_anvil_not_ready_is_not_passed(tmp_path) -> None:
    runner = AnvilAcceptanceRunner(tmp_path, http_get=_absent_get, http_post=_scripted_post)
    report = runner.run(provider_id="local_openai_compatible", model_id=MODEL, base_url=BASE)
    assert report["anvil_ready"] is False
    assert report["proof_level"] == "anvil_real_eval_pending"
    assert report["natural_fallback_observed"] is False
    assert report["scenarios"] == []


def test_natural_fallback_recovers_and_passes(tmp_path) -> None:
    runner = AnvilAcceptanceRunner(tmp_path, http_get=_served_get, http_post=_scripted_post)
    report = runner.run(provider_id="local_openai_compatible", model_id=MODEL, base_url=BASE)

    assert report["anvil_ready"] is True
    assert report["natural_fallback_observed"] is True
    assert report["natural_fallback_recovered"] is True
    assert report["proof_level"] == "anvil_real_eval_passed"

    first = report["scenarios"][0]
    # The primary structured method must genuinely fail before fallback fires.
    assert first["primary"] == "structured_patch_json"
    assert len(first["attempts"]) > 1
    assert first["attempts"][0]["status"] != "passed"
    # Fallback terminates on review-only, which recovers without applying a file.
    assert first["selected_method"] == "review_only"
    assert first["final_status"] == "passed"
    assert first["fallback_reasons"]

    # Evidence is persisted and resolvable.
    report_ref = report["report_ref"]
    assert json.loads(open(report_ref, encoding="utf-8").read())["run_id"] == report["run_id"]
    transcript = json.loads(open(first["raw_output_ref"], encoding="utf-8").read())
    assert any(entry["method_variant"] == "review_only" for entry in transcript)


def test_safe_apply_boundary_never_bypassed(tmp_path) -> None:
    runner = AnvilAcceptanceRunner(tmp_path, http_get=_served_get, http_post=_scripted_post)
    report = runner.run(provider_id="local_openai_compatible", model_id=MODEL, base_url=BASE)
    for scenario in report["scenarios"]:
        for attempt in scenario["attempts"]:
            assert "safe_apply_bypass" not in attempt["blocked_reasons"]


def test_default_scenarios_use_real_failure_triggers() -> None:
    for scenario in default_scenarios():
        for step in scenario.chain.fallbacks:
            assert set(step.trigger_on) == set(NATURAL_FALLBACK_TRIGGERS)
        assert "content_missing" in NATURAL_FALLBACK_TRIGGERS
        assert "file_changes_missing" in NATURAL_FALLBACK_TRIGGERS
