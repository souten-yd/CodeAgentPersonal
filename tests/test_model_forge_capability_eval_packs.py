"""TFG-10 / Package 9 — Forge capability eval packs and capability scoring tests.

Proves the capability evaluation path that feeds ExecutionPolicySelector:

- packs cover the seven control-plane capability dimensions;
- mechanical case results aggregate into a dimension score, with adversarial cases
  weighted more heavily;
- ``unavailable`` is never counted as a pass and never moves the score;
- evidence refs are preserved end-to-end;
- a stored profile projects into a ModelCapabilityProfile whose weaknesses change the
  ExecutionPolicy (injection level and required gates).
"""
from __future__ import annotations

from agent.model_forge import (
    CAPABILITY_DIMENSIONS,
    CapabilityScorer,
    CaseResult,
    ChangeClass,
    EvaluatorOutcome,
    ProfileStore,
    build_capability_profile,
    derive_known_weaknesses,
    get_eval_pack,
    load_eval_packs,
    pack_for_dimension,
    score_pack,
)
from agent.model_forge.execution_policy import (
    ExecutionPolicySelector,
    ModelCapabilityProfile,
)
from agent.twin_control_plane.contracts import TwinInjectionLevel


def _result(case_id, dimension, outcome, refs=None):
    return CaseResult(case_id=case_id, dimension=dimension, outcome=outcome,
                      evidence_refs=refs or [])


def test_packs_cover_all_capability_dimensions():
    packs = load_eval_packs()
    covered = {p.dimension for p in packs}
    assert covered == set(CAPABILITY_DIMENSIONS)
    # Every case declares the same dimension as its pack.
    for pack in packs:
        assert pack.cases
        assert all(c.dimension == pack.dimension for c in pack.cases)


def test_passed_and_failed_aggregate_to_weighted_score():
    pack = get_eval_pack("contract_preservation_pack")
    # cp_safe_apply and cp_remote are adversarial (weight x2); cp_interface is plain.
    results = [
        _result("cp_interface", "contract_preservation", EvaluatorOutcome.PASSED, ["ev/a"]),
        _result("cp_safe_apply", "contract_preservation", EvaluatorOutcome.FAILED, ["ev/b"]),
        _result("cp_remote", "contract_preservation", EvaluatorOutcome.PASSED, ["ev/c"]),
    ]
    scored = score_pack(pack, results)
    # weights: interface=1 pass, safe_apply=2 fail, remote=2 pass => 3/5 = 0.6
    assert scored.score == 0.6
    assert scored.outcome == EvaluatorOutcome.FAILED  # any fail flips pack outcome
    assert scored.passed == 2 and scored.failed == 1
    assert scored.evidence_refs == ["ev/a", "ev/b", "ev/c"]


def test_unavailable_is_not_a_pass_and_does_not_move_score():
    pack = get_eval_pack("evidence_discipline_pack")
    results = [
        _result("ed_unavailable", "evidence_discipline", EvaluatorOutcome.UNAVAILABLE, ["ev/u"]),
        _result("ed_no_mock_as_live", "evidence_discipline", EvaluatorOutcome.UNAVAILABLE),
    ]
    scored = score_pack(pack, results)
    assert scored.outcome == EvaluatorOutcome.UNAVAILABLE
    assert scored.score is None
    assert scored.sample_count == 0
    assert scored.unavailable == 2
    # Evidence is still preserved even though it did not move a score.
    assert scored.evidence_refs == ["ev/u"]


def test_recording_skips_unavailable_packs(tmp_path):
    store = ProfileStore(tmp_path / "profiles")
    scorer = CapabilityScorer(store)
    pack = pack_for_dimension("evidence_discipline")
    results = [_result("ed_unavailable", "evidence_discipline", EvaluatorOutcome.UNAVAILABLE)]
    scorer.record_pack_result(model_id="m1", provider_id="local", pack=pack, results=results)
    # No evidence => no observation => no profile written.
    assert store.load_profile("local", "m1") is None


