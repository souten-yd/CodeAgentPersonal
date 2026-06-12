"""PFG-16 — Model Profile Store and profile updater tests.

Proves: updates are append-only AND versioned, raw evidence is preserved, scores can
be recomputed from the observation log, and user feedback is weak (never moves the
score on its own).
"""
from __future__ import annotations

from agent.model_forge import (
    CandidateScore,
    ProfileStore,
    VERDICT_ELIGIBLE,
    VERDICT_REJECTED,
)


def _store(tmp_path):
    return ProfileStore(tmp_path / "profiles")


def test_updates_are_versioned_and_append_only(tmp_path):
    s = _store(tmp_path)
    s.record_observation(model_id="m1", provider_id="local",
                         dimensions={"patch_generation": 0.8}, evidence_refs=["ev1"])
    s.record_observation(model_id="m1", provider_id="local",
                         dimensions={"patch_generation": 0.6}, evidence_refs=["ev2"])
    assert s.list_versions("local", "m1") == [1, 2]
    v1 = s.load_profile_version("local", "m1", 1)
    v2 = s.load_profile_version("local", "m1", 2)
    # v1 is never rewritten when v2 lands.
    assert v1.dimension_scores["patch_generation"] == 0.8
    assert v2.dimension_scores["patch_generation"] == 0.7  # mean of 0.8, 0.6
    assert v2.sample_count == 2
    assert s.load_profile("local", "m1").version == 2


def test_raw_evidence_preserved_and_scores_recomputable(tmp_path):
    s = _store(tmp_path)
    s.record_observation(model_id="m1", provider_id="local",
                         dimensions={"repair": 1.0}, evidence_refs=["arena/run1"])
    s.record_observation(model_id="m1", provider_id="local",
                         dimensions={"repair": 0.0}, evidence_refs=["arena/run2"])
    obs = s.load_observations("local", "m1")
    assert [o.evidence_refs[0] for o in obs] == ["arena/run1", "arena/run2"]
    # Recompute from the log independently of the persisted version.
    recomputed = s.recompute_profile("local", "m1")
    assert recomputed.dimension_scores["repair"] == 0.5
    assert set(recomputed.evidence_refs) == {"arena/run1", "arena/run2"}


def test_user_feedback_is_weak_and_does_not_move_score(tmp_path):
    s = _store(tmp_path)
    s.record_observation(model_id="m1", provider_id="local",
                         dimensions={"web_app": 0.9}, evidence_refs=["portal/run1"])
    before = s.load_profile("local", "m1").dimension_scores["web_app"]
    # A discard decision is recorded as weak feedback but must not change the score.
    prof = s.record_user_feedback(model_id="m1", provider_id="local",
                                  decision="discard", dimensions={"web_app": 0.0},
                                  evidence_refs=["portal/discard1"])
    assert prof.dimension_scores["web_app"] == before == 0.9
    # The weak observation is still preserved as evidence.
    weak = [o for o in s.load_observations("local", "m1") if o.weak_feedback]
    assert len(weak) == 1 and weak[0].source == "user_decision:discard"
    assert "portal/discard1" in prof.evidence_refs


def test_update_from_candidate_score(tmp_path):
    s = _store(tmp_path)
    eligible = CandidateScore(candidate_id="c1", final_score=0.75, verdict=VERDICT_ELIGIBLE)
    prof = s.update_from_candidate_score(
        eligible, model_id="m1", provider_id="local",
        dimensions=["patch_generation", "overall"],
    )
    assert prof.dimension_scores["patch_generation"] == 0.75
    assert prof.dimension_scores["overall"] == 0.75
    assert "candidate:c1" in prof.evidence_refs

    rejected = CandidateScore(candidate_id="c2", final_score=0.9, verdict=VERDICT_REJECTED,
                              blocked_reasons=["contract_parse"])
    prof2 = s.update_from_candidate_score(
        rejected, model_id="m1", provider_id="local", dimensions=["patch_generation"],
    )
    # Rejected candidate contributes 0.0 regardless of its (ignored) final_score.
    assert prof2.dimension_scores["patch_generation"] == 0.375  # mean of 0.75, 0.0


def test_profiles_are_isolated_per_model(tmp_path):
    s = _store(tmp_path)
    s.record_observation(model_id="m1", provider_id="local", dimensions={"overall": 1.0})
    s.record_observation(model_id="m2", provider_id="local", dimensions={"overall": 0.2})
    assert s.load_profile("local", "m1").dimension_scores["overall"] == 1.0
    assert s.load_profile("local", "m2").dimension_scores["overall"] == 0.2
    keys = {p.model_id for p in s.list_profiles()}
    assert keys == {"m1", "m2"}
