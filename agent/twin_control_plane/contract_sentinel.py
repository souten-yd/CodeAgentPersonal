"""Contract Sentinel for hard safety and preservation checks.

The sentinel consumes policy/brief constraints and BlastMap findings. It does
not apply changes or decide schema/state compatibility itself; future Schema
Guardian and StateMirror findings are represented as required delegated proof.
"""
from __future__ import annotations

from typing import Iterable

from pydantic import Field

from agent.twin_control_plane.blast_map import BlastMap
from agent.twin_control_plane.contracts import ExecutionPolicy, TwinBrief, TwinConstraint, TwinControlPlaneModel


class ContractFinding(TwinControlPlaneModel):
    finding_id: str = Field(min_length=1)
    severity: str = "advisory"       # hard | soft | advisory
    status: str = "needs_proof"      # passed | needs_proof | blocked
    message: str = Field(min_length=1)
    refs: list[str] = Field(default_factory=list)
    delegated_to: str | None = None


class ContractSentinelReport(TwinControlPlaneModel):
    report_id: str = Field(min_length=1)
    accepted: bool = False
    blocked: bool = False
    findings: list[ContractFinding] = Field(default_factory=list)
    hard_constraints: list[str] = Field(default_factory=list)
    soft_constraints: list[str] = Field(default_factory=list)
    advisory_constraints: list[str] = Field(default_factory=list)
    proof_requirements: list[str] = Field(default_factory=list)


def _unique(values: Iterable[str]) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})


def _constraints(policy: ExecutionPolicy, brief: TwinBrief) -> list[TwinConstraint]:
    seen: dict[tuple[str, str], TwinConstraint] = {}
    for constraint in [*policy.hard_constraints, *brief.hard_constraints]:
        seen.setdefault((constraint.constraint_id, constraint.text), constraint)
    return [seen[key] for key in sorted(seen)]


def _finding(finding_id: str, severity: str, status: str, message: str, refs: Iterable[str] = (), delegated_to: str | None = None) -> ContractFinding:
    return ContractFinding(
        finding_id=finding_id,
        severity=severity,
        status=status,
        message=message,
        refs=_unique(refs),
        delegated_to=delegated_to,
    )


def evaluate_contracts(
    policy: ExecutionPolicy,
    brief: TwinBrief,
    blast_map: BlastMap,
    *,
    attempted_actions: Iterable[str] = (),
    explicit_test_weakening_approval: bool = False,
) -> ContractSentinelReport:
    """Evaluate hard/soft/advisory constraints before patch acceptance."""
    actions = {str(action).strip().lower() for action in attempted_actions if str(action).strip()}
    constraints = _constraints(policy, brief)
    findings: list[ContractFinding] = []
    proof_requirements = list(blast_map.proof_requirements)

    hard = [c for c in constraints if c.constraint_type == "hard"]
    soft = [c for c in constraints if c.constraint_type == "soft"]
    advisory = [c for c in constraints if c.constraint_type == "advisory"]

    if "bypass_safe_apply" in actions or "direct_workspace_write" in actions:
        findings.append(_finding(
            "contract.safe_apply_bypass",
            "hard",
            "blocked",
            "Patch attempts to bypass Proposal / Safe Apply / Verification boundaries.",
            ["SafeApply", *brief.allowed_refs],
        ))
    if "remote_publish" in actions or "remote_mutation" in actions or "create_pr" in actions:
        findings.append(_finding(
            "contract.remote_publication_requires_approval",
            "hard",
            "blocked",
            "Remote publication or mutation requires explicit approval.",
            ["GitSteward"],
        ))
    if ("weaken_test" in actions or "delete_stale_test" in actions) and not explicit_test_weakening_approval:
        findings.append(_finding(
            "contract.test_or_gate_weakening",
            "hard",
            "blocked",
            "Tests, gates, and stale-test retirement cannot be weakened or deleted without explicit proof and approval.",
            ["TwinProof", "ContractSentinel"],
        ))

    for entry in [*blast_map.direct_impacts, *blast_map.transitive_impacts, *blast_map.side_effects, *blast_map.affected_requirements]:
        if "schema" in entry.hints:
            findings.append(_finding(
                f"contract.schema_guardian_required:{entry.ref}",
                "soft" if entry.constraint_level != "hard" else "hard",
                "needs_proof",
                "Schema-affecting impact requires Schema Guardian compatibility or migration proof.",
                [entry.ref],
                delegated_to="SchemaGuardian",
            ))
            proof_requirements.append(f"Schema Guardian proof required for {entry.ref}")
        if {"state", "ui", "persistence"} & set(entry.hints):
            findings.append(_finding(
                f"contract.state_mirror_required:{entry.ref}",
                "soft" if entry.constraint_level != "hard" else "hard",
                "needs_proof",
                "State/UI/persistence impact requires StateMirror consistency proof.",
                [entry.ref],
                delegated_to="StateMirror",
            ))
            proof_requirements.append(f"StateMirror proof required for {entry.ref}")

    for constraint in hard:
        if not any(constraint.constraint_id in finding.finding_id for finding in findings):
            proof_requirements.append(f"Preserve hard constraint: {constraint.text}")
    for constraint in soft:
        proof_requirements.append(f"Address soft constraint: {constraint.text}")

    blocked = any(finding.status == "blocked" and finding.severity == "hard" for finding in findings)
    return ContractSentinelReport(
        report_id=f"contract_sentinel:{policy.policy_id}:{brief.brief_id}",
        accepted=not blocked,
        blocked=blocked,
        findings=findings,
        hard_constraints=[constraint.text for constraint in hard],
        soft_constraints=[constraint.text for constraint in soft],
        advisory_constraints=[constraint.text for constraint in advisory],
        proof_requirements=_unique(proof_requirements),
    )


__all__ = ["ContractFinding", "ContractSentinelReport", "evaluate_contracts"]
