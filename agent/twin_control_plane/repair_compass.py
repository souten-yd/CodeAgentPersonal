"""Repair Compass for Patch Impact Gate outcomes.

This module converts gate failures into targeted repair instructions. It is
pure policy: it does not execute repairs, weaken tests, apply patches, or
publish changes.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Iterable

from pydantic import Field

from agent.twin_control_plane.contracts import ExecutionPolicy, TwinBrief, TwinControlPlaneModel
from agent.twin_control_plane.patch_impact_gate import PatchImpactReport
from agent.twin_control_plane.proof_ledger import ProofLedgerEntry


class RepairCategory(StrEnum):
    HARD_BOUNDARY = "hard_boundary"
    PRODUCT_REGRESSION = "product_regression"
    ENVIRONMENT_UNAVAILABLE = "environment_unavailable"
    MISSING_VERIFICATION = "missing_verification"
    MISSING_TWIN_EVIDENCE = "missing_twin_evidence"
    SCHEMA_PROOF = "schema_proof"
    STATE_PROOF = "state_proof"
    TEST_PROOF = "test_proof"
    PROOF_REQUIREMENT = "proof_requirement"


class RepairInstruction(TwinControlPlaneModel):
    instruction_id: str = Field(min_length=1)
    category: RepairCategory
    summary: str = Field(min_length=1)
    refs: list[str] = Field(default_factory=list)
    proof_requirements: list[str] = Field(default_factory=list)
    prohibited_actions: list[str] = Field(default_factory=list)


class RepairCompassReport(TwinControlPlaneModel):
    report_id: str = Field(min_length=1)
    patch_report_id: str = Field(min_length=1)
    policy_id: str = ""
    brief_id: str = ""
    local_minimal_repair_required: bool = True
    allowed_refs: list[str] = Field(default_factory=list)
    forbidden_refs: list[str] = Field(default_factory=list)
    hard_constraints: list[str] = Field(default_factory=list)
    prohibited_actions: list[str] = Field(default_factory=list)
    product_regression_refs: list[str] = Field(default_factory=list)
    environment_unavailable_refs: list[str] = Field(default_factory=list)
    anti_pattern_hints: list[str] = Field(default_factory=list)
    instructions: list[RepairInstruction] = Field(default_factory=list)


def _unique(values: Iterable[str]) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})


def _hard_constraint_texts(policy: ExecutionPolicy, brief: TwinBrief) -> list[str]:
    return _unique(
        [
            constraint.text
            for constraint in [*policy.hard_constraints, *brief.hard_constraints]
            if constraint.constraint_type == "hard"
        ]
    )


def _base_prohibited_actions(policy: ExecutionPolicy) -> list[str]:
    actions = [
        "Do not weaken or delete tests to make the repair pass.",
        "Do not weaken gates or mark missing proof as passed.",
        "Do not treat unavailable environment/runtime/model evidence as passed.",
        "Do not bypass Proposal, Safe Apply, Verification, or approval boundaries.",
        "Do not perform unrelated broad rewrites while repairing a targeted failure.",
    ]
    if policy.git_policy.remote_publication_requires_approval or policy.git_policy.remote_mutation_requires_approval:
        actions.append("Do not push, publish, create a PR, merge, or mutate remote state without approval.")
    return _unique(actions)


def _instruction(
    instruction_id: str,
    category: RepairCategory,
    summary: str,
    *,
    refs: Iterable[str] = (),
    proof_requirements: Iterable[str] = (),
    prohibited_actions: Iterable[str] = (),
) -> RepairInstruction:
    return RepairInstruction(
        instruction_id=instruction_id,
        category=category,
        summary=summary,
        refs=_unique(refs),
        proof_requirements=_unique(proof_requirements),
        prohibited_actions=_unique(prohibited_actions),
    )


def build_repair_compass(
    *,
    policy: ExecutionPolicy,
    brief: TwinBrief,
    patch_report: PatchImpactReport,
    ledger_entry: ProofLedgerEntry | None = None,
    anti_pattern_hints: Iterable[str] = (),
) -> RepairCompassReport:
    """Build targeted repair instructions from a patch decision report."""
    prohibited = _base_prohibited_actions(policy)
    instructions: list[RepairInstruction] = []
    product_refs = list(patch_report.failed_evidence_refs)
    unavailable_refs = list(patch_report.unavailable_evidence_refs)

    if patch_report.blocked_reasons:
        instructions.append(_instruction(
            f"repair:{patch_report.report_id}:hard_boundary",
            RepairCategory.HARD_BOUNDARY,
            "Stop acceptance and repair the hard boundary violation before changing product behavior.",
            refs=[*patch_report.blocked_reasons, *patch_report.gate_refs],
            proof_requirements=[
                "Restore Proposal / Safe Apply / Verification / approval boundaries and rerun the blocking gate.",
            ],
            prohibited_actions=prohibited,
        ))

    if "verification_failed" in patch_report.repair_reasons or patch_report.failed_evidence_refs:
        instructions.append(_instruction(
            f"repair:{patch_report.report_id}:product_regression",
            RepairCategory.PRODUCT_REGRESSION,
            "Repair the product behavior covered by failed verification, then rerun the same focused evidence.",
            refs=patch_report.failed_evidence_refs,
            proof_requirements=[
                "Keep the failing test or verifier intact unless a separate stale-contract proof and approval exists.",
                "Record the rerun command and evidence id after the repair.",
            ],
            prohibited_actions=prohibited,
        ))

    if "verification_unavailable" in patch_report.repair_reasons or patch_report.unavailable_evidence_refs:
        instructions.append(_instruction(
            f"repair:{patch_report.report_id}:environment_unavailable",
            RepairCategory.ENVIRONMENT_UNAVAILABLE,
            "Keep unavailable environment, runtime, or model evidence separate from product regression repair.",
            refs=patch_report.unavailable_evidence_refs,
            proof_requirements=[
                "Record the unavailable dependency explicitly and rerun when the dependency is available.",
                "Do not change product code solely to satisfy unavailable evidence.",
            ],
            prohibited_actions=prohibited,
        ))

    if "verification_missing" in patch_report.repair_reasons:
        instructions.append(_instruction(
            f"repair:{patch_report.report_id}:missing_verification",
            RepairCategory.MISSING_VERIFICATION,
            "Run or add focused verification for the required gates before acceptance.",
            refs=policy.required_gates,
            proof_requirements=brief.required_tests or patch_report.proof_requirements,
            prohibited_actions=prohibited,
        ))

    if "twin_revision_evidence_missing" in patch_report.repair_reasons:
        instructions.append(_instruction(
            f"repair:{patch_report.report_id}:missing_twin_evidence",
            RepairCategory.MISSING_TWIN_EVIDENCE,
            "Refresh or record before/after Project Twin revisions before deciding acceptance.",
            refs=[patch_report.before_twin_revision_id, patch_report.after_twin_revision_id],
            proof_requirements=[
                "Record before_twin_revision_id and after_twin_revision_id for the repaired patch.",
            ],
            prohibited_actions=prohibited,
        ))

    if "schema_guardian_needs_proof" in patch_report.repair_reasons:
        instructions.append(_instruction(
            f"repair:{patch_report.report_id}:schema_proof",
            RepairCategory.SCHEMA_PROOF,
            "Add schema compatibility, migration, and consumer proof for schema-affecting changes.",
            refs=patch_report.gate_refs,
            proof_requirements=[
                requirement
                for requirement in patch_report.proof_requirements
                if "schema" in requirement.lower() or "migration" in requirement.lower()
            ],
            prohibited_actions=prohibited,
        ))

    if "state_mirror_needs_proof" in patch_report.repair_reasons:
        instructions.append(_instruction(
            f"repair:{patch_report.report_id}:state_proof",
            RepairCategory.STATE_PROOF,
            "Prove backend, UI projection, persistence, and runtime state remain consistent.",
            refs=patch_report.gate_refs,
            proof_requirements=[
                requirement
                for requirement in patch_report.proof_requirements
                if any(term in requirement.lower() for term in ("state", "ui", "persistence", "reload", "runtime"))
            ],
            prohibited_actions=prohibited,
        ))

    if "twinproof_needs_proof" in patch_report.repair_reasons:
        instructions.append(_instruction(
            f"repair:{patch_report.report_id}:test_proof",
            RepairCategory.TEST_PROOF,
            "Close TwinProof gaps with targeted tests or explicit stale-test classification.",
            refs=patch_report.gate_refs,
            proof_requirements=patch_report.proof_requirements,
            prohibited_actions=prohibited,
        ))

    remaining_requirements = [
        requirement
        for requirement in patch_report.proof_requirements
        if not any(requirement in instruction.proof_requirements for instruction in instructions)
    ]
    if remaining_requirements:
        instructions.append(_instruction(
            f"repair:{patch_report.report_id}:proof_requirements",
            RepairCategory.PROOF_REQUIREMENT,
            "Satisfy remaining proof requirements with the smallest local change and focused evidence.",
            refs=[*patch_report.gate_refs, *(ledger_entry.gate_refs if ledger_entry else [])],
            proof_requirements=remaining_requirements,
            prohibited_actions=prohibited,
        ))

    hints = [
        f"Advisory anti-pattern hint, not absolute truth: {hint}"
        for hint in anti_pattern_hints
        if str(hint).strip()
    ]
    return RepairCompassReport(
        report_id=f"repair_compass:{patch_report.report_id}",
        patch_report_id=patch_report.report_id,
        policy_id=policy.policy_id,
        brief_id=brief.brief_id,
        local_minimal_repair_required=policy.git_policy.local_branch_required or policy.git_policy.local_commit_required,
        allowed_refs=_unique([*brief.allowed_refs, *patch_report.changed_files]),
        forbidden_refs=_unique(brief.forbidden_refs),
        hard_constraints=_hard_constraint_texts(policy, brief),
        prohibited_actions=prohibited,
        product_regression_refs=_unique(product_refs),
        environment_unavailable_refs=_unique(unavailable_refs),
        anti_pattern_hints=_unique(hints),
        instructions=sorted(instructions, key=lambda item: item.instruction_id),
    )


__all__ = [
    "RepairCategory",
    "RepairCompassReport",
    "RepairInstruction",
    "build_repair_compass",
]
