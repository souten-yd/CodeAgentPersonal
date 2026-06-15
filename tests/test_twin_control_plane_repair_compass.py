from __future__ import annotations

from agent.model_forge.route_taxonomy import ForgeRoute
from agent.twin_control_plane.contracts import (
    ExecutionPolicy,
    InstructionStyle,
    ModelCapabilityMode,
    TwinBrief,
    TwinConstraint,
    TwinInjectionLevel,
)
from agent.twin_control_plane.patch_impact_gate import PatchGateDecision, PatchImpactReport
from agent.twin_control_plane.proof_ledger import ProofLedgerEntry
from agent.twin_control_plane.repair_compass import RepairCategory, build_repair_compass


def _policy() -> ExecutionPolicy:
    return ExecutionPolicy(
        policy_id="policy1",
        route=ForgeRoute.BLUEPRINT_SLICE,
        model_id="local-coder",
        instruction_style=InstructionStyle.REPAIR_COMPASS,
        model_capability_mode=ModelCapabilityMode.WEAK_LOCAL,
        twin_injection_level=TwinInjectionLevel.STRICT_INTERFACE_AND_REPAIR,
        required_gates=["TwinProof", "PatchImpactGate"],
        hard_constraints=[
            TwinConstraint(
                constraint_id="safe_apply_required",
                text="File mutation must remain behind Safe Apply.",
                refs=["SafeApply"],
            )
        ],
    )


def _brief() -> TwinBrief:
    return TwinBrief(
        brief_id="brief1",
        allowed_refs=["agent/service.py", "tests/test_service.py"],
        forbidden_refs=["agent/unrelated.py"],
        required_tests=["tests/test_service.py"],
        proof_requirements=["Prove service behavior."],
    )


def _patch_report(**updates: object) -> PatchImpactReport:
    data = {
        "report_id": "patch_impact:policy1:brief1:abc123",
        "decision": PatchGateDecision.NEEDS_REPAIR,
        "needs_repair": True,
        "policy_id": "policy1",
        "brief_id": "brief1",
        "base_ref": "main",
        "head_ref": "abc123",
        "changed_files": ["agent/service.py"],
        "failed_evidence_refs": [],
        "unavailable_evidence_refs": [],
        "blocked_reasons": [],
        "repair_reasons": [],
        "proof_requirements": [],
        "gate_refs": ["proof1"],
    }
    data.update(updates)
    return PatchImpactReport(**data)


def test_repair_compass_targets_failed_verification_without_weakening_tests() -> None:
    report = _patch_report(
        failed_evidence_refs=["test://service"],
        repair_reasons=["verification_failed", "twinproof_needs_proof"],
        proof_requirements=["Add focused test coverage for service edge case."],
    )

    compass = build_repair_compass(policy=_policy(), brief=_brief(), patch_report=report)

    assert compass.local_minimal_repair_required is True
    assert compass.allowed_refs == ["agent/service.py", "tests/test_service.py"]
    assert compass.forbidden_refs == ["agent/unrelated.py"]
    assert compass.product_regression_refs == ["test://service"]
    product = [item for item in compass.instructions if item.category == RepairCategory.PRODUCT_REGRESSION][0]
    assert product.refs == ["test://service"]
    assert any("Keep the failing test" in requirement for requirement in product.proof_requirements)
    assert any("Do not weaken" in action for action in compass.prohibited_actions)


def test_repair_compass_keeps_unavailable_environment_separate_from_product_regression() -> None:
    report = _patch_report(
        unavailable_evidence_refs=["runtime://portal-smoke"],
        repair_reasons=["verification_unavailable"],
    )

    compass = build_repair_compass(policy=_policy(), brief=_brief(), patch_report=report)

    assert compass.product_regression_refs == []
    assert compass.environment_unavailable_refs == ["runtime://portal-smoke"]
    environment = [item for item in compass.instructions if item.category == RepairCategory.ENVIRONMENT_UNAVAILABLE][0]
    assert environment.refs == ["runtime://portal-smoke"]
    assert any("Do not change product code solely" in requirement for requirement in environment.proof_requirements)


def test_repair_compass_preserves_hard_boundaries_for_blocked_gate() -> None:
    report = _patch_report(
        decision=PatchGateDecision.BLOCKED,
        blocked=True,
        needs_repair=False,
        blocked_reasons=["contract_sentinel_blocked"],
        gate_refs=["sentinel1"],
    )

    compass = build_repair_compass(policy=_policy(), brief=_brief(), patch_report=report)

    assert compass.hard_constraints == ["File mutation must remain behind Safe Apply."]
    boundary = [item for item in compass.instructions if item.category == RepairCategory.HARD_BOUNDARY][0]
    assert boundary.refs == ["contract_sentinel_blocked", "sentinel1"]
    assert any("Safe Apply" in requirement for requirement in boundary.proof_requirements)
    assert any("Do not push" in action for action in boundary.prohibited_actions)


def test_repair_compass_includes_anti_pattern_hints_as_advisory() -> None:
    report = _patch_report(
        repair_reasons=["verification_missing", "schema_guardian_needs_proof"],
        proof_requirements=["Schema Guardian proof required for agent/service.py"],
    )
    ledger = ProofLedgerEntry(
        entry_id="ledger1",
        gate_refs=["schema1"],
        proof_requirements=["Schema Guardian proof required for agent/service.py"],
    )

    compass = build_repair_compass(
        policy=_policy(),
        brief=_brief(),
        patch_report=report,
        ledger_entry=ledger,
        anti_pattern_hints=["This route often forgets migration proof."],
    )

    assert compass.anti_pattern_hints == [
        "Advisory anti-pattern hint, not absolute truth: This route often forgets migration proof."
    ]
    categories = {instruction.category for instruction in compass.instructions}
    assert RepairCategory.MISSING_VERIFICATION in categories
    assert RepairCategory.SCHEMA_PROOF in categories
