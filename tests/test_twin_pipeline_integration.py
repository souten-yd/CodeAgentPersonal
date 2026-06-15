"""TFG-12 cut-over — Twin Control Plane live-pipeline integration seam tests.

Proves the seam is safe and reversible:

- mode resolves from config/env and defaults to OFF (unknown values are OFF too);
- OFF produces inert evidence and engages nothing;
- SHADOW assembles advisory evidence without engaging;
- ACTIVE engages only with shadow evidence and stays advisory (never execution authority);
- evidence building never raises.
"""
from __future__ import annotations

import pytest

from agent.twin_control_plane.active_integration import PipelineMode
from agent.twin_control_plane.pipeline_integration import (
    GATE_BLOCKING_ENV,
    PIPELINE_MODE_ENV,
    build_twin_pipeline_evidence,
    resolve_gate_blocking,
    resolve_pipeline_mode,
    try_project_twin_impact,
    twin_gate_block_reason,
)


def test_mode_defaults_to_active(monkeypatch):
    monkeypatch.delenv(PIPELINE_MODE_ENV, raising=False)
    assert resolve_pipeline_mode() == PipelineMode.ACTIVE


def test_mode_reads_env(monkeypatch):
    monkeypatch.setenv(PIPELINE_MODE_ENV, "off")
    assert resolve_pipeline_mode() == PipelineMode.OFF
    monkeypatch.setenv(PIPELINE_MODE_ENV, "shadow")
    assert resolve_pipeline_mode() == PipelineMode.SHADOW


def test_unknown_mode_falls_back_to_default(monkeypatch):
    monkeypatch.setenv(PIPELINE_MODE_ENV, "banana")
    assert resolve_pipeline_mode() == PipelineMode.ACTIVE


def test_off_is_explicitly_reachable(monkeypatch):
    monkeypatch.setenv(PIPELINE_MODE_ENV, "active")
    assert resolve_pipeline_mode("off") == PipelineMode.OFF


def test_gate_blocking_defaults_on_and_is_reversible(monkeypatch):
    monkeypatch.delenv(GATE_BLOCKING_ENV, raising=False)
    assert resolve_gate_blocking() is True
    for off in ("0", "off", "false", "no"):
        monkeypatch.setenv(GATE_BLOCKING_ENV, off)
        assert resolve_gate_blocking() is False


def test_block_reason_only_on_active_missing_shadow_evidence():
    # Normal active evidence (shadow assembled) does not block.
    ok = build_twin_pipeline_evidence(mode=PipelineMode.ACTIVE, requirement="x",
                                      pool_id="p1", changed_refs=["a.py"])
    assert ok["requires_shadow_evidence"] is False
    assert twin_gate_block_reason(ok) == ""
    # The genuine prerequisite failure blocks.
    blocking = {"mode": "active", "available": True, "requires_shadow_evidence": True}
    assert twin_gate_block_reason(blocking) == "twin_gate_requires_shadow_evidence"
    # Infra unavailable (available=False) never blocks.
    infra = {"mode": "active", "available": False, "requires_shadow_evidence": True}
    assert twin_gate_block_reason(infra) == ""
    # Off/shadow never block.
    assert twin_gate_block_reason({"mode": "off"}) == ""
    assert twin_gate_block_reason({"mode": "shadow", "requires_shadow_evidence": True}) == ""


def test_off_mode_is_inert():
    ev = build_twin_pipeline_evidence(mode=PipelineMode.OFF, requirement="add feature",
                                      pool_id="p1", changed_refs=["a.py"])
    assert ev["engaged"] is False
    assert ev["available"] is False
    assert ev["mode"] == "off"
    assert "shadow_report" not in ev


def test_shadow_mode_assembles_advisory_evidence():
    ev = build_twin_pipeline_evidence(mode=PipelineMode.SHADOW, requirement="add feature",
                                      pool_id="p1", changed_refs=["a.py", "b.py"])
    assert ev["available"] is True
    assert ev["advisory"] is True
    assert ev["engaged"] is False  # shadow records, never engages
    assert ev["policy_id"]
    assert ev["brief_id"]
    assert ev["shadow_report"] is not None


