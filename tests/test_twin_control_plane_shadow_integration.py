"""TFG-11 / Package 10 — Atlas pipeline shadow integration tests.

Proves the shadow orchestrator composes Twin/Forge/Git artifacts without taking over
execution:

- OFF mode returns None and assembles nothing (legacy flow unchanged);
- SHADOW mode produces ExecutionPolicy, TwinBrief, a local Git plan, BlastMap, and
  TwinProof where inputs allow;
- missing inputs are recorded as ``unavailable`` rather than raising;
- the local Git plan never includes approval-bound remote operations;
- the report never claims to change execution or production routing;
- reports round-trip through the shadow store.
"""
from __future__ import annotations

from datetime import datetime, timezone

from agent.model_forge.route_taxonomy import ForgeRoute
from agent.project_intelligence.contracts import RuntimeObservationRecord
from agent.project_twin.contracts import ImpactItem, ImpactResult
from agent.twin_control_plane.contracts import (
    ExecutionPolicy,
    InstructionStyle,
    ModelCapabilityMode,
    TwinBrief,
    TwinConstraint,
    TwinInjectionLevel,
    default_hard_constraints,
)
from agent.twin_control_plane.shadow_integration import (
    TwinShadowMode,
    TwinShadowOrchestrator,
    TwinShadowStore,
)


def _impact() -> ImpactResult:
    return ImpactResult(
        project_id="p1", twin_revision_id="tw1", generated_at=datetime.now(timezone.utc),
        direct_impacts=[ImpactItem(
            canonical_ref="py://feature.entry", item_type="symbol", status="verified",
            confidence=0.9, source_refs=["py://feature.entry"],
            evidence_refs=["evidence://feature.entry"], reason="changed",
        )],
    )


def _policy() -> ExecutionPolicy:
    return ExecutionPolicy(
        policy_id="policy1", route=ForgeRoute.BLUEPRINT_SLICE, model_id="local-coder",
        instruction_style=InstructionStyle.CONSTRAINED_PATCH,
        model_capability_mode=ModelCapabilityMode.WEAK_LOCAL,
        twin_injection_level=TwinInjectionLevel.CONSTRAINED_WITH_TESTS,
        required_gates=["SafeApplyBoundary", "RemotePublishApprovalGate"],
        hard_constraints=default_hard_constraints(),
    )


def _brief() -> TwinBrief:
    return TwinBrief(
        brief_id="brief1", allowed_refs=["py://feature.entry"],
        impacted_refs=["py://feature.entry"],
        hard_constraints=[TwinConstraint(constraint_id="c1", text="Preserve API.")],
        proof_requirements=["prove feature entry behavior"],
    )


def _runtime() -> RuntimeObservationRecord:
    return RuntimeObservationRecord(
        observation_id="o1", project_id="p1", workspace_id="w1", collector="pytest",
        observation_type="test_execution", subject_refs=["test://test_feature", "py://feature.entry"],
        result="passed", evidence_refs=["evidence://o1"],
    )


def test_off_mode_returns_none_and_assembles_nothing():
    orch = TwinShadowOrchestrator(TwinShadowMode.OFF)
    assert orch.mode == TwinShadowMode.OFF
    report = orch.assemble(
        requirement_ref="req1", plan_item_ref="plan1",
        execution_policy=_policy(), twin_brief=_brief(), impact=_impact(),
    )
    assert report is None


def test_shadow_mode_assembles_full_report():
    orch = TwinShadowOrchestrator(TwinShadowMode.SHADOW)
    report = orch.assemble(
        requirement_ref="req1", plan_item_ref="plan1",
        execution_policy=_policy(), twin_brief=_brief(), impact=_impact(),
        changed_refs=["py://feature.entry"],
        runtime_observations=[_runtime()], related_test_refs=["test://test_feature"],
    )
    assert report is not None
    assert report.mode == TwinShadowMode.SHADOW
    assert report.execution_policy.policy_id == "policy1"
    assert report.twin_brief.brief_id == "brief1"
    assert report.blast_map is not None
    assert "py://feature.entry" in report.blast_map.changed_refs
    assert report.twinproof.test_inventory  # built from the runtime observation
    assert report.git_plan  # local plan present
    assert report.unavailable_artifacts == []


def test_shadow_never_changes_execution_or_routing():
    orch = TwinShadowOrchestrator(TwinShadowMode.SHADOW)
    report = orch.assemble(execution_policy=_policy(), twin_brief=_brief(), impact=_impact())
    assert report.changes_execution is False
    assert report.changes_production_routing is False


def test_missing_inputs_recorded_as_unavailable_not_raised():
    orch = TwinShadowOrchestrator(TwinShadowMode.SHADOW)
    # No impact, no policy, no brief, no runtime/test evidence.
    report = orch.assemble(plan_item_ref="plan1")
    assert report is not None
    assert report.execution_policy is None
    assert report.blast_map is None
    assert "blast_map:no_impact_result" in report.unavailable_artifacts
    assert "execution_policy:not_supplied" in report.unavailable_artifacts
    assert "twin_brief:not_supplied" in report.unavailable_artifacts
    assert "twinproof:no_runtime_or_test_evidence" in report.unavailable_artifacts


def test_git_plan_excludes_remote_publication():
    orch = TwinShadowOrchestrator(TwinShadowMode.SHADOW)
    report = orch.assemble(
        plan_item_ref="plan1",
        git_operations=["status", "branch", "commit", "push", "create-pr"],
    )
    planned = {d.operation for d in report.git_plan}
    assert "status" in planned and "commit" in planned
    # Remote publication is approval-bound and excluded from the autonomous shadow plan.
    assert "push" not in planned and "create-pr" not in planned
    assert "git_plan:push:approval_required" in report.unavailable_artifacts
    assert all(not d.approval_required for d in report.git_plan)


def test_report_round_trips_through_store(tmp_path):
    orch = TwinShadowOrchestrator(TwinShadowMode.SHADOW)
    report = orch.assemble(
        plan_item_ref="plan1", execution_policy=_policy(), twin_brief=_brief(), impact=_impact(),
    )
    store = TwinShadowStore(tmp_path / "twin_shadow")
    store.record(report)
    loaded = store.load(report.report_id)
    assert loaded is not None
    assert loaded.report_id == report.report_id
    assert loaded.execution_policy.policy_id == "policy1"
