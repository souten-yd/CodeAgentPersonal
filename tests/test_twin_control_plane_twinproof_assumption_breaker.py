from __future__ import annotations

from agent.project_intelligence.contracts import ProjectMode, RuntimeObservationRecord
from agent.twin_control_plane.assumption_breaker import AssumptionBreakerCase, generate_assumption_breaker_briefs
from agent.twin_control_plane.genesis import GenesisKind
from agent.twin_control_plane.no_data_bootstrap_gate import evaluate_no_data_bootstrap
from agent.twin_control_plane.schema_guardian import (
    SchemaField,
    SchemaSnapshot,
    SchemaSurface,
    compare_schema_snapshots,
)
from agent.twin_control_plane.state_mirror import StateObservation, StateSurface, compare_state_mirror
from agent.twin_control_plane.twinproof import TestClassification, build_twinproof


def _runtime(oid: str, result: str, subjects: list[str]) -> RuntimeObservationRecord:
    return RuntimeObservationRecord(
        observation_id=oid,
        project_id="p1",
        workspace_id="w1",
        collector="pytest",
        observation_type="test_execution",
        subject_refs=subjects,
        result=result,
        evidence_refs=[f"evidence://{oid}"],
    )


def test_twinproof_classifies_impacted_stale_flaky_redundant_and_coverage_gaps() -> None:
    report = build_twinproof(
        runtime_observations=[
            _runtime("o1", "passed", ["test://test_feature", "py://feature.entry"]),
            _runtime("o2", "failed", ["test://test_feature", "py://feature.entry"]),
            _runtime("o3", "passed", ["test://test_duplicate_a", "py://feature.entry"]),
            _runtime("o4", "passed", ["test://test_duplicate_b", "py://feature.entry"]),
        ],
        related_test_refs=["test://stale_old_contract"],
        impacted_refs=["py://feature.entry", "py://uncovered.ref"],
        stale_test_refs=["test://stale_old_contract"],
    )

    assert "test://test_feature" in report.impacted_tests
    assert "test://stale_old_contract" in report.stale_candidates
    assert "test://test_feature" in report.flaky_candidates
    assert "test://test_duplicate_b" in report.redundant_candidates
    assert "py://uncovered.ref" in report.coverage_gaps
    flaky = next(item for item in report.test_inventory if item.test_ref == "test://test_feature")
    assert TestClassification.FLAKY_CANDIDATE in flaky.classifications
    assert report.accepted is False


def test_twinproof_consumes_no_data_schema_and_state_findings() -> None:
    no_data = evaluate_no_data_bootstrap(
        genesis_kind=GenesisKind.PROJECT,
        project_mode=ProjectMode.EMPTY,
        has_persisted_state=False,
    )
    schema = compare_schema_snapshots(
        SchemaSnapshot(
            schema_id="api://runtime.status",
            surface=SchemaSurface.API_RESPONSE,
            fields=[SchemaField(name="status", field_type="str", required=True)],
        ),
        SchemaSnapshot(
            schema_id="api://runtime.status",
            surface=SchemaSurface.API_RESPONSE,
            fields=[SchemaField(name="status", field_type="int", required=True)],
        ),
    )
    state = compare_state_mirror(
        backend=[StateObservation(path="can_execute", value=False, surface=StateSurface.BACKEND)],
        ui=[StateObservation(path="can_execute", value=True, surface=StateSurface.UI_PROJECTION)],
    )

    report = build_twinproof(no_data=no_data, schema_guardian=schema, state_mirror=state)

    gap_types = {gap.gap_type for gap in report.proof_gaps}
    assert {"no_data", "schema", "state"} <= gap_types
    assert any("Record clean-workspace" in req for req in report.proof_requirements)
    assert any("Unit tests alone are insufficient" in req for req in report.proof_requirements)
    assert any("Align UI projection" in req for req in report.proof_requirements)


def test_assumption_breaker_generates_targeted_briefs() -> None:
    no_data = evaluate_no_data_bootstrap(
        genesis_kind=GenesisKind.PROJECT,
        project_mode=ProjectMode.EMPTY,
        has_persisted_state=False,
    )
    state = compare_state_mirror(
        backend=[StateObservation(path="workflow_state.completed_plan_item_count", value=3, surface=StateSurface.BACKEND)],
        persisted=[StateObservation(path="workflow_state.completed_plan_item_count", value=1, surface=StateSurface.PERSISTENCE)],
    )
    twinproof = build_twinproof(
        related_test_refs=["test://old_contract"],
        stale_test_refs=["test://old_contract"],
        no_data=no_data,
        state_mirror=state,
    )

    briefs = generate_assumption_breaker_briefs(
        twinproof,
        no_data=no_data,
        state_mirror=state,
        feature_flag_refs=["flag://new_workflow"],
        stale_contract_refs=["contract://old_status"],
    )

    case_types = {brief.case_type for brief in briefs}
    assert AssumptionBreakerCase.NO_DATA in case_types
    assert AssumptionBreakerCase.RELOAD in case_types
    assert AssumptionBreakerCase.FEATURE_FLAG in case_types
    assert AssumptionBreakerCase.STALE_CONTRACT in case_types
    stale = next(brief for brief in briefs if brief.case_type == AssumptionBreakerCase.STALE_CONTRACT)
    assert "test://old_contract" in stale.refs
    assert "contract://old_status" in stale.refs
