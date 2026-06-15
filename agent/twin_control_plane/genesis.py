"""Genesis taxonomy and Greenfield adapter.

Genesis is a classification layer over existing Project Intelligence and
Greenfield behavior. It does not create a second generation pipeline.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Iterable

from pydantic import Field

from agent.project_intelligence.contracts import ProjectMode
from agent.project_intelligence.greenfield import GreenfieldSession, SliceWork
from agent.twin_control_plane.contracts import TwinControlPlaneModel


class GenesisKind(StrEnum):
    PROJECT = "project_genesis"
    FEATURE = "feature_genesis"
    MODULE = "module_genesis"


class GenesisClassification(TwinControlPlaneModel):
    genesis_kind: GenesisKind
    project_mode: str
    task_category: str = ""
    uses_existing_greenfield_pipeline: bool = True
    must_use_safe_apply: bool = True
    normalized_from_greenfield_partial: bool = False
    reasons: list[str] = Field(default_factory=list)


class GenesisRun(TwinControlPlaneModel):
    genesis_kind: GenesisKind
    project_id: str
    workspace_id: str
    blueprint_revision_id: str = ""
    project_mode: str
    slices: list[list[str]] = Field(default_factory=list)
    completed_slices: list[int] = Field(default_factory=list)
    uses_existing_greenfield_pipeline: bool = True
    must_use_safe_apply: bool = True
    normalized_from_greenfield_partial: bool = False
    reasons: list[str] = Field(default_factory=list)


_MODULE_TASK_CATEGORIES = {
    "api",
    "service",
    "ui",
    "frontend",
    "backend",
    "module",
    "test_cluster",
    "persistence",
}

_MODULE_REF_PREFIXES = (
    "api://",
    "service://",
    "ui://",
    "frontend://",
    "backend://",
    "test://",
    "schema://",
    "persistence://",
)


def _mode_value(project_mode: ProjectMode | str) -> str:
    return project_mode.value if isinstance(project_mode, ProjectMode) else str(project_mode)


def _has_module_shape(values: Iterable[str]) -> bool:
    return any(str(value).startswith(_MODULE_REF_PREFIXES) for value in values)


def classify_genesis(
    project_mode: ProjectMode | str,
    *,
    task_category: str = "",
    target_refs: Iterable[str] = (),
    required_interfaces: Iterable[str] = (),
) -> GenesisClassification:
    """Classify work into Project, Feature, or Module Genesis."""
    mode = _mode_value(project_mode)
    category = task_category.strip().lower()
    refs = [*target_refs, *required_interfaces]
    reasons: list[str] = []
    normalized = False

    if mode == ProjectMode.EMPTY.value:
        kind = GenesisKind.PROJECT
        reasons.append("empty_project")
    elif mode == ProjectMode.GREENFIELD_PARTIAL.value:
        kind = GenesisKind.FEATURE
        normalized = True
        reasons.append("greenfield_partial_normalized_to_feature_genesis")
    elif category in _MODULE_TASK_CATEGORIES or _has_module_shape(refs):
        kind = GenesisKind.MODULE
        reasons.append("module_boundary_detected")
    else:
        kind = GenesisKind.FEATURE
        reasons.append("existing_project_new_feature")

    return GenesisClassification(
        genesis_kind=kind,
        project_mode=mode,
        task_category=task_category,
        normalized_from_greenfield_partial=normalized,
        reasons=reasons,
    )


def adapt_greenfield_session(session: GreenfieldSession) -> GenesisRun:
    """Adapt an existing Greenfield session into Genesis terms without replacing it."""
    classification = classify_genesis(session.project_mode)
    return GenesisRun(
        genesis_kind=classification.genesis_kind,
        project_id=session.project_id,
        workspace_id=session.workspace_id,
        blueprint_revision_id=session.blueprint_revision_id,
        project_mode=session.project_mode,
        slices=[list(layer) for layer in session.slices],
        completed_slices=list(session.completed_slices),
        uses_existing_greenfield_pipeline=True,
        must_use_safe_apply=True,
        normalized_from_greenfield_partial=classification.normalized_from_greenfield_partial,
        reasons=[
            *classification.reasons,
            "adapted_from_existing_greenfield_session",
            "greenfield_orchestrator_remains_slice_authority",
        ],
    )


def safe_apply_required_for_slice(work: SliceWork) -> bool:
    """Expose the existing Greenfield Safe Apply invariant for Genesis tests."""
    return bool(work.must_use_safe_apply)


__all__ = [
    "GenesisClassification",
    "GenesisKind",
    "GenesisRun",
    "adapt_greenfield_session",
    "classify_genesis",
    "safe_apply_required_for_slice",
]
