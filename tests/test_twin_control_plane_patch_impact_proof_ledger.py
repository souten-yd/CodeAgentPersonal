from __future__ import annotations

from agent.git_steward.contracts import GitStewardResult
from agent.model_forge.route_taxonomy import ForgeRoute
from agent.twin_control_plane.blast_map import BlastMap
from agent.twin_control_plane.contract_sentinel import ContractFinding, ContractSentinelReport
from agent.twin_control_plane.contracts import (
    ExecutionPolicy,
    InstructionStyle,
    ModelCapabilityMode,
    TwinBrief,
    TwinInjectionLevel,
)
from agent.twin_control_plane.patch_impact_gate import PatchGateDecision, VerificationEvidence, evaluate_patch_impact
from agent.twin_control_plane.proof_ledger import ProofLedger, append_proof_entry, create_proof_ledger_entry
from agent.twin_control_plane.schema_guardian import SchemaGuardianReport
from agent.twin_control_plane.state_mirror import StateMirrorReport
from agent.twin_control_plane.twinproof import TwinProofReport


def _policy() -> ExecutionPolicy:
    return ExecutionPolicy(
        policy_id="policy1",
        route=ForgeRoute.BLUEPRINT_SLICE,
        model_id="local-coder",
        instruction_style=InstructionStyle.CONSTRAINED_PATCH,
        model_capability_mode=ModelCapabilityMode.WEAK_LOCAL,
        twin_injection_level=TwinInjectionLevel.CONSTRAINED_WITH_TESTS,
        required_gates=["TwinProof", "ContractSentinel"],
    )


def _brief() -> TwinBrief:
    return TwinBrief(brief_id="brief1", proof_requirements=["prove behavior"])


def _git() -> GitStewardResult:
    return GitStewardResult(operation="commit", status="ok", commit_sha="abc123", changed_files=["agent/x.py"])


def test_patch_impact_gate_accepts_when_all_required_evidence_passes() -> None:
    report = evaluate_patch_impact(
        policy=_policy(),
        brief=_brief(),
        base_ref="main",
        head_ref="abc123",
        git_result=_git(),
        before_twin_revision_id="tw-before",
        after_twin_revision_id="tw-after",
        verification=[VerificationEvidence(evidence_id="test://ok", status="passed", command="pytest")],
        blast_map=BlastMap(blast_map_id="blast1", proof_requirements=["prove blast"]),
        contract_sentinel=ContractSentinelReport(report_id="sentinel1", accepted=True),
        schema_guardian=SchemaGuardianReport(report_id="schema1", accepted=True),
        state_mirror=StateMirrorReport(report_id="state1", accepted=True),
        twinproof=TwinProofReport(report_id="proof1", accepted=True),
    )

    assert report.decision == PatchGateDecision.ACCEPTED
    assert report.accepted is True
    assert report.changed_files == ["agent/x.py"]
    assert report.passed_evidence_refs == ["test://ok"]
    assert "blast1" in report.gate_refs


def test_patch_impact_gate_blocks_on_hard_contract_boundary() -> None:
    sentinel = ContractSentinelReport(
        report_id="sentinel1",
        accepted=False,
        blocked=True,
        findings=[
            ContractFinding(
                finding_id="contract.safe_apply_bypass",
                severity="hard",
                status="blocked",
                message="blocked",
            )
        ],
    )

    report = evaluate_patch_impact(
        policy=_policy(),
        brief=_brief(),
        base_ref="main",
        head_ref="abc123",
        git_result=_git(),
        before_twin_revision_id="tw-before",
        after_twin_revision_id="tw-after",
        verification=[VerificationEvidence(evidence_id="test://ok", status="passed")],
        contract_sentinel=sentinel,
    )

    assert report.decision == PatchGateDecision.BLOCKED
    assert report.blocked is True
    assert "contract_sentinel_blocked" in report.blocked_reasons


def test_patch_impact_gate_needs_repair_for_failed_unavailable_or_missing_proof() -> None:
    report = evaluate_patch_impact(
        policy=_policy(),
        brief=_brief(),
        base_ref="main",
        head_ref="abc123",
        git_result=_git(),
        before_twin_revision_id="tw-before",
        after_twin_revision_id="",
        verification=[
            VerificationEvidence(evidence_id="test://failed", status="failed"),
            VerificationEvidence(evidence_id="runtime://smoke", status="unavailable"),
        ],
        schema_guardian=SchemaGuardianReport(report_id="schema1", accepted=False, migration_required=True),
        state_mirror=StateMirrorReport(report_id="state1", accepted=False, unavailable_evidence=["runtime.state"]),
        twinproof=TwinProofReport(report_id="proof1", accepted=False, proof_requirements=["add coverage"]),
    )

    assert report.decision == PatchGateDecision.NEEDS_REPAIR
    assert report.needs_repair is True
    assert "verification_failed" in report.repair_reasons
    assert "verification_unavailable" in report.repair_reasons
    assert "twin_revision_evidence_missing" in report.repair_reasons
    assert report.failed_evidence_refs == ["test://failed"]
    assert report.unavailable_evidence_refs == ["runtime://smoke"]


def test_proof_ledger_entry_explains_decision_and_append_is_idempotent() -> None:
    patch_report = evaluate_patch_impact(
        policy=_policy(),
        brief=_brief(),
        base_ref="main",
        head_ref="abc123",
        git_result=_git(),
        before_twin_revision_id="tw-before",
        after_twin_revision_id="tw-after",
        verification=[VerificationEvidence(evidence_id="test://ok", status="passed")],
        contract_sentinel=ContractSentinelReport(report_id="sentinel1", accepted=True),
        twinproof=TwinProofReport(report_id="proof1", accepted=True),
    )
    entry = create_proof_ledger_entry(
        requirement_ref="req://1",
        plan_item_ref="plan://item1",
        policy=_policy(),
        brief=_brief(),
        patch_report=patch_report,
    )
    ledger = append_proof_entry(ProofLedger(ledger_id="ledger1"), entry)
    ledger = append_proof_entry(ledger, entry)

    assert len(ledger.entries) == 1
    stored = ledger.entries[0]
    assert stored.requirement_ref == "req://1"
    assert stored.plan_item_ref == "plan://item1"
    assert stored.git_commit_sha == "abc123"
    assert stored.before_twin_revision_id == "tw-before"
    assert stored.after_twin_revision_id == "tw-after"
    assert stored.test_refs == ["test://ok"]
    assert stored.gate_refs == ["proof1", "sentinel1"]
    assert stored.accepted is True
