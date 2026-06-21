"""PR17: Natural fallback pack — induce each real failure mode, fall back safely."""
from __future__ import annotations

import json

from agent.model_forge.method_taxonomy import MethodVariant
from agent.model_forge.natural_fallback_pack import (
    FAILURE_MODES,
    NaturalFallbackCase,
    NaturalFallbackPackRunner,
    default_fallback_pack,
)

MODEL = "Qwen3.6-35B-A3B-UD-IQ4_XS.gguf"
BASE = "http://127.0.0.1:8080"


def _served_get(_url: str, _timeout: float) -> tuple[int, str]:
    return 200, json.dumps({"object": "list", "data": [{"id": MODEL}]})


def _ok(content: str) -> tuple[int, str]:
    return 200, json.dumps({"id": "stub", "choices": [{"message": {"content": content}}]})


def _prose_post(url, payload, _headers, _timeout) -> tuple[int, str]:
    """Weak-model stand-in: structured/edit/anchored get prose (schema_invalid); the
    unreachable discard port raises a transport error; review-only returns usable text."""
    if url.startswith("http://127.0.0.1:9"):
        raise ConnectionRefusedError("refused")
    user = payload["messages"][1]["content"]
    if "review findings" in user:
        return _ok("Severity: low. The change looks safe; no patch produced.")
    return _ok("Here is some prose explaining the change, not JSON.")


def test_pack_covers_every_failure_mode() -> None:
    modes = [case.mode for case in default_fallback_pack()]
    assert modes == FAILURE_MODES
    assert "provider_unavailable" in modes


def test_schema_invalid_naturally_falls_back_and_recovers(tmp_path) -> None:
    case = NaturalFallbackCase(
        mode="schema_invalid",
        primary=MethodVariant.STRUCTURED_PATCH_JSON,
        goal="Discuss in prose; do not output JSON.",
        expected_reasons=["schema_invalid"],
    )
    runner = NaturalFallbackPackRunner(tmp_path, http_get=_served_get, http_post=_prose_post)
    report = runner.run(provider_id="local_openai_compatible", model_id=MODEL, base_url=BASE, cases=[case])
    item = report["modes"][0]
    assert item["mode_observed"] is True
    assert item["natural_fallback"] is True
    assert item["recovered"] is True
    assert item["selected_method"] == "review_only"
    assert item["handled"] is True
    assert report["proof_level"] == "natural_fallback_real_eval_passed"


def test_provider_unavailable_is_not_passed(tmp_path) -> None:
    case = NaturalFallbackCase(
        mode="provider_unavailable",
        primary=MethodVariant.STRUCTURED_PATCH_JSON,
        goal="Create eval_target.txt with content ok.",
        expected_reasons=["transport_error", "adapter_unavailable"],
    )
    runner = NaturalFallbackPackRunner(tmp_path, http_get=_served_get, http_post=_prose_post)
    report = runner.run(provider_id="local_openai_compatible", model_id=MODEL, base_url=BASE, cases=[case])
    item = report["modes"][0]
    assert item["final_status"] != "passed"
    assert item["mode_observed"] is True
    assert item["handled"] is True


def test_pending_when_model_not_served(tmp_path) -> None:
    def _absent_get(_url, _timeout):
        return 200, json.dumps({"object": "list", "data": [{"id": "other"}]})

    runner = NaturalFallbackPackRunner(tmp_path, http_get=_absent_get, http_post=_prose_post)
    report = runner.run(provider_id="local_openai_compatible", model_id=MODEL, base_url=BASE)
    assert report["anvil_ready"] is False
    assert report["proof_level"] == "natural_fallback_real_eval_pending"
    # Non-provider modes are skipped honestly; provider_unavailable still runs.
    fallback_modes = [m for m in report["modes"] if m["mode"] != "provider_unavailable"]
    assert all(m["skipped"] for m in fallback_modes)


def test_no_unsafe_apply_on_any_attempt(tmp_path) -> None:
    runner = NaturalFallbackPackRunner(tmp_path, http_get=_served_get, http_post=_prose_post)
    report = runner.run(provider_id="local_openai_compatible", model_id=MODEL, base_url=BASE)
    for item in report["modes"]:
        assert "safe_apply_bypass" not in item.get("observed_reasons", []) or item["final_status"] != "passed"
        # A passed terminal must be review_only (no file applied) under the prose stub.
        if item["final_status"] == "passed" and not item["skipped"]:
            assert item["selected_method"] == "review_only"
