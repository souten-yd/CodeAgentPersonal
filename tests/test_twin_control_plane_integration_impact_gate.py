from __future__ import annotations

from datetime import datetime, timezone

from agent.project_intelligence.contracts import ProjectMode
from agent.project_twin.contracts import ImpactItem, ImpactResult
from agent.twin_control_plane.contracts import TwinBrief
from agent.twin_control_plane.genesis import GenesisKind, classify_genesis
from agent.twin_control_plane.integration_impact_gate import assess_integration_impact


def _item(ref: str, *, confidence: float = 0.8, status: str = "verified", reason: str = "") -> ImpactItem:
    return ImpactItem(
        canonical_ref=ref,
        item_type="symbol",
        status=status,
        confidence=confidence,
        source_refs=[ref],
        evidence_refs=[f"evidence://{ref}"],
        reason=reason,
    )


def _impact(**kwargs) -> ImpactResult:
    return ImpactResult(
        project_id="p1",
        twin_revision_id="tw1",
        generated_at=datetime.now(timezone.utc),
        **kwargs,
    )


def test_integration_gate_reports_existing_integration_points_and_contracts() -> None:
    classification = classify_genesis(ProjectMode.EXISTING, task_category="feature")
    brief = TwinBrief(
        brief_id="brief1",
        allowed_refs=["py://new_feature.create"],
        contracts_to_preserve=["contract://proposal.safe_apply"],
        proof_requirements=["prove proposal still uses Safe Apply"],
    )
    impact = _impact(
        direct_impacts=[_item("py://proposal.create")],
        transitive_impacts=[_item("py://portal.runtime_status")],
        affected_requirements=[_item("requirement://safe_apply_boundary")],
        recommended_tests=[_item("test://proposal_safe_apply")],
    )

    report = assess_integration_impact(classification, brief, impact)

    assert report.genesis_kind == GenesisKind.FEATURE
    assert "py://proposal.create" in {point.ref for point in report.integration_points}
    assert "py://portal.runtime_status" in {point.ref for point in report.integration_points}
    assert "contract://proposal.safe_apply" in report.contracts_to_preserve
    assert "requirement://safe_apply_boundary" in report.contracts_to_preserve
    assert "Run Twin-recommended test: test://proposal_safe_apply" in report.proof_requirements
    assert report.blocked is False


def test_integration_gate_blocks_when_impacts_have_no_tests_or_required_tests() -> None:
    classification = classify_genesis(ProjectMode.EXISTING, task_category="feature")
    brief = TwinBrief(brief_id="brief1", allowed_refs=["py://new_feature.create"])
    impact = _impact(direct_impacts=[_item("py://existing.integration")])

    report = assess_integration_impact(classification, brief, impact)

    assert report.blocked is True
    assert "integration://missing_recommended_tests" in report.missing_tests
    assert "Run or justify missing integration test: integration://missing_recommended_tests" in report.proof_requirements
    assert "missing_integration_tests" in report.reasons


def test_integration_gate_uses_advisory_wording_for_uncertain_impacts() -> None:
    classification = classify_genesis(
        ProjectMode.EXISTING,
        task_category="api",
        target_refs=["api://billing.create"],
    )
    brief = TwinBrief(brief_id="brief1", required_tests=["test://billing_contract"])
    impact = _impact(
        direct_impacts=[_item("api://existing.billing", confidence=0.4, status="inferred", reason="heuristic edge")],
        uncertainty=[{"code": "low_confidence_path", "ref": "api://existing.billing"}],
    )

    report = assess_integration_impact(classification, brief, impact)

    assert report.genesis_kind == GenesisKind.MODULE
    assert report.advisory_only is True
    assert report.blocked is False
    assert report.integration_points[0].advisory is True
    assert any("advisory_confidence" in item for item in report.uncertainty)
    assert any("low_confidence_path" in item for item in report.uncertainty)


def test_integration_gate_preserves_changed_refs_from_brief_when_not_explicit() -> None:
    classification = classify_genesis(ProjectMode.EXISTING, task_category="feature")
    brief = TwinBrief(brief_id="brief1", allowed_refs=["py://feature.entry"])
    impact = _impact()

    report = assess_integration_impact(classification, brief, impact)

    assert report.changed_refs == ["py://feature.entry"]
    assert report.integration_points == []
    assert report.blocked is False
