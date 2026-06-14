"""Focused unit tests for the research-agent retrieval/recursive DECISION helpers.

These cover the pure phase logic (retrieval targets, download budget reservation, expansion/deficit
decisions, recursive stop) directly — robustly and without the brittle full-flow mocks that made the
end-to-end recursive tests fragile. This is the testable foundation the run_research_job split builds on.
"""

from __future__ import annotations

from app.nexus.research_agent import (
    ResearchAgentInput,
    _should_stop_recursive_research,
    build_retrieval_targets,
    compute_recursive_download_budget,
    compute_retrieval_deficit,
    should_auto_expand_download_budget,
    should_expand_retrieval,
)


def _payload(**kw) -> ResearchAgentInput:
    return ResearchAgentInput(query="q", **kw)


def test_build_retrieval_targets_defaults_overrides_and_flags():
    deep = build_retrieval_targets(_payload(mode="deep"))
    assert deep["max_retrieval_rounds"] == 4
    assert deep["target_valid_source_count"] == 60
    # explicit payload value overrides the depth default
    assert build_retrieval_targets(_payload(mode="deep", target_valid_source_count=3))["target_valid_source_count"] == 3
    # replenishment flag propagates onto the targets
    assert build_retrieval_targets(_payload(replenishment_enabled=False))["replenishment_enabled"] is False
    # unknown depth collapses to standard defaults
    assert build_retrieval_targets(_payload(mode="bogus"))["max_retrieval_rounds"] == 2


def test_compute_recursive_download_budget_reserves_for_deep_only():
    deep = compute_recursive_download_budget("deep", 40)
    assert deep["recursive_reserved_downloads"] >= 20
    assert deep["initial_download_limit"] == 40 - deep["recursive_reserved_downloads"]
    std = compute_recursive_download_budget("standard", 12)
    assert std == {"initial_download_limit": 12, "recursive_reserved_downloads": 0}


def test_should_expand_retrieval_gated_by_rounds_and_targets():
    targets = {"max_retrieval_rounds": 3, "target_valid_source_count": 10, "target_evidence_count": 20}
    expand, reasons = should_expand_retrieval({"valid_source_count": 2, "evidence_count": 1}, targets, round_index=0)
    assert expand is True
    assert "valid_sources_below_target" in reasons and "evidence_below_target" in reasons
    # round budget exhausted -> never expand
    assert should_expand_retrieval({"valid_source_count": 0}, targets, round_index=3) == (False, [])
    # targets satisfied -> no expansion
    assert should_expand_retrieval({"valid_source_count": 10, "evidence_count": 20}, targets, round_index=0) == (False, [])


def test_compute_retrieval_deficit_flags_replacement_when_below_target():
    targets = {"target_valid_source_count": 10, "target_evidence_count": 20, "target_replacement_ratio": 1.0, "max_replenishment_candidates": 40}
    deficit = compute_retrieval_deficit({"valid_source_count": 2, "evidence_count": 3, "failed_candidate_count": 1}, targets)
    assert deficit["valid_source_deficit"] == 8
    assert deficit["evidence_deficit"] == 17
    assert deficit["replacement_needed"] is True
    # targets met -> no replacement needed
    assert compute_retrieval_deficit({"valid_source_count": 10, "evidence_count": 20}, targets)["replacement_needed"] is False


def test_should_auto_expand_download_budget_requires_skips_and_shortfall():
    targets = {"target_valid_source_count": 10, "target_evidence_count": 20}
    assert should_auto_expand_download_budget({"skipped_due_to_download_limit_count": 3, "valid_source_count": 1, "evidence_count": 1}, targets) is True
    # nothing was skipped due to the limit -> never auto-expand
    assert should_auto_expand_download_budget({"skipped_due_to_download_limit_count": 0, "valid_source_count": 0}, targets) is False


def test_should_stop_recursive_research_decisions():
    # confidence at/above threshold (and stop_when_sufficient) -> stop
    assert _should_stop_recursive_research(analysis={"confidence": 0.9}, iteration=1, payload=_payload(confidence_threshold=0.75)) == (True, "confidence_threshold_reached")
    # explicit sufficiency flag -> stop
    assert _should_stop_recursive_research(analysis={"confidence": 0.1, "sufficient": True}, iteration=1, payload=_payload()) == (True, "sufficient_evidence")
    # below threshold and not sufficient -> continue
    assert _should_stop_recursive_research(analysis={"confidence": 0.1, "sufficient": False}, iteration=1, payload=_payload(confidence_threshold=0.75)) == (False, "continue")
    # stop_when_sufficient disabled -> never stop on confidence
    assert _should_stop_recursive_research(analysis={"confidence": 0.99}, iteration=1, payload=_payload(stop_when_sufficient=False)) == (False, "continue")
