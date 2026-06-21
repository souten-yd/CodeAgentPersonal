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
    assert loaded["min_sufficient_injection_level"] == 2


def test_high_tolerance_lowers_to_minimum_level(tmp_path, monkeypatch):
    # "How far can we lower it?" — with a generous tolerance any level counts as sufficient, so the
    # minimum-sufficient level drops to the lowest swept level while the PEAK stays unchanged.
    import agent.model_forge.real_method_runner as rmr
    monkeypatch.setattr(rmr, "_default_post", _level_sensitive_post())
    rec = _svc(tmp_path).injection_sweep_profile(
        provider_id="local", model_id="m1", base_url="http://x",
        dimensions=["structured_output_fidelity"], tolerance=1.0,
    )
    assert rec["min_sufficient_injection_level"] == 0
    assert rec["recommended_injection_level"] == 2


def test_zero_tolerance_min_sufficient_equals_peak(tmp_path, monkeypatch):
    import agent.model_forge.real_method_runner as rmr
    monkeypatch.setattr(rmr, "_default_post", _level_sensitive_post())
    rec = _svc(tmp_path).injection_sweep_profile(
        provider_id="local", model_id="m1", base_url="http://x",
        dimensions=["structured_output_fidelity"], tolerance=0.0,
    )
    assert rec["min_sufficient_injection_level"] == rec["recommended_injection_level"] == 2


def test_invalid_tolerance_rejected(tmp_path):
    with pytest.raises(ValueError, match="invalid_tolerance"):
        _svc(tmp_path).injection_sweep_profile(
            provider_id="local", model_id="m1", base_url="http://x",
            dimensions=["structured_output_fidelity"], tolerance=1.5)


def test_failure_escalation_raises_injection_from_minimum():
    from agent.model_forge.execution_policy import ExecutionPolicySelector, ModelCapabilityProfile
    from agent.model_forge.route_matrix import ChangeClass
    from agent.model_forge.route_taxonomy import ForgeRoute
    from agent.twin_control_plane.contracts import ModelCapabilityMode

    # Start at the minimum sufficient injection, then raise one level per consecutive failure.
    profile = ModelCapabilityProfile(model_id="weak", mode=ModelCapabilityMode.WEAK_LOCAL,
                                     measured_optimal_injection_level=0)
    sel = ExecutionPolicySelector()
    p0 = sel.select(ChangeClass.LARGE, requested_route=ForgeRoute.TEST_FIRST, model_profile=profile)
    p1 = sel.select(ChangeClass.LARGE, requested_route=ForgeRoute.TEST_FIRST, model_profile=profile,
                    consecutive_method_failures=1)
    assert int(p0.twin_injection_level) == 2        # min sufficient -> route safety floor
    assert int(p1.twin_injection_level) == 3        # escalated +1 after a failure
    assert any(r == "failure_escalation+1" for r in p1.reasons)


def test_sweep_auto_reflected_into_profile(tmp_path, monkeypatch):
    # Running the sweep records the measured optimum onto the model profile (A: ExecutionPolicy wiring).
    import agent.model_forge.real_method_runner as rmr
    monkeypatch.setattr(rmr, "_default_post", _level_sensitive_post())
    store = ProfileStore(tmp_path / "profiles")
    svc = ForgeEvaluationService(tmp_path, store)
    svc.injection_sweep_profile(
        provider_id="local", model_id="m1", base_url="http://x",
        dimensions=["structured_output_fidelity"],
    )
    profile = store.load_profile("local", "m1")
    assert profile is not None
    assert profile.measured_optimal_injection_level == 2


def test_capability_profile_carries_injection_recommendations(tmp_path):
    from agent.model_forge.capability_scoring import build_capability_profile
    from agent.model_forge.schema import ModelProfile

    mp = ModelProfile(model_id="m1", provider_id="local",
                      recommended_twin_injection_level=4, measured_optimal_injection_level=1)
    cap = build_capability_profile(mp)
    assert cap.recommended_twin_injection_level == 4
    assert cap.measured_optimal_injection_level == 1


def test_execution_policy_caps_injection_at_measured_optimum():
    from agent.model_forge.execution_policy import ExecutionPolicySelector, ModelCapabilityProfile
    from agent.model_forge.route_matrix import ChangeClass
    from agent.model_forge.route_taxonomy import ForgeRoute
    from agent.twin_control_plane.contracts import ModelCapabilityMode

    # WEAK_LOCAL on TEST_FIRST (range 2..4) would heuristically inject 4; the sweep measured 0 as
    # optimal -> capped down to the route's safety floor (2), never below it.
    profile = ModelCapabilityProfile(model_id="weak", mode=ModelCapabilityMode.WEAK_LOCAL,
                                     measured_optimal_injection_level=0)
    policy = ExecutionPolicySelector().select(
        ChangeClass.LARGE, requested_route=ForgeRoute.TEST_FIRST, model_profile=profile)
    assert int(policy.twin_injection_level) == 2
    assert any(r == "injection_sweep_min_sufficient=0" for r in policy.reasons)