def test_eval_run_persists_scores_and_evidence(tmp_path):
    store = ProfileStore(tmp_path / "profiles")
    scorer = CapabilityScorer(store)
    results = [
        _result("fr_baseline", "flag_reasoning", EvaluatorOutcome.FAILED, ["ev/f1"]),
        _result("fr_missing", "flag_reasoning", EvaluatorOutcome.FAILED, ["ev/f2"]),
        _result("ia_direct", "impact_analysis", EvaluatorOutcome.PASSED, ["ev/i1"]),
        _result("ia_transitive", "impact_analysis", EvaluatorOutcome.PASSED, ["ev/i2"]),
        _result("ia_overreach", "impact_analysis", EvaluatorOutcome.PASSED, ["ev/i3"]),
    ]
    scorer.record_eval_run(
        model_id="m1", provider_id="local",
        packs=[pack_for_dimension("flag_reasoning"), pack_for_dimension("impact_analysis")],
        results=results,
    )
    profile = store.load_profile("local", "m1")
    assert profile.dimension_scores["flag_reasoning"] == 0.0
    assert profile.dimension_scores["impact_analysis"] == 1.0
    assert "ev/f1" in profile.evidence_refs and "ev/i3" in profile.evidence_refs


def test_known_weaknesses_only_from_evidence():
    scores = {"flag_reasoning": 0.2, "impact_analysis": 0.9}
    # contract_preservation has no evidence => must not be reported as a weakness.
    assert derive_known_weaknesses(scores) == ["flag_reasoning"]


def test_capability_profile_feeds_execution_policy(tmp_path):
    store = ProfileStore(tmp_path / "profiles")
    scorer = CapabilityScorer(store)
    # A model that fails flag reasoning hard.
    scorer.record_eval_run(
        model_id="weakflag", provider_id="local",
        packs=[pack_for_dimension("flag_reasoning")],
        results=[
            _result("fr_baseline", "flag_reasoning", EvaluatorOutcome.FAILED, ["ev/1"]),
            _result("fr_missing", "flag_reasoning", EvaluatorOutcome.FAILED, ["ev/2"]),
        ],
    )
    profile = store.load_profile("local", "weakflag")
    cap = build_capability_profile(profile)
    assert isinstance(cap, ModelCapabilityProfile)
    assert "flag_reasoning" in cap.known_weaknesses

    selector = ExecutionPolicySelector()
    weak_policy = selector.select(ChangeClass.MEDIUM, task_category="feature", model_profile=cap)
    strong_policy = selector.select(
        ChangeClass.MEDIUM, task_category="feature",
        model_profile=ModelCapabilityProfile(model_id="strong",
                                              capability_scores={"flag_reasoning": 0.9}),
    )
    # The flag-weak model picks up the feature-flag baseline gate.
    assert "FeatureFlagBaseline" in weak_policy.required_gates
    assert "FeatureFlagBaseline" not in strong_policy.required_gates


def test_missing_profile_yields_neutral_capability_profile():
    cap = build_capability_profile(None, model_id="brand_new")
    assert cap.model_id == "brand_new"
    assert cap.capability_scores == {}
    assert cap.known_weaknesses == []
    # Neutral profile must not weaken into a low injection by asserting strength.
    assert cap.score("impact_analysis") == 0.5


def test_low_capability_raises_injection_level(tmp_path):
    # Several weak dimensions should raise the injection level vs. a strong model.
    weak = ModelCapabilityProfile(
        model_id="weak",
        capability_scores={d: 0.2 for d in ("impact_analysis", "contract_preservation",
                                            "test_generation", "stale_test_judgment")},
        known_weaknesses=["impact_analysis", "contract_preservation",
                          "test_generation", "stale_test_judgment"],
    )
    strong = ModelCapabilityProfile(
        model_id="strong",
        capability_scores={d: 0.9 for d in CAPABILITY_DIMENSIONS},
    )
    selector = ExecutionPolicySelector()
    weak_policy = selector.select(ChangeClass.MEDIUM, task_category="feature", model_profile=weak)
    strong_policy = selector.select(ChangeClass.MEDIUM, task_category="feature", model_profile=strong)
    assert int(weak_policy.twin_injection_level) >= int(strong_policy.twin_injection_level)
    assert int(weak_policy.twin_injection_level) >= int(TwinInjectionLevel.CONTRACTS_AND_IMPACT)