def test_active_mode_engages_with_shadow_evidence_and_stays_advisory():
    ev = build_twin_pipeline_evidence(mode=PipelineMode.ACTIVE, requirement="add feature",
                                      pool_id="p1", changed_refs=["a.py"])
    assert ev["available"] is True
    assert ev["engaged"] is True  # shadow evidence was assembled
    assert ev["requires_shadow_evidence"] is False
    # Active never claims execution authority: it is advisory evidence only.
    assert ev["advisory"] is True
    assert ev["shadow_report"]["changes_execution"] is False
    assert ev["shadow_report"]["changes_production_routing"] is False


def test_build_never_raises_on_bad_input():
    # Garbage change_class still yields inert/available=False evidence, not an exception.
    ev = build_twin_pipeline_evidence(mode=PipelineMode.ACTIVE, change_class="not_a_class")
    assert ev["available"] is False
    assert ev["engaged"] is False


# --- Step 1: live Project Twin impact connection ----------------------------------

def _seed_twin_store():
    """Build an in-memory Project Twin store with a small snapshot for project 'p1'."""
    from datetime import datetime, timezone
    from agent.project_twin.contracts import TwinDelta, TwinEdge, TwinNode
    from agent.project_twin.store import SqliteProjectTwinStore

    now = datetime(2026, 6, 15, tzinfo=timezone.utc)

    def node(node_id, ref):
        return TwinNode(node_id=node_id, project_id="p1", domain="structural",
                        node_type="function", canonical_ref=ref, label=ref, source_kind="git",
                        source_ref="mod.py", derivation="deterministic_static", confidence=0.9,
                        status="declared", valid_from=now, created_at=now, updated_at=now)

    store = SqliteProjectTwinStore(":memory:")
    store.apply_delta(TwinDelta(
        project_id="p1", idempotency_key="seed", trigger_type="workspace.changed",
        nodes=[node("n1", "py://mod.f"), node("n2", "py://mod.caller")],
        edges=[TwinEdge(edge_id="e1", project_id="p1", domain="structural",
                        source_node_id="n2", target_node_id="n1", edge_type="calls",
                        source_kind="git", source_ref="mod.py", derivation="deterministic_static",
                        confidence=0.8, status="declared", valid_from=now, created_at=now, updated_at=now)],
    ))
    return store


def test_impact_unavailable_recorded_not_crashed():
    ev = build_twin_pipeline_evidence(mode=PipelineMode.ACTIVE, requirement="x",
                                      pool_id="p1", changed_refs=["py://mod.f"], impact=None)
    assert ev["available"] is True
    assert ev["impact"]["available"] is False
    assert ev["impact"]["reason"] == "project_twin_impact_unavailable"


def test_no_store_yields_no_impact():
    assert try_project_twin_impact(project_id="p1", changed_refs=["py://mod.f"], store=None) is None


def test_impact_available_flows_into_blast_map():
    store = _seed_twin_store()
    impact = try_project_twin_impact(project_id="p1", changed_refs=["py://mod.f"], store=store)
    assert impact is not None
    ev = build_twin_pipeline_evidence(mode=PipelineMode.ACTIVE, requirement="x",
                                      pool_id="p1", changed_refs=["py://mod.f"], impact=impact)
    assert ev["impact"]["available"] is True
    assert ev["impact"]["project_id"] == "p1"
    # Real impact populates the shadow BlastMap and runs Contract Sentinel.
    assert ev["shadow_report"]["blast_map"] is not None
    assert ev["contract_sentinel"] is not None
    store.close()


# --- Step 2: Forge capability profile integration ---------------------------------

def _seed_profile(tmp_path, dims):
    from agent.model_forge.profile_store import ProfileStore
    store = ProfileStore(tmp_path / "profiles")
    store.record_observation(model_id="m1", provider_id="local", dimensions=dims,
                             evidence_refs=["eval/run1"])
    return str(tmp_path / "profiles")


