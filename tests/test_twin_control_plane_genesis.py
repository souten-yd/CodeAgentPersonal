from __future__ import annotations

from agent.project_intelligence.contracts import ProjectMode
from agent.project_intelligence.greenfield import GreenfieldSession, SliceWork
from agent.twin_control_plane.genesis import (
    GenesisKind,
    adapt_greenfield_session,
    classify_genesis,
    safe_apply_required_for_slice,
)


def test_empty_project_maps_to_project_genesis() -> None:
    classification = classify_genesis(ProjectMode.EMPTY, task_category="greenfield")

    assert classification.genesis_kind == GenesisKind.PROJECT
    assert classification.must_use_safe_apply is True
    assert classification.uses_existing_greenfield_pipeline is True
    assert "empty_project" in classification.reasons


def test_existing_project_new_feature_maps_to_feature_genesis() -> None:
    classification = classify_genesis(ProjectMode.EXISTING, task_category="feature")

    assert classification.genesis_kind == GenesisKind.FEATURE
    assert classification.normalized_from_greenfield_partial is False
    assert "existing_project_new_feature" in classification.reasons


def test_new_api_service_ui_or_test_cluster_maps_to_module_genesis() -> None:
    classification = classify_genesis(
        ProjectMode.EXISTING,
        task_category="feature",
        target_refs=["api://billing.create", "service://billing.processor"],
        required_interfaces=["test://billing.contract"],
    )

    assert classification.genesis_kind == GenesisKind.MODULE
    assert "module_boundary_detected" in classification.reasons


def test_greenfield_partial_normalizes_to_feature_genesis() -> None:
    classification = classify_genesis("greenfield_partial", task_category="feature")

    assert classification.genesis_kind == GenesisKind.FEATURE
    assert classification.normalized_from_greenfield_partial is True
    assert "greenfield_partial_normalized_to_feature_genesis" in classification.reasons


def test_existing_greenfield_session_adapts_without_replacing_pipeline() -> None:
    session = GreenfieldSession(
        project_id="p1",
        workspace_id="w1",
        blueprint_revision_id="bp1",
        project_mode="greenfield_partial",
        slices=[["item1"], ["item2", "item3"]],
        completed_slices=[0],
    )

    run = adapt_greenfield_session(session)

    assert run.genesis_kind == GenesisKind.FEATURE
    assert run.project_id == session.project_id
    assert run.workspace_id == session.workspace_id
    assert run.blueprint_revision_id == session.blueprint_revision_id
    assert run.slices == session.slices
    assert run.completed_slices == session.completed_slices
    assert run.uses_existing_greenfield_pipeline is True
    assert run.must_use_safe_apply is True
    assert "greenfield_orchestrator_remains_slice_authority" in run.reasons


def test_greenfield_safe_apply_slice_behavior_is_preserved() -> None:
    work = SliceWork(slice_index=0, apply_intents=[], must_use_safe_apply=True)

    assert safe_apply_required_for_slice(work) is True
