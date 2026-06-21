"""PR20: Gated activation of Forge method policy (shadow -> explicit active)."""
from __future__ import annotations

import json

import pytest

from agent.model_forge.method_activation import MethodActivationGate
from agent.model_forge.stage_taxonomy import ForgeStage

STAGE = ForgeStage.PATCH_GENERATION


def _write_shadow(shadow_dir, n, *, method="edit_intent_list", unavailable=False, production=False, start=0):
    stage_dir = shadow_dir / STAGE.value
    stage_dir.mkdir(parents=True, exist_ok=True)
    for i in range(start, start + n):
        (stage_dir / f"req_{i}.json").write_text(json.dumps({
            "request_id": f"req_{i}",
            "stage": STAGE.value,
            "method_variant": method,
            "unavailable_reasons": ["model_evaluation_profile:unavailable"] if unavailable else [],
            "changes_production_routing": production,
        }), encoding="utf-8")


def _gate(tmp_path):
    return MethodActivationGate(tmp_path / "shadow", tmp_path / "activation", min_samples=3)


def test_not_ready_with_too_few_samples(tmp_path):
    _write_shadow(tmp_path / "shadow", 2)
    readiness = _gate(tmp_path).evaluate_readiness(STAGE)
    assert readiness.ready is False
    assert any("insufficient_shadow_samples" in r for r in readiness.reasons)


def test_not_ready_when_method_unstable(tmp_path):
    sd = tmp_path / "shadow"
    _write_shadow(sd, 2, method="edit_intent_list", start=0)
    _write_shadow(sd, 2, method="anchored_edit_block", start=2)
    readiness = _gate(tmp_path).evaluate_readiness(STAGE)
    assert readiness.ready is False
    assert "method_recommendation_not_stable" in readiness.reasons


def test_not_ready_without_evidence(tmp_path):
    _write_shadow(tmp_path / "shadow", 4, unavailable=True)
    readiness = _gate(tmp_path).evaluate_readiness(STAGE)
    assert readiness.ready is False
    assert "no_model_evaluation_evidence" in readiness.reasons


def test_ready_with_stable_evidenced_shadow(tmp_path):
    _write_shadow(tmp_path / "shadow", 4, method="edit_intent_list")
    readiness = _gate(tmp_path).evaluate_readiness(STAGE)
    assert readiness.ready is True
    assert readiness.stable_method == "edit_intent_list"
    assert readiness.reasons == []


def test_activate_requires_acknowledge(tmp_path):
    _write_shadow(tmp_path / "shadow", 4)
    with pytest.raises(PermissionError):
        _gate(tmp_path).activate(STAGE)


def test_activate_blocked_when_not_ready(tmp_path):
    _write_shadow(tmp_path / "shadow", 2)
    with pytest.raises(ValueError, match="method_activation_not_ready"):
        _gate(tmp_path).activate(STAGE, acknowledge=True)


def test_activate_then_deactivate(tmp_path):
    _write_shadow(tmp_path / "shadow", 4, method="edit_intent_list")
    gate = _gate(tmp_path)
    record = gate.activate(STAGE, acknowledge=True)
    assert record.status == "active"
    assert record.active_method_enabled is True
    assert record.active_auto_enabled is False  # invariant
    assert record.stable_method == "edit_intent_list"
    assert record.proof_requirements
    assert gate.is_active(STAGE) is True

    # Recovery needs no acknowledgement.
    reverted = gate.deactivate(STAGE)
    assert reverted.status == "shadow"
    assert reverted.active_method_enabled is False
    assert gate.is_active(STAGE) is False


def test_automation_never_enabled(tmp_path):
    _write_shadow(tmp_path / "shadow", 5, method="edit_intent_list")
    gate = _gate(tmp_path)
    record = gate.activate(STAGE, acknowledge=True)
    assert record.active_auto_enabled is False
    for rec in gate.list_activations():
        assert rec.active_auto_enabled is False


def test_non_shadow_record_blocks_activation(tmp_path):
    _write_shadow(tmp_path / "shadow", 4, method="edit_intent_list", production=True)
    readiness = _gate(tmp_path).evaluate_readiness(STAGE)
    assert readiness.ready is False
    assert "non_shadow_record_present" in readiness.reasons
