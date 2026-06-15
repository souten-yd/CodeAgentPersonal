"""Integration Impact Gate for Feature/Module Genesis.

The gate compares Feature Genesis intent with existing Project Twin impact
evidence. It reports integration points, contracts to preserve, missing tests,
and proof requirements; uncertain Twin evidence remains advisory.
"""
from __future__ import annotations

from typing import Iterable

from pydantic import Field

from agent.project_twin.contracts import ImpactItem, ImpactResult
from agent.twin_control_plane.contracts import TwinBrief, TwinControlPlaneModel
from agent.twin_control_plane.genesis import GenesisClassification, GenesisKind


class IntegrationPoint(TwinControlPlaneModel):
    ref: str = Field(min_length=1)
    source: str = Field(min_length=1)
    impact_type: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    advisory: bool = False
    reason: str = ""
    evidence_refs: list[str] = Field(default_factory=list)


class IntegrationImpactReport(TwinControlPlaneModel):
    report_id: str = Field(min_length=1)
    genesis_kind: GenesisKind
    changed_refs: list[str] = Field(default_factory=list)
    integration_points: list[IntegrationPoint] = Field(default_factory=list)
    contracts_to_preserve: list[str] = Field(default_factory=list)
    missing_tests: list[str] = Field(default_factory=list)
    proof_requirements: list[str] = Field(default_factory=list)
    uncertainty: list[str] = Field(default_factory=list)
    advisory_only: bool = False
    blocked: bool = False
    reasons: list[str] = Field(default_factory=list)


def _unique(values: Iterable[str]) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})


def _item_point(item: ImpactItem, *, source: str, impact_type: str, advisory_threshold: float) -> IntegrationPoint:
    advisory = item.confidence < advisory_threshold or item.status in {"inferred", "declared"}
    reason = item.reason or f"{source}:{impact_type}"
    if advisory:
        reason = f"advisory_confidence:{reason}"
    return IntegrationPoint(
        ref=item.canonical_ref,
        source=source,
        impact_type=impact_type,
        confidence=item.confidence,
        advisory=advisory,
        reason=reason,
        evidence_refs=list(item.evidence_refs),
    )


def _points_from_impact(impact: ImpactResult, *, advisory_threshold: float) -> list[IntegrationPoint]:
    points: list[IntegrationPoint] = []
    for item in impact.direct_impacts:
        points.append(_item_point(item, source="project_twin", impact_type="direct", advisory_threshold=advisory_threshold))
    for item in impact.transitive_impacts:
        points.append(_item_point(item, source="project_twin", impact_type="transitive", advisory_threshold=advisory_threshold))
    for item in impact.side_effects:
        points.append(_item_point(item, source="project_twin", impact_type="side_effect", advisory_threshold=advisory_threshold))
    for item in impact.affected_requirements:
        points.append(_item_point(item, source="project_twin", impact_type="requirement", advisory_threshold=advisory_threshold))

    deduped: dict[tuple[str, str], IntegrationPoint] = {}
    for point in points:
        key = (point.ref, point.impact_type)
        existing = deduped.get(key)
        if existing is None or point.confidence > existing.confidence:
            deduped[key] = point
    return [deduped[key] for key in sorted(deduped)]


def assess_integration_impact(
    classification: GenesisClassification,
    brief: TwinBrief,
    impact: ImpactResult,
    *,
    changed_refs: Iterable[str] = (),
    advisory_threshold: float = 0.55,
) -> IntegrationImpactReport:
    """Assess integration risks using existing Twin impact evidence."""
    points = _points_from_impact(impact, advisory_threshold=advisory_threshold)
    recommended_tests = _unique(item.canonical_ref for item in impact.recommended_tests)
    required_tests = _unique(brief.required_tests)
    changed = _unique(changed_refs or brief.allowed_refs or brief.impacted_refs)

    missing_tests: list[str] = []
    if points and not recommended_tests and not required_tests:
        missing_tests.append("integration://missing_recommended_tests")

    impacted_refs = _unique(point.ref for point in points)
    contracts = _unique([
        *brief.contracts_to_preserve,
        *(item.canonical_ref for item in impact.affected_requirements),
    ])

    proof_requirements = _unique([
        *brief.proof_requirements,
        *(f"Prove integration point remains compatible: {ref}" for ref in impacted_refs),
        *(f"Run or justify missing integration test: {test}" for test in missing_tests),
    ])
    for test in recommended_tests:
        if test not in required_tests:
            proof_requirements.append(f"Run Twin-recommended test: {test}")
    proof_requirements = _unique(proof_requirements)

    uncertainty = _unique([
        *(str(item) for item in impact.uncertainty),
        *(point.reason for point in points if point.advisory),
    ])
    advisory_only = bool(points) and all(point.advisory for point in points)
    blocked = bool(missing_tests)
    reasons = [
        f"genesis_kind={classification.genesis_kind.value}",
        f"integration_points={len(points)}",
    ]
    if advisory_only:
        reasons.append("all_integration_points_advisory")
    if missing_tests:
        reasons.append("missing_integration_tests")

    return IntegrationImpactReport(
        report_id=f"integration_impact:{classification.genesis_kind.value}:{impact.project_id}:{impact.twin_revision_id or 'current'}",
        genesis_kind=classification.genesis_kind,
        changed_refs=changed,
        integration_points=points,
        contracts_to_preserve=contracts,
        missing_tests=missing_tests,
        proof_requirements=proof_requirements,
        uncertainty=uncertainty,
        advisory_only=advisory_only,
        blocked=blocked,
        reasons=reasons,
    )


__all__ = [
    "IntegrationImpactReport",
    "IntegrationPoint",
    "assess_integration_impact",
]
