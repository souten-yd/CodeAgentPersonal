"""PFG-37 — legacy retirement gates and consumer registry.

The registry records the real production modules that still call the legacy
model-execution path; the retirement gate refuses deletion until the legacy path is
consumer-zero AND benchmark/shadow/rollback gates pass. No legacy path is deleted here.
"""
from __future__ import annotations

from pathlib import Path

from agent.model_forge import (
    LegacyModelConsumerRegistry,
    build_model_consumer_registry,
    evaluate_model_retirement_gate,
    scan_legacy_model_consumers,
)

ROOT = Path(__file__).resolve().parent.parent


def test_registry_records_real_legacy_consumers():
    consumers = scan_legacy_model_consumers(ROOT)
    # There ARE real direct legacy callers today (the legacy path must not be deleted).
    assert len(consumers) > 0
    # The legacy owner and the Forge wrapper are not counted as consumers.
    assert "agent/atlas_llm_json_adapter.py" not in consumers
    assert "agent/model_forge/providers/legacy_atlas.py" not in consumers
    # Known production callers are present.
    assert "app/api/atlas_pipeline.py" in consumers


def test_retirement_gate_blocks_while_consumers_remain():
    registry = build_model_consumer_registry(ROOT)
    assert registry.legacy_consumer_count > 0
    gate = evaluate_model_retirement_gate(
        registry, benchmark_passed=True, shadow_passed=True, rollback_available=True,
    )
    # Even with every other gate green, a non-zero consumer count blocks retirement.
    assert gate.allowed is False
    assert gate.checklist["consumer_zero"] is False
    assert "gate_failed:consumer_zero" in gate.blocked_reasons


def test_retirement_allowed_only_when_consumer_zero_and_gates_pass():
    zero = LegacyModelConsumerRegistry(consumers=[], legacy_consumer_count=0)
    # Consumer-zero but a failing benchmark still blocks.
    blocked = evaluate_model_retirement_gate(
        zero, benchmark_passed=False, shadow_passed=True, rollback_available=True)
    assert blocked.allowed is False
    assert "gate_failed:benchmark_passed" in blocked.blocked_reasons
    # Consumer-zero AND all gates pass -> retirement allowed.
    allowed = evaluate_model_retirement_gate(
        zero, benchmark_passed=True, shadow_passed=True, rollback_available=True)
    assert allowed.allowed is True
    assert allowed.blocked_reasons == []
    assert all(allowed.checklist.values())
