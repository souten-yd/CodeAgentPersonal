"""Arena assist capability: measure capability with vs without a Twin assist directive."""
from __future__ import annotations

import json

from agent.model_forge.evaluation_service import ForgeEvaluationService
from agent.model_forge.profile_store import ProfileStore


def _svc(tmp_path):
    return ForgeEvaluationService(tmp_path, ProfileStore(tmp_path / "profiles"))


def _assist_aware_post():
    """Stub model: fails the structured contract WITHOUT the assist directive, passes WITH it.
    This produces a real, measurable lift between the two passes."""
    def post(_url, payload, _headers, _timeout):
        system = payload["messages"][0]["content"]
        assisted = "Twin assist guidance" in system
        if assisted:
            content = '{"file_changes": [{"path": "eval_target.txt", "action_type": "create", "proposed_content": "ok"}]}'
        else:
            content = "Sure, I can help with that. (prose, not JSON)"
        return 200, json.dumps({"id": "stub", "choices": [{"message": {"content": content}}]})
    return post


def test_assist_lift_is_measured_per_dimension(tmp_path, monkeypatch):
    import agent.model_forge.real_method_runner as rmr
    monkeypatch.setattr(rmr, "_default_post", _assist_aware_post())
    svc = _svc(tmp_path)
    rec = svc.assist_capability_profile(
        provider_id="local", model_id="m1", base_url="http://x",
        dimensions=["structured_output_fidelity"],
    )
    assert rec["baseline_scores"]["structured_output_fidelity"] == 0.0
    assert rec["assisted_scores"]["structured_output_fidelity"] == 1.0
    assert rec["lift"]["structured_output_fidelity"] == 1.0


def test_assist_capability_persisted_and_loadable(tmp_path, monkeypatch):
    import agent.model_forge.real_method_runner as rmr
    monkeypatch.setattr(rmr, "_default_post", _assist_aware_post())
    svc = _svc(tmp_path)
    svc.assist_capability_profile(
        provider_id="local", model_id="m1", base_url="http://x",
        dimensions=["structured_output_fidelity"],
    )
    loaded = svc.load_assist_capability("local", "m1")
    assert loaded is not None
    assert loaded["assisted_scores"]["structured_output_fidelity"] == 1.0
    assert "assist_directive" in loaded


def test_unknown_dimension_rejected(tmp_path):
    import pytest
    with pytest.raises(ValueError, match="unknown_evaluation_dimension"):
        _svc(tmp_path).assist_capability_profile(
            provider_id="local", model_id="m1", base_url="http://x", dimensions=["not_a_dim"])


def test_load_missing_is_none(tmp_path):
    assert _svc(tmp_path).load_assist_capability("local", "absent") is None
