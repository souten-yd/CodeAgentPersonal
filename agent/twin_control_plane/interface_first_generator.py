"""Interface First Generator for Genesis work.

The generator emits public interface, schema, state, and test contracts before
implementation instructions. It feeds the existing TwinBrief contract rather
than creating a separate execution authority.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Iterable

from pydantic import Field

from agent.twin_control_plane.contracts import TwinBrief, TwinControlPlaneModel
from agent.twin_control_plane.genesis import GenesisClassification
from agent.twin_control_plane.no_data_bootstrap_gate import NoDataBootstrapAssessment


class InterfaceSectionKind(StrEnum):
    PUBLIC_INTERFACE = "public_interface"
    SERVICE_BOUNDARY = "service_boundary"
    ARTIFACT_SCHEMA = "artifact_schema"
    UI_PROJECTION = "ui_projection"
    PERSISTENCE_SCHEMA = "persistence_schema"
    TEST_FIXTURE = "test_fixture"


class InterfaceFirstSection(TwinControlPlaneModel):
    section_id: str = Field(min_length=1)
    kind: InterfaceSectionKind
    refs: list[str] = Field(default_factory=list)
    contract_steps: list[str] = Field(default_factory=list)
    proof_requirements: list[str] = Field(default_factory=list)


class InterfaceFirstPlan(TwinControlPlaneModel):
    plan_id: str = Field(min_length=1)
    genesis_kind: str
    sections: list[InterfaceFirstSection] = Field(default_factory=list)
    required_interfaces: list[str] = Field(default_factory=list)
    required_tests: list[str] = Field(default_factory=list)
    proof_requirements: list[str] = Field(default_factory=list)
    bootstrap_requirement_ids: list[str] = Field(default_factory=list)


def _unique(values: Iterable[str]) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})


def _section(
    kind: InterfaceSectionKind,
    refs: Iterable[str],
    *,
    contract_steps: Iterable[str],
    proof_requirements: Iterable[str],
) -> InterfaceFirstSection:
    return InterfaceFirstSection(
        section_id=f"interface_first.{kind.value}",
        kind=kind,
        refs=_unique(refs),
        contract_steps=list(contract_steps),
        proof_requirements=list(proof_requirements),
    )


def generate_interface_first_plan(
    classification: GenesisClassification,
    *,
    public_interfaces: Iterable[str] = (),
    service_boundaries: Iterable[str] = (),
    artifact_schemas: Iterable[str] = (),
    ui_projection_contracts: Iterable[str] = (),
    persistence_schemas: Iterable[str] = (),
    test_fixture_contracts: Iterable[str] = (),
    bootstrap: NoDataBootstrapAssessment | None = None,
) -> InterfaceFirstPlan:
    """Generate interface/schema/state/test contracts before implementation."""
    sections = [
        _section(
            InterfaceSectionKind.PUBLIC_INTERFACE,
            public_interfaces,
            contract_steps=[
                "Declare request/response shape, errors, and ownership before implementation.",
                "Preserve listed public interfaces unless migration proof is recorded.",
            ],
            proof_requirements=["Public interface contract test or explicit no-interface rationale."],
        ),
        _section(
            InterfaceSectionKind.SERVICE_BOUNDARY,
            service_boundaries,
            contract_steps=[
                "Declare service responsibilities and forbidden cross-boundary writes.",
                "Keep Proposal, Safe Apply, Verification, and publication authority separate.",
            ],
            proof_requirements=["Service boundary test or static contract assertion."],
        ),
        _section(
            InterfaceSectionKind.ARTIFACT_SCHEMA,
            artifact_schemas,
            contract_steps=[
                "Declare artifact fields, version, data policy, and compatibility expectations.",
                "Record migration notes before accepting schema-affecting changes.",
            ],
            proof_requirements=["Artifact schema compatibility or migration proof."],
        ),
        _section(
            InterfaceSectionKind.UI_PROJECTION,
            ui_projection_contracts,
            contract_steps=[
                "Declare backend-authoritative fields and UI projection states.",
                "Require proof that UI controls do not contradict backend authority.",
            ],
            proof_requirements=["Backend-state-to-UI-state projection proof."],
        ),
        _section(
            InterfaceSectionKind.PERSISTENCE_SCHEMA,
            persistence_schemas,
            contract_steps=[
                "Declare persisted shape, keys, defaults, and reload behavior.",
                "Require create/read/reload proof for new persistence.",
            ],
            proof_requirements=["Persistence create/read/reload proof."],
        ),
        _section(
            InterfaceSectionKind.TEST_FIXTURE,
            test_fixture_contracts,
            contract_steps=[
                "Declare required fixtures, deterministic seeds, and unavailable-evidence behavior.",
                "Tests must prove bootstrap contracts before broad implementation is accepted.",
            ],
            proof_requirements=["Initial contract tests and truthful unavailable evidence records."],
        ),
    ]

    bootstrap_requirements = list(bootstrap.requirements) if bootstrap else []
    required_tests = [req.test_ref for req in bootstrap_requirements]
    proof_requirements = [proof for section in sections for proof in section.proof_requirements]
    proof_requirements.extend(req.proof_requirement for req in bootstrap_requirements)

    return InterfaceFirstPlan(
        plan_id=f"interface_first:{classification.genesis_kind.value}:{classification.project_mode}",
        genesis_kind=classification.genesis_kind.value,
        sections=sections,
        required_interfaces=_unique([
            *public_interfaces,
            *service_boundaries,
            *artifact_schemas,
            *ui_projection_contracts,
            *persistence_schemas,
            *test_fixture_contracts,
        ]),
        required_tests=_unique(required_tests),
        proof_requirements=_unique(proof_requirements),
        bootstrap_requirement_ids=[req.requirement_id for req in bootstrap_requirements],
    )


def apply_interface_first_plan(brief: TwinBrief, plan: InterfaceFirstPlan) -> TwinBrief:
    """Return a TwinBrief enriched with Interface First contracts and proof."""
    section_payload = [section.model_dump(mode="json") for section in plan.sections]
    metadata = dict(brief.metadata or {})
    metadata["interface_first_plan_id"] = plan.plan_id
    metadata["interface_first_sections"] = section_payload
    metadata["bootstrap_requirement_ids"] = list(plan.bootstrap_requirement_ids)

    return brief.model_copy(update={
        "required_interfaces": _unique([*brief.required_interfaces, *plan.required_interfaces]),
        "required_tests": _unique([*brief.required_tests, *plan.required_tests]),
        "proof_requirements": _unique([*brief.proof_requirements, *plan.proof_requirements]),
        "metadata": metadata,
    })


__all__ = [
    "InterfaceFirstPlan",
    "InterfaceFirstSection",
    "InterfaceSectionKind",
    "apply_interface_first_plan",
    "generate_interface_first_plan",
]
