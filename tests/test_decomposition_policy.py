"""Model-capability-driven file-decomposition policy.

Genuine tests: each tier has a should-pick and a should-NOT-pick branch, so a regression that
collapses the policy to one tier (making it model-agnostic again) breaks a test.
"""
from __future__ import annotations

from agent.model_forge.decomposition_policy import (
    DecompositionPolicy,
    derive_decomposition_policy,
    render_decomposition_directive,
)


def test_small_local_model_splits_aggressively():
    p = derive_decomposition_policy(model_id="Mistral-Small-3.2-24B-Instruct-2506-Q3_K_S.gguf")
    assert p.tier == "weak"
    assert p.prefer_split is True
    assert p.max_file_lines <= 250


def test_frontier_model_keeps_large_files():
    p = derive_decomposition_policy(model_id="claude-opus-4-8")
    assert p.tier == "frontier"
    assert p.prefer_split is False
    assert p.max_file_lines >= 1000


def test_long_context_window_implies_frontier():
    p = derive_decomposition_policy(model_id="some-unknown-model", context_window=200_000)
    assert p.tier == "frontier"


def test_unknown_model_defaults_to_balanced_standard():
    p = derive_decomposition_policy(model_id="")
    assert p.tier == "standard"
    assert p.prefer_split is True
    assert 250 <= p.max_file_lines <= 500


def test_strong_capability_scores_lift_to_frontier():
    strong = {"contract_preservation": 0.9, "impact_analysis": 0.88, "repair_discipline": 0.85,
              "test_generation": 0.82}
    p = derive_decomposition_policy(capability_scores=strong, model_id="house-model")
    assert p.tier == "frontier"


def test_core_capability_weakness_keeps_out_of_frontier():
    # Even a frontier-sounding name must not get the large-file budget when a core edit dimension is
    # a known weakness — that is exactly the model that mangles large files.
    p = derive_decomposition_policy(
        model_id="gpt-4o-mini",
        capability_scores={"contract_preservation": 0.2},
        known_weaknesses=["contract_preservation"],
    )
    assert p.tier != "frontier"
    assert p.prefer_split is True


def test_weak_capability_scores_force_split_even_for_neutral_name():
    p = derive_decomposition_policy(
        model_id="house-model",
        capability_scores={"contract_preservation": 0.3, "impact_analysis": 0.35},
    )
    assert p.tier == "weak"


def test_measured_large_file_score_drives_tier_over_name():
    # A measured large_file_editing score wins over the model-name heuristic (Part B).
    # Frontier name + LOW measured score -> weak (the measurement is believed).
    p = derive_decomposition_policy(
        model_id="claude-opus-4-8", capability_scores={"large_file_editing": 0.25})
    assert p.tier == "weak"
    assert "measured large_file_editing" in p.rationale

    # Small name + HIGH measured score -> frontier.
    p2 = derive_decomposition_policy(
        model_id="tiny-7b", capability_scores={"large_file_editing": 0.85})
    assert p2.tier == "frontier"


def test_measured_middling_score_is_standard():
    p = derive_decomposition_policy(
        model_id="house-model", capability_scores={"large_file_editing": 0.55})
    assert p.tier == "standard"


def test_measured_high_but_core_weakness_not_frontier():
    p = derive_decomposition_policy(
        model_id="house-model",
        capability_scores={"large_file_editing": 0.9, "contract_preservation": 0.2},
        known_weaknesses=["contract_preservation"])
    assert p.tier == "weak"


def test_directive_reflects_split_preference():
    weak = derive_decomposition_policy(model_id="tinyllama-1.5b")
    text = render_decomposition_directive(weak)
    assert "DECOMPOSITION BUDGET" in text
    assert "split" in text.lower()
    assert str(weak.max_file_lines) in text

    frontier = derive_decomposition_policy(model_id="claude-sonnet-4-6")
    ftext = render_decomposition_directive(frontier)
    assert "single self-contained file is acceptable" in ftext


def test_policy_to_dict_roundtrips_fields():
    p = DecompositionPolicy(tier="standard", max_file_lines=350, prefer_split=True,
                            max_source_files=5, rationale="x")
    d = p.to_dict()
    assert d["tier"] == "standard" and d["max_file_lines"] == 350 and d["prefer_split"] is True
