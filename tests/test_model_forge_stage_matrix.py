"""PFG-17 — Stage Matrix policy and selector tests.

Proves: defaults are disabled/shadow (no live routing), an active production-routing
mode cannot be set without explicit acknowledgement (no automatic cutover), and every
selection records its reasons.
"""
from __future__ import annotations

import pytest

from agent.model_forge import (
    ProfileStore,
    StageCandidate,
    StageMatrix,
    StageSelector,
)
from agent.model_forge.stage_taxonomy import ForgeStage, StageMode


def test_defaults_are_disabled_or_shadow_no_live_routing():
    m = StageMatrix()
    for entry in m.matrix():
        assert entry.mode in (StageMode.DISABLED, StageMode.SHADOW_SELECT)
    # PATCH_GENERATION defaults to shadow; CONTEXT_SELECTION defaults to disabled.
    assert m.get_entry(ForgeStage.PATCH_GENERATION).mode == StageMode.SHADOW_SELECT
    assert m.get_entry(ForgeStage.CONTEXT_SELECTION).mode == StageMode.DISABLED


def test_active_mode_requires_explicit_acknowledgement():
    m = StageMatrix()
    for mode in (StageMode.AUTO_SELECT, StageMode.FIXED_MODEL, StageMode.ARENA_SELECT):
        with pytest.raises(PermissionError):
            m.set_policy(ForgeStage.PATCH_GENERATION, mode)
    # Acknowledged cutover is allowed.
    entry = m.set_policy(ForgeStage.PATCH_GENERATION, StageMode.AUTO_SELECT,
                         allow_production_routing=True, reason="evidence_backed")
    assert entry.mode == StageMode.AUTO_SELECT


def test_shadow_select_does_not_change_production_routing(tmp_path):
    profiles = ProfileStore(tmp_path / "profiles")
    profiles.record_observation(model_id="big", provider_id="local",
                                dimensions={"patch_generation": 0.9})
    profiles.record_observation(model_id="small", provider_id="local",
                                dimensions={"patch_generation": 0.3})
    m = StageMatrix()  # PATCH_GENERATION default == shadow
    sel = StageSelector(m, profile_store=profiles).select(
        ForgeStage.PATCH_GENERATION,
        candidates=[StageCandidate(provider_id="local", model_id="small"),
                    StageCandidate(provider_id="local", model_id="big")],
    )
    # Best-by-profile candidate chosen, but legacy stays primary in shadow.
    assert sel.selected_model_id == "big"
    assert sel.changes_production_routing is False
    assert sel.legacy_remains_primary is True
    assert "shadow_select" in sel.reasons and "legacy_primary" in sel.reasons


def test_disabled_stage_selects_nothing_with_reason():
    m = StageMatrix()
    sel = StageSelector(m).select(
        ForgeStage.CONTEXT_SELECTION,
        candidates=[StageCandidate(provider_id="local", model_id="m1")],
    )
    assert sel.selected_model_id == ""
    assert sel.changes_production_routing is False
    assert "stage_disabled" in sel.reasons


def test_auto_select_changes_routing_only_after_ack(tmp_path):
    m = StageMatrix(tmp_path / "stage_policy.json")
    m.set_policy(ForgeStage.REPAIR, StageMode.AUTO_SELECT, allow_production_routing=True)
    sel = StageSelector(m).select(
        ForgeStage.REPAIR, candidates=[StageCandidate(provider_id="local", model_id="m1")],
    )
    assert sel.selected_model_id == "m1"
    assert sel.changes_production_routing is True
    assert sel.legacy_remains_primary is False
    assert "auto_select" in sel.reasons
    # Policy persisted across instances.
    assert StageMatrix(tmp_path / "stage_policy.json").get_entry(ForgeStage.REPAIR).mode == StageMode.AUTO_SELECT


def test_arena_select_requires_safe_apply():
    m = StageMatrix()
    m.set_policy(ForgeStage.PATCH_GENERATION, StageMode.ARENA_SELECT,
                 allow_production_routing=True)
    sel = StageSelector(m).select(
        ForgeStage.PATCH_GENERATION,
        candidates=[StageCandidate(provider_id="local", model_id="m1")],
    )
    # Arena never auto-applies; routing stays with legacy until Safe Apply.
    assert sel.changes_production_routing is False
    assert "candidate_requires_safe_apply" in sel.reasons