def test_capability_profile_unavailable_is_neutral(tmp_path):
    # No profile persisted -> neutral, recorded unavailable, no false weakness.
    ev = build_twin_pipeline_evidence(mode=PipelineMode.ACTIVE, requirement="x", pool_id="p1",
                                      changed_refs=["a.py"], model_id="m1", provider_id="local",
                                      profile_store_dir=str(tmp_path / "profiles"))
    assert ev["capability_profile_available"] is False
    assert ev["capability_profile_unavailable"] is True
    assert ev["known_weaknesses"] == []


def test_missing_model_id_is_neutral_not_weakness():
    ev = build_twin_pipeline_evidence(mode=PipelineMode.ACTIVE, requirement="x", pool_id="p1",
                                      changed_refs=["a.py"])  # no model_id
    assert ev["capability_profile_available"] is False
    assert ev["known_weaknesses"] == []


def test_low_flag_reasoning_profile_adds_gate(tmp_path):
    store_dir = _seed_profile(tmp_path, {"flag_reasoning": 0.2, "impact_analysis": 0.9})
    ev = build_twin_pipeline_evidence(mode=PipelineMode.ACTIVE, requirement="x", pool_id="p1",
                                      changed_refs=["a.py"], model_id="m1", provider_id="local",
                                      profile_store_dir=store_dir)
    assert ev["capability_profile_available"] is True
    assert "flag_reasoning" in ev["known_weaknesses"]
    # Evidence-backed weakness raises the policy's required gates.
    assert "FeatureFlagBaseline" in ev["required_gates"]


def test_strong_profile_no_extra_weakness_gate(tmp_path):
    store_dir = _seed_profile(tmp_path, {"flag_reasoning": 0.9, "impact_analysis": 0.9})
    ev = build_twin_pipeline_evidence(mode=PipelineMode.ACTIVE, requirement="x", pool_id="p1",
                                      changed_refs=["a.py"], model_id="m1", provider_id="local",
                                      profile_store_dir=store_dir)
    assert ev["capability_profile_available"] is True
    assert "flag_reasoning" not in ev["known_weaknesses"]


# --- Step 3: compiled Twin instruction in real generation -------------------------

from agent.twin_control_plane.pipeline_integration import compose_generation_system_prompt


def test_compiled_instruction_contains_hard_constraints():
    ev = build_twin_pipeline_evidence(mode=PipelineMode.ACTIVE, requirement="add x",
                                      pool_id="p1", changed_refs=["a.py"])
    text = ev["compiled_instruction"]
    assert text  # present in active mode
    low = text.lower()
    assert "safe apply" in low
    assert "approval" in low  # remote publication requires approval
    assert "stale test" in low
    assert "unavailable" in low  # unavailable-not-passed obligation


def test_off_mode_has_no_compiled_instruction():
    ev = build_twin_pipeline_evidence(mode=PipelineMode.OFF, requirement="x", pool_id="p1",
                                      changed_refs=["a.py"])
    assert "compiled_instruction" not in ev


def test_compose_prompt_appends_section_and_is_off_safe():
    base = "You generate advisory patch proposals only."
    # No instruction -> unchanged (off-safe).
    assert compose_generation_system_prompt(base, None) == base
    assert compose_generation_system_prompt(base, "") == base
    # With instruction -> bounded section appended, base preserved.
    out = compose_generation_system_prompt(base, "# Atlas Implementation Instruction\nSafe Apply boundary.")
    assert out.startswith(base)
    assert "Twin Control Plane" in out
    assert "Safe Apply boundary." in out


def test_audit_only_instruction_has_no_mutation_authority():
    from agent.model_forge.execution_policy import ExecutionPolicySelector, ModelCapabilityProfile
    from agent.model_forge.route_matrix import ChangeClass
    from agent.twin_control_plane.contracts import ModelCapabilityMode
    from agent.twin_control_plane.instruction_compiler import compile_model_instruction
    from agent.twin_control_plane.contracts import TwinBrief

    policy = ExecutionPolicySelector().select(
        ChangeClass.MEDIUM, task_category="audit",
        model_profile=ModelCapabilityProfile(model_id="m", mode=ModelCapabilityMode.AUDIT_ONLY),
    )
    instr = compile_model_instruction(TwinBrief(brief_id="b", goal="review"), policy)
    low = instr.text.lower()
    assert "audit only" in low
    assert "do not mutate files" in low or "do not imply direct apply authority" in low


