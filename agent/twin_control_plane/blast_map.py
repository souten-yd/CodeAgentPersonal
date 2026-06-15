"""BlastMap projection from Project Twin impact evidence.

BlastMap reuses existing Project Twin ImpactResult data. It does not inspect the
repository directly and does not replace the Twin impact query.
"""
from __future__ import annotations

from typing import Iterable

from pydantic import Field

from agent.project_twin.contracts import ImpactItem, ImpactResult
from agent.twin_control_plane.contracts import TwinBrief, TwinControlPlaneModel


class BlastMapEntry(TwinControlPlaneModel):
    ref: str = Field(min_length=1)
    impact_scope: str = Field(min_length=1)  # changed | direct | transitive | test | side_effect | requirement
    constraint_level: str = "advisory"       # hard | soft | advisory
    confidence: float = Field(ge=0.0, le=1.0)
    hints: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    reason: str = ""


class BlastMap(TwinControlPlaneModel):
    blast_map_id: str = Field(min_length=1)
    changed_refs: list[str] = Field(default_factory=list)
    direct_impacts: list[BlastMapEntry] = Field(default_factory=list)
    transitive_impacts: list[BlastMapEntry] = Field(default_factory=list)
    recommended_tests: list[BlastMapEntry] = Field(default_factory=list)
    side_effects: list[BlastMapEntry] = Field(default_factory=list)
    affected_requirements: list[BlastMapEntry] = Field(default_factory=list)
    uncertainty: list[str] = Field(default_factory=list)
    proof_requirements: list[str] = Field(default_factory=list)


def _unique(values: Iterable[str]) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})


def _hints_for_ref(ref: str) -> list[str]:
    hints: list[str] = []
    low = ref.lower()
    if ref.startswith("api://") or "api" in low:
        hints.append("api")
    if ref.startswith("ui://") or "ui" in low or "portal" in low or "web/" in low:
        hints.append("ui")
    if ref.startswith("schema://") or "schema" in low or "artifact" in low or "payload" in low:
        hints.append("schema")
    if ref.startswith("persistence://") or "store" in low or "sqlite" in low or "db" in low:
        hints.append("persistence")
    if "state" in low or "status" in low or "workflow" in low:
        hints.append("state")
    if ref.startswith("test://") or "test" in low:
        hints.append("test")
    return _unique(hints)


def _constraint_level(item: ImpactItem, *, scope: str) -> str:
    hints = set(_hints_for_ref(item.canonical_ref))
    if scope in {"requirement", "test"}:
        return "hard"
    if item.status in {"verified", "user_approved"} and item.confidence >= 0.75:
        return "hard" if hints & {"api", "schema", "persistence", "state"} else "soft"
    if item.status in {"observed"} and item.confidence >= 0.6:
        return "soft"
    return "advisory"


def _entry(item: ImpactItem, *, scope: str) -> BlastMapEntry:
    return BlastMapEntry(
        ref=item.canonical_ref,
        impact_scope=scope,
        constraint_level=_constraint_level(item, scope=scope),
        confidence=item.confidence,
        hints=_hints_for_ref(item.canonical_ref),
        evidence_refs=list(item.evidence_refs),
        reason=item.reason or f"project_twin:{scope}",
    )


def build_blast_map(
    impact: ImpactResult,
    *,
    brief: TwinBrief | None = None,
    changed_refs: Iterable[str] = (),
) -> BlastMap:
    """Build a BlastMap from an existing Project Twin ImpactResult."""
    changed = _unique(changed_refs or (brief.allowed_refs if brief else []) or (brief.impacted_refs if brief else []))
    direct = [_entry(item, scope="direct") for item in impact.direct_impacts]
    transitive = [_entry(item, scope="transitive") for item in impact.transitive_impacts]
    tests = [_entry(item, scope="test") for item in impact.recommended_tests]
    side_effects = [_entry(item, scope="side_effect") for item in impact.side_effects]
    requirements = [_entry(item, scope="requirement") for item in impact.affected_requirements]

    proof = []
    for entry in [*direct, *transitive, *side_effects, *requirements]:
        if entry.constraint_level in {"hard", "soft"}:
            proof.append(f"Prove {entry.impact_scope} impact remains valid: {entry.ref}")
    for entry in tests:
        proof.append(f"Run impacted test: {entry.ref}")
    if brief:
        proof.extend(brief.proof_requirements)

    return BlastMap(
        blast_map_id=f"blast_map:{impact.project_id}:{impact.twin_revision_id or 'current'}",
        changed_refs=changed,
        direct_impacts=direct,
        transitive_impacts=transitive,
        recommended_tests=tests,
        side_effects=side_effects,
        affected_requirements=requirements,
        uncertainty=_unique(str(item) for item in impact.uncertainty),
        proof_requirements=_unique(proof),
    )


__all__ = ["BlastMap", "BlastMapEntry", "build_blast_map"]
