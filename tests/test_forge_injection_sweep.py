"""Benchmark capability across varying Twin injection levels -> optimal injection amount."""
from __future__ import annotations

import json

import pytest

from agent.model_forge.evaluation_service import ForgeEvaluationService
from agent.model_forge.profile_store import ProfileStore


def _svc(tmp_path):
    return ForgeEvaluationService(tmp_path, ProfileStore(tmp_path / "profiles"))


def _level_sensitive_post():
    """Stub: passes the structured contract only once the directive includes the level-2
    'contracts+impact' guidance — so levels 0/1 fail and levels 2..4 pass."""
    def post(_url, payload, _headers, _timeout):
        system = payload["messages"][0]["content"]
        strong = "contracts+impact" in system or "constrained+tests" in system or "strict interface" in system
        if strong:
            content = '{"file_changes": [{"path": "eval_target.txt", "action_type": "create", "proposed_content": "ok"}]}'
        else:
            content = "Sure! (prose, not JSON)"
        return 200, json.dumps({"id": "stub", "choices": [{"message": {"content": content}}]})
    return post


def test_injection_sweep_finds_optimal_level(tmp_path, monkeypatch):
    import agent.model_forge.real_method_runner as rmr
    monkeypatch.setattr(rmr, "_default_post", _level_sensitive_post())
    svc = _svc(tmp_path)
    rec = svc.injection_sweep_profile(
        provider_id="local", model_id="m1", base_url="http://x",
        dimensions=["structured_output_fidelity"],
    )
    by_level = rec["scores_by_level"]
    assert by_level["0"]["structured_output_fidelity"] == 0.0
    assert by_level["1"]["structured_output_fidelity"] == 0.0
    assert by_level["2"]["structured_output_fidelity"] == 1.0
    assert by_level["4"]["structured_output_fidelity"] == 1.0
    # Optimal level is the LOWEST that reaches the best score (tie -> least injection).
    assert rec["per_dimension_optimal"]["structured_output_fidelity"] == 2
    assert rec["recommended_injection_level"] == 2


def test_injection_sweep_persisted_and_loadable(tmp_path, monkeypatch):
    import agent.model_forge.real_method_runner as rmr
    monkeypatch.setattr(rmr, "_default_post", _level_sensitive_post())
    svc = _svc(tmp_path)
    svc.injection_sweep_profile(
        provider_id="local", model_id="m1", base_url="http://x",
        dimensions=["structured_output_fidelity"], levels=[0, 2],
    )
    loaded = svc.load_injection_sweep("local", "m1")
    assert loaded is not None
    assert loaded["levels"] == [0, 2]
    assert loaded["recommended_injection_level"] == 2


def test_invalid_level_rejected(tmp_path):
    with pytest.raises(ValueError, match="invalid_injection_level"):
        _svc(tmp_path).injection_sweep_profile(
            provider_id="local", model_id="m1", base_url="http://x",
            dimensions=["structured_output_fidelity"], levels=[0, 9])


def test_unknown_dimension_rejected(tmp_path):
    with pytest.raises(ValueError, match="unknown_evaluation_dimension"):
        _svc(tmp_path).injection_sweep_profile(
            provider_id="local", model_id="m1", base_url="http://x", dimensions=["nope"])