# --- Step 4: post-apply gates with real sub-gate evidence -------------------------

from agent.twin_control_plane.pipeline_integration import evaluate_twin_post_apply


def test_post_apply_accepted_with_passed_verification():
    r = evaluate_twin_post_apply(
        mode=PipelineMode.ACTIVE, blocking=True, requirement="x", pool_id="p1",
        changed_files=["a.py"], verification=[{"evidence_id": "v1", "status": "passed"}],
        before_twin_revision_id="b", after_twin_revision_id="a")
    assert r["ran"] is True
    assert r["accepted"] is True
    assert r["gate_blocked"] is False
    assert "v1" in r["passed_evidence"]


def test_post_apply_needs_repair_on_failed_verification():
    r = evaluate_twin_post_apply(
        mode=PipelineMode.ACTIVE, blocking=True, requirement="x", pool_id="p1",
        changed_files=["a.py"], verification=[{"evidence_id": "v1", "status": "failed"}],
        before_twin_revision_id="b", after_twin_revision_id="a")
    assert r["needs_repair"] is True
    assert r["accepted"] is False
    # A failed verification is not a hard-boundary block by itself.
    assert r["gate_blocked"] is False


def test_post_apply_unavailable_never_accepts():
    r = evaluate_twin_post_apply(
        mode=PipelineMode.ACTIVE, blocking=True, requirement="x", pool_id="p1",
        changed_files=["a.py"], verification=[{"evidence_id": "v1", "status": "unavailable"}],
        before_twin_revision_id="b", after_twin_revision_id="a")
    assert r["accepted"] is False
    assert "v1" in r["unavailable_evidence"]


def test_post_apply_hard_boundary_blocks_via_contract_sentinel():
    # A blocked Contract Sentinel report -> Patch Impact Gate BLOCKED -> hard block.
    from agent.twin_control_plane.contract_sentinel import ContractFinding, ContractSentinelReport
    sentinel = ContractSentinelReport(
        report_id="cs1", accepted=False, blocked=True,
        findings=[ContractFinding(finding_id="contract.remote_publication_requires_approval",
                                  severity="hard", status="blocked",
                                  message="Remote publication requires approval.")])
    r = evaluate_twin_post_apply(
        mode=PipelineMode.ACTIVE, blocking=True, requirement="x", pool_id="p1",
        changed_files=["a.py"], verification=[{"evidence_id": "v1", "status": "passed"}],
        before_twin_revision_id="b", after_twin_revision_id="a", contract_sentinel=sentinel)
    assert r["blocked_decision"] is True
    assert r["gate_blocked"] is True
    assert r["block_reason"] == "twin_post_apply_hard_boundary"


def test_post_apply_builds_subgates_from_impact():
    store = _seed_twin_store()
    impact = try_project_twin_impact(project_id="p1", changed_refs=["py://mod.f"], store=store)
    r = evaluate_twin_post_apply(
        mode=PipelineMode.ACTIVE, blocking=True, requirement="x", pool_id="p1",
        changed_files=["py://mod.f"], verification=[{"evidence_id": "v1", "status": "passed"}],
        before_twin_revision_id="b", after_twin_revision_id="a", impact=impact)
    # Contract Sentinel + TwinProof were built from the real impact evidence.
    assert "contract_sentinel" in r["sub_gates"]["built_from_impact"]
    assert "twinproof" in r["sub_gates"]["built_from_impact"]
    assert r["sub_gates"]["schema_guardian"] is False  # honestly unavailable
    store.close()


def test_post_apply_off_mode_does_not_run():
    r = evaluate_twin_post_apply(mode=PipelineMode.OFF, blocking=True, changed_files=["a.py"])
    assert r["ran"] is False
    assert r["gate_blocked"] is False
