"""Patch Impact Gate.

Compares patch refs, Git/Twin refs, verification evidence, and control-plane
gate findings. The gate is pure policy and does not execute verification.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Iterable

from pydantic import Field

from agent.git_steward.contracts import GitStewardResult
from agent.twin_control_plane.blast_map import BlastMap
from agent.twin_control_plane.contract_sentinel import ContractSentinelReport
from agent.twin_control_plane.contracts import ExecutionPolicy, TwinBrief, TwinControlPlaneModel
from agent.twin_control_plane.schema_guardian import SchemaGuardianReport
from agent.twin_control_plane.state_mirror import StateMirrorReport
from agent.twin_control_plane.twinproof import TwinProofReport


class PatchGateDecision(StrEnum):
    ACCEPTED = "accepted"
    BLOCKED = "blocked"
    NEEDS_REPAIR = "needs_repair"


class VerificationEvidence(TwinControlPlaneModel):
    evidence_id: str = Field(min_length=1)
    status: str = "unavailable"  # passed | failed | unavailable
    command: str = ""
    refs: list[str] = Field(default_factory=list)
    summary: str = ""


class PatchImpactReport(TwinControlPlaneModel):
    report_id: str = Field(min_length=1)
    decision: PatchGateDecision
    accepted: bool = False
    blocked: bool = False
    needs_repair: bool = False
    policy_id: str = ""
    brief_id: str = ""
    base_ref: str = ""
    head_ref: str = ""
    git_commit_sha: str = ""
    changed_files: list[str] = Field(default_factory=list)
    before_twin_revision_id: str = ""
    after_twin_revision_id: str = ""
    passed_evidence_refs: list[str] = Field(default_factory=list)
    failed_evidence_refs: list[str] = Field(default_factory=list)
    unavailable_evidence_refs: list[str] = Field(default_factory=list)
    blocked_reasons: list[str] = Field(default_factory=list)
    repair_reasons: list[str] = Field(default_factory=list)
    proof_requirements: list[str] = Field(default_factory=list)
    gate_refs: list[str] = Field(default_factory=list)


def _unique(values: Iterable[str]) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})


def evaluate_patch_impact(
    *,
    policy: ExecutionPolicy,
    brief: TwinBrief,
    base_ref: str,
    head_ref: str,
    git_result: GitStewardResult | None = None,
    changed_files: Iterable[str] = (),
    before_twin_revision_id: str = "",
    after_twin_revision_id: str = "",
    verification: Iterable[VerificationEvidence] = (),
    blast_map: BlastMap | None = None,
    contract_sentinel: ContractSentinelReport | None = None,
    schema_guardian: SchemaGuardianReport | None = None,
    state_mirror: StateMirrorReport | None = None,
    twinproof: TwinProofReport | None = None,
) -> PatchImpactReport:
    """Evaluate patch acceptance from collected evidence and gate reports."""
    verification_items = list(verification)
    blocked_reasons: list[str] = []
    repair_reasons: list[str] = []
    proof_requirements: list[str] = []
    gate_refs: list[str] = []

    if contract_sentinel:
        gate_refs.append(contract_sentinel.report_id)
        proof_requirements.extend(contract_sentinel.proof_requirements)
        if contract_sentinel.blocked:
            blocked_reasons.append("contract_sentinel_blocked")
    if schema_guardian:
        gate_refs.append(schema_guardian.report_id)
        proof_requirements.extend(schema_guardian.proof_requirements)
        if schema_guardian.blocked:
            blocked_reasons.append("schema_guardian_blocked")
        elif schema_guardian.migration_required or not schema_guardian.accepted:
            repair_reasons.append("schema_guardian_needs_proof")
    if state_mirror:
        gate_refs.append(state_mirror.report_id)
        proof_requirements.extend(state_mirror.proof_requirements)
        if state_mirror.blocked:
            blocked_reasons.append("state_mirror_blocked")
        elif not state_mirror.accepted:
            repair_reasons.append("state_mirror_needs_proof")
    if twinproof:
        gate_refs.append(twinproof.report_id)
        proof_requirements.extend(twinproof.proof_requirements)
        if not twinproof.accepted:
            repair_reasons.append("twinproof_needs_proof")
    if blast_map:
        gate_refs.append(blast_map.blast_map_id)
        proof_requirements.extend(blast_map.proof_requirements)

    passed = [item.evidence_id for item in verification_items if item.status == "passed"]
    failed = [item.evidence_id for item in verification_items if item.status == "failed"]
    unavailable = [item.evidence_id for item in verification_items if item.status == "unavailable"]
    if failed:
        repair_reasons.append("verification_failed")
    if unavailable:
        repair_reasons.append("verification_unavailable")
    if policy.required_gates and not verification_items:
        repair_reasons.append("verification_missing")

    if not before_twin_revision_id or not after_twin_revision_id:
        repair_reasons.append("twin_revision_evidence_missing")

    if blocked_reasons:
        decision = PatchGateDecision.BLOCKED
    elif repair_reasons:
        decision = PatchGateDecision.NEEDS_REPAIR
    else:
        decision = PatchGateDecision.ACCEPTED

    all_changed = [*changed_files]
    if git_result:
        all_changed.extend(git_result.changed_files)
    return PatchImpactReport(
        report_id=f"patch_impact:{policy.policy_id}:{brief.brief_id}:{head_ref or 'working_tree'}",
        decision=decision,
        accepted=decision == PatchGateDecision.ACCEPTED,
        blocked=decision == PatchGateDecision.BLOCKED,
        needs_repair=decision == PatchGateDecision.NEEDS_REPAIR,
        policy_id=policy.policy_id,
        brief_id=brief.brief_id,
        base_ref=base_ref,
        head_ref=head_ref,
        git_commit_sha=git_result.commit_sha if git_result else "",
        changed_files=_unique(all_changed),
        before_twin_revision_id=before_twin_revision_id,
        after_twin_revision_id=after_twin_revision_id,
        passed_evidence_refs=_unique(passed),
        failed_evidence_refs=_unique(failed),
        unavailable_evidence_refs=_unique(unavailable),
        blocked_reasons=_unique(blocked_reasons),
        repair_reasons=_unique(repair_reasons),
        proof_requirements=_unique(proof_requirements),
        gate_refs=_unique(gate_refs),
    )


__all__ = [
    "PatchGateDecision",
    "PatchImpactReport",
    "VerificationEvidence",
    "evaluate_patch_impact",
]