def test_max_score_objective_raises_injection_to_peak():
    from agent.model_forge.execution_policy import ExecutionPolicySelector, ModelCapabilityProfile
    from agent.model_forge.route_matrix import ChangeClass
    from agent.model_forge.route_taxonomy import ForgeRoute
    from agent.twin_control_plane.contracts import ModelCapabilityMode

    # max_score: a strong model whose heuristic base is low gets RAISED to the peak-scoring level.
    profile = ModelCapabilityProfile(model_id="strong", mode=ModelCapabilityMode.FRONTIER_ASSISTED,
                                     measured_optimal_injection_level=4, injection_objective="max_score")
    policy = ExecutionPolicySelector().select(
        ChangeClass.MICRO, requested_route=ForgeRoute.DIRECT_PATCH, model_profile=profile)
    assert int(policy.twin_injection_level) == 3   # DIRECT_PATCH range (1,3) -> clamped peak
    assert any(r == "injection_sweep_max_score=4" for r in policy.reasons)


def test_objective_switches_selected_level_in_sweep(tmp_path, monkeypatch):
    import agent.model_forge.real_method_runner as rmr
    monkeypatch.setattr(rmr, "_default_post", _level_sensitive_post())
    svc = _svc(tmp_path)
    rec_min = svc.injection_sweep_profile(
        provider_id="local", model_id="m1", base_url="http://x",
        dimensions=["structured_output_fidelity"], tolerance=1.0, objective="min_sufficient")
    rec_max = svc.injection_sweep_profile(
        provider_id="local", model_id="m2", base_url="http://x",
        dimensions=["structured_output_fidelity"], tolerance=1.0, objective="max_score")
    assert rec_min["selected_injection_level"] == 0   # lowest sufficient (generous tolerance)
    assert rec_max["selected_injection_level"] == 2   # peak

def test_invalid_objective_rejected(tmp_path):
    with pytest.raises(ValueError, match="invalid_objective"):
        _svc(tmp_path).injection_sweep_profile(
            provider_id="local", model_id="m1", base_url="http://x",
            dimensions=["structured_output_fidelity"], objective="nope")


def test_forge_service_resolves_local_base_url_default(tmp_path):
    # An already-running local model is evaluable by port: with no env/settings the resolver falls
    # back to the per-runtime default so base_url need not be supplied by the client.
    from agent.model_forge.forge_service import ForgeService
    fs = ForgeService(tmp_path, env={})
    assert fs._resolve_local_base_url("", "") == "http://127.0.0.1:8080"
    assert fs._resolve_local_base_url("", "lm_studio") == "http://127.0.0.1:1234"
    assert fs._resolve_local_base_url("http://127.0.0.1:9999", "") == "http://127.0.0.1:9999"


def test_forge_service_injection_sweep_resolves_blank_base_url(tmp_path, monkeypatch):
    from agent.model_forge.forge_service import ForgeService
    fs = ForgeService(tmp_path, env={})
    captured = {}

    def fake(**payload):
        captured.update(payload)
        return {"ok": True}

    monkeypatch.setattr(fs.evaluation, "injection_sweep_profile", fake)
    fs.injection_sweep_profile(provider_id="local_openai_compatible", model_id="m1", base_url="",
                               runtime_kind="", dimensions=["structured_output_fidelity"])
    assert captured["base_url"] == "http://127.0.0.1:8080"
    assert "runtime_kind" not in captured  # consumed by the service, not forwarded


def test_twin_assist_floor_wins_over_sweep_cap():
    from agent.model_forge.execution_policy import ExecutionPolicySelector, ModelCapabilityProfile
    from agent.model_forge.route_matrix import ChangeClass
    from agent.model_forge.route_taxonomy import ForgeRoute
    from agent.twin_control_plane.contracts import ModelCapabilityMode

    # Same model, but twin-assist measured a NEED for level 4: the floor wins over the sweep cap.
    profile = ModelCapabilityProfile(model_id="weak", mode=ModelCapabilityMode.WEAK_LOCAL,
                                     measured_optimal_injection_level=0,
                                     recommended_twin_injection_level=4)
    policy = ExecutionPolicySelector().select(
        ChangeClass.LARGE, requested_route=ForgeRoute.TEST_FIRST, model_profile=profile)
    assert int(policy.twin_injection_level) == 4
    assert any(r == "twin_assist_injection_floor=4" for r in policy.reasons)


def test_invalid_level_rejected(tmp_path):
    with pytest.raises(ValueError, match="invalid_injection_level"):
        _svc(tmp_path).injection_sweep_profile(
            provider_id="local", model_id="m1", base_url="http://x",
            dimensions=["structured_output_fidelity"], levels=[0, 9])


def test_unknown_dimension_rejected(tmp_path):
    with pytest.raises(ValueError, match="unknown_evaluation_dimension"):
        _svc(tmp_path).injection_sweep_profile(
            provider_id="local", model_id="m1", base_url="http://x", dimensions=["nope"])
