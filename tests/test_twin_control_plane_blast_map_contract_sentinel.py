from __future__ import annotations

from datetime import datetime, timezone

from agent.model_forge.route_taxonomy import ForgeRoute
from agent.project_twin.contracts import ImpactItem, ImpactResult
from agent.twin_control_plane.blast_map import build_blast_map
from agent.twin_control_plane.contract_sentinel import evaluate_contracts
from agent.twin_control_plane.contracts import (
    ExecutionPolicy,
    InstructionStyle,
    ModelCapabilityMode,
    TwinBrief,
    TwinConstraint,
    TwinInjectionLevel,
    default_hard_constraints,
)


def _item(ref: str, *, confidence: float = 0.85, status: str = "verified", item_type: str = "symbol") -> ImpactItem:
    return ImpactItem(
        canonical_ref=ref,
        item_type=item_type,
        status=status,
        confidence=confidence,
        source_refs=[ref],
        evidence_refs=[f"evidence://{ref}"],
        reason="test impact",
    )


def _impact(**kwargs) -> ImpactResult:
    return ImpactResult(
        project_id="p1",
        twin_revision_id="tw1",
        generated_at=datetime.now(timezone.utc),
        **kwargs,
    )


def _policy() -> ExecutionPolicy:
    return ExecutionPolicy(
        policy_id="policy1",
        route=ForgeRoute.BLUEPRINT_SLICE,
        model_id="local-coder",
        instruction_style=InstructionStyle.CONSTRAINED_PATCH,
        model_capability_mode=ModelCapabilityMode.WEAK_LOCAL,
        twin_injection_level=TwinInjectionLevel.CONSTRAINED_WITH_TESTS,
        required_gates=["SafeApplyBoundary", "RemotePublishApprovalGate", "NoTestWeakening"],
        hard_constraints=default_hard_constraints(),
    )


def _brief() -> TwinBrief:
    return TwinBrief(
        brief_id="brief1",
        allowed_refs=["py://feature.entry"],
        hard_constraints=[
            TwinConstraint(
                constraint_id="preserve_runtime_status",
                text="Preserve runtime status API shape.",
                constraint_type="soft",
                refs=["api://runtime.status"],
            )
        ],
        proof_requirements=["prove feature entry behavior"],
    )


def test_blast_map_represents_direct_transitive_tests_and_state_hints() -> None:
    impact = _impact(
        direct_impacts=[_item("api://proposal.create")],
        transitive_impacts=[_item("ui://portal.runtime_status", confidence=0.7, status="observed")],
        side_effects=[_item("persistence://proposal_store.state")],
        affected_requirements=[_item("requirement://safe_apply_boundary")],
        recommended_tests=[_item("test://proposal_contract")],
        uncertainty=[{"code": "low_confidence_path"}],
    )

    blast = build_blast_map(impact, brief=_brief())

    assert blast.changed_refs == ["py://feature.entry"]
    assert blast.direct_impacts[0].constraint_level == "hard"
    assert {"api"} <= set(blast.direct_impacts[0].hints)
    assert {"state", "ui"} <= set(blast.transitive_impacts[0].hints)
    assert {"persistence", "state"} <= set(blast.side_effects[0].hints)
    assert blast.recommended_tests[0].constraint_level == "hard"
    assert "Run impacted test: test://proposal_contract" in blast.proof_requirements
    assert any("low_confidence_path" in item for item in blast.uncertainty)


def test_contract_sentinel_blocks_safe_apply_remote_and_test_gate_bypass() -> None:
    blast = build_blast_map(_impact(direct_impacts=[_item("py://feature.entry")]), brief=_brief())

    report = evaluate_contracts(
        _policy(),
        _brief(),
        blast,
        attempted_actions=["bypass_safe_apply", "remote_publish", "weaken_test"],
    )

    assert report.blocked is True
    assert report.accepted is False
    finding_ids = {finding.finding_id for finding in report.findings}
    assert "contract.safe_apply_bypass" in finding_ids
    assert "contract.remote_publication_requires_approval" in finding_ids
    assert "contract.test_or_gate_weakening" in finding_ids


def test_contract_sentinel_delegates_schema_state_ui_persistence_findings() -> None:
    impact = _impact(
        direct_impacts=[_item("schema://proposal.artifact")],
        transitive_impacts=[_item("ui://workflow.status_state")],
        side_effects=[_item("persistence://proposal_store")],
    )
    blast = build_blast_map(impact, brief=_brief())

    report = evaluate_contracts(_policy(), _brief(), blast)

    assert report.blocked is False
    delegated = {(finding.delegated_to, tuple(finding.refs)) for finding in report.findings}
    assert ("SchemaGuardian", ("schema://proposal.artifact",)) in delegated
    assert ("StateMirror", ("ui://workflow.status_state",)) in delegated
    assert ("StateMirror", ("persistence://proposal_store",)) in delegated
    assert "Schema Guardian proof required for schema://proposal.artifact" in report.proof_requirements
    assert "StateMirror proof required for ui://workflow.status_state" in report.proof_requirements
    assert "StateMirror proof required for persistence://proposal_store" in report.proof_requirements


def test_contract_sentinel_classifies_soft_constraints_without_blocking() -> None:
    blast = build_blast_map(_impact(), brief=_brief())

    report = evaluate_contracts(_policy(), _brief(), blast)

    assert report.accepted is True
    assert report.blocked is False
    assert "Preserve runtime status API shape." in report.soft_constraints
    assert "Address soft constraint: Preserve runtime status API shape." in report.proof_requirements
