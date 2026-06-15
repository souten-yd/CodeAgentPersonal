"""No-data bootstrap gate for Genesis work.

Empty stores, missing persisted state, absent runtime evidence, and absent tests
are normal startup conditions. They still require explicit bootstrap acceptance
scenarios before implementation can be accepted.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Iterable

from pydantic import Field

from agent.project_intelligence.contracts import ProjectMode
from agent.twin_control_plane.contracts import TwinControlPlaneModel
from agent.twin_control_plane.genesis import GenesisKind


class BootstrapCondition(StrEnum):
    EMPTY_PROJECT = "empty_project"
    PARTIALLY_KNOWN_PROJECT = "partially_known_project"
    MISSING_PERSISTED_STATE = "missing_persisted_state"
    NO_RUNTIME_EVIDENCE = "no_runtime_evidence"
    NO_PRIOR_TESTS = "no_prior_tests"


class BootstrapRequirement(TwinControlPlaneModel):
    requirement_id: str = Field(min_length=1)
    condition: BootstrapCondition
    description: str = Field(min_length=1)
    acceptance_scenario: str = Field(min_length=1)
    proof_requirement: str = Field(min_length=1)
    test_ref: str = Field(min_length=1)


class NoDataBootstrapAssessment(TwinControlPlaneModel):
    assessment_id: str = Field(min_length=1)
    genesis_kind: GenesisKind
    project_mode: str
    conditions: list[BootstrapCondition] = Field(default_factory=list)
    requirements: list[BootstrapRequirement] = Field(default_factory=list)
    bootstrap_required: bool = False
    accept_implementation_without_bootstrap: bool = True
    reasons: list[str] = Field(default_factory=list)


def _mode_value(project_mode: ProjectMode | str) -> str:
    return project_mode.value if isinstance(project_mode, ProjectMode) else str(project_mode)


def _has_values(values: Iterable[str]) -> bool:
    return any(str(value).strip() for value in values)


def _requirement(condition: BootstrapCondition, *, genesis_kind: GenesisKind) -> BootstrapRequirement:
    if condition == BootstrapCondition.EMPTY_PROJECT:
        return BootstrapRequirement(
            requirement_id="bootstrap.empty_project.acceptance",
            condition=condition,
            description="Empty project bootstrap must not assume existing files, data, tests, or runtime state.",
            acceptance_scenario="Create the first runnable slice from declared interfaces and verify it from a clean workspace.",
            proof_requirement="Record clean-workspace create/build/test evidence before accepting implementation.",
            test_ref="bootstrap://empty_project_clean_workspace",
        )
    if condition == BootstrapCondition.PARTIALLY_KNOWN_PROJECT:
        return BootstrapRequirement(
            requirement_id="bootstrap.partial_project.acceptance",
            condition=condition,
            description="Partially-known project bootstrap must preserve known state and make unknowns explicit.",
            acceptance_scenario="Run a feature bootstrap that lists known refs, unknown refs, and required discovery before edits.",
            proof_requirement="Record discovery output and focused tests for new feature boundaries.",
            test_ref="bootstrap://partial_project_discovery",
        )
    if condition == BootstrapCondition.MISSING_PERSISTED_STATE:
        return BootstrapRequirement(
            requirement_id="bootstrap.persistence.create_read_reload",
            condition=condition,
            description="New or missing persisted state requires create/read/reload proof.",
            acceptance_scenario="Create persisted state, reload the process/store, and read the same authoritative values.",
            proof_requirement="Record create/read/reload evidence and schema expectations.",
            test_ref="bootstrap://persistence_create_read_reload",
        )
    if condition == BootstrapCondition.NO_RUNTIME_EVIDENCE:
        return BootstrapRequirement(
            requirement_id="bootstrap.runtime.first_observation",
            condition=condition,
            description="No prior runtime evidence requires first-run observation proof.",
            acceptance_scenario="Run the smallest representative runtime path and record passed/failed/unavailable explicitly.",
            proof_requirement="Record runtime observation ids; unavailable runtime remains unavailable.",
            test_ref="bootstrap://runtime_first_observation",
        )
    return BootstrapRequirement(
        requirement_id="bootstrap.tests.initial_contract",
        condition=condition,
        description="No prior tests requires initial contract tests before implementation is accepted.",
        acceptance_scenario="Add focused tests for public interface, persistence/reload, and projection contracts before broad implementation.",
        proof_requirement=f"Record initial contract test output for {genesis_kind.value}.",
        test_ref="bootstrap://initial_contract_tests",
    )


def evaluate_no_data_bootstrap(
    *,
    genesis_kind: GenesisKind,
    project_mode: ProjectMode | str,
    has_persisted_state: bool,
    prior_runtime_evidence_refs: Iterable[str] = (),
    prior_test_refs: Iterable[str] = (),
) -> NoDataBootstrapAssessment:
    """Evaluate normal no-data startup conditions and required bootstrap proof."""
    mode = _mode_value(project_mode)
    conditions: list[BootstrapCondition] = []

    if mode == ProjectMode.EMPTY.value or genesis_kind == GenesisKind.PROJECT:
        conditions.append(BootstrapCondition.EMPTY_PROJECT)
    elif mode in {ProjectMode.GREENFIELD_PARTIAL.value, ProjectMode.IMPORTED_UNKNOWN.value, ProjectMode.GENERATED_UNVERIFIED.value}:
        conditions.append(BootstrapCondition.PARTIALLY_KNOWN_PROJECT)

    if not has_persisted_state:
        conditions.append(BootstrapCondition.MISSING_PERSISTED_STATE)
    if not _has_values(prior_runtime_evidence_refs):
        conditions.append(BootstrapCondition.NO_RUNTIME_EVIDENCE)
    if not _has_values(prior_test_refs):
        conditions.append(BootstrapCondition.NO_PRIOR_TESTS)

    deduped = list(dict.fromkeys(conditions))
    requirements = [_requirement(condition, genesis_kind=genesis_kind) for condition in deduped]
    bootstrap_required = bool(requirements)
    return NoDataBootstrapAssessment(
        assessment_id=f"no_data_bootstrap:{genesis_kind.value}:{mode}",
        genesis_kind=genesis_kind,
        project_mode=mode,
        conditions=deduped,
        requirements=requirements,
        bootstrap_required=bootstrap_required,
        accept_implementation_without_bootstrap=not bootstrap_required,
        reasons=[condition.value for condition in deduped],
    )


__all__ = [
    "BootstrapCondition",
    "BootstrapRequirement",
    "NoDataBootstrapAssessment",
    "evaluate_no_data_bootstrap",
]
