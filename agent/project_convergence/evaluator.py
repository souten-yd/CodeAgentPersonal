"""Multidimensional convergence evaluator (PI-13).

Evaluates each Blueprint element against one immutable Actual Twin revision across the
structural / interface / verification-runtime / delivery dimensions and assigns one of the
distinct states: absent, partial, materialized, observed, verified, divergent, blocked,
stale. File existence never implies behavior verification, and stale evidence cannot satisfy
mandatory verification. Pure and reproducible; consumes only public data.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from agent.architecture_blueprint.contracts import BlueprintRevision
from agent.architecture_blueprint.mapping import ActualEntry, MappingHint
from agent.project_convergence.contracts import (
    ConvergenceMismatch,
    ConvergenceReport,
    ElementConvergenceResult,
)
from agent.project_convergence.matcher import match_elements
from agent.project_intelligence.contracts import GapSummary, IntelligenceDiagnostic


@dataclass
class VerificationEvidence:
    """Public verification summary for an actual ref (from PI-8 runtime/reconciliation)."""
    result: str  # passed | failed | observed | unavailable
    source_revision: str | None = None
    evidence_refs: list[str] = field(default_factory=list)


# States
ABSENT = "absent"
PARTIAL = "partial"
MATERIALIZED = "materialized"
OBSERVED = "observed"
VERIFIED = "verified"
DIVERGENT = "divergent"
BLOCKED = "blocked"
STALE = "stale"


def _interface_mismatch(el, entry: ActualEntry | None) -> ConvergenceMismatch | None:
    """A coarse interface check: a declared interface kind must match the actual kind."""
    expected_ifaces = (el.properties or {}).get("interfaces") or []
    if expected_ifaces and entry is not None and entry.kind:
        # If the element expects an interface but the actual is a plain file with no symbol,
        # that's a divergence (interface not realized).
        if entry.kind == "file" and "file" not in [str(i).lower() for i in expected_ifaces]:
            return ConvergenceMismatch(dimension="interface", expected_ref=el.canonical_ref,
                                       actual_ref=entry.ref, detail="declared interface not realized")
    return None


def evaluate_element(
    el,
    match,
    *,
    current_twin_revision_id: str | None,
    snapshot_by_ref: dict[str, ActualEntry],
    verification: dict[str, VerificationEvidence],
) -> ElementConvergenceResult:
    matched = match.matched_actual_refs
    missing = match.missing_actual_refs
    mismatches: list[ConvergenceMismatch] = []
    evidence: list[str] = []

    # blocked / absent
    if not matched:
        state = BLOCKED if el.mandatory else ABSENT
        return ElementConvergenceResult(
            blueprint_element_id=el.element_id, state=state, matched_actual_refs=[],
            missing_actual_refs=missing or [r for r in el.expected_actual_refs],
            evidence_refs=[], mismatches=[], confidence=0.8 if state == BLOCKED else 0.6,
        )

    primary = matched[0]
    entry = snapshot_by_ref.get(primary)

    # interface divergence
    im = _interface_mismatch(el, entry)
    if im:
        mismatches.append(im)

    # verification / runtime dimension
    ev = verification.get(primary)
    state = MATERIALIZED  # structural presence only (file exists != verified)
    confidence = 0.6
    if ev is not None:
        evidence = list(ev.evidence_refs)
        if ev.result == "failed":
            mismatches.append(ConvergenceMismatch(dimension="runtime", actual_ref=primary,
                                                  detail="runtime observation failed"))
            state = DIVERGENT
            confidence = 0.8
        elif ev.result == "passed":
            if ev.source_revision == current_twin_revision_id:
                state = VERIFIED
                confidence = 0.95
            else:
                # stale evidence cannot satisfy verification.
                state = STALE
                confidence = 0.5
                mismatches.append(ConvergenceMismatch(dimension="verification", actual_ref=primary,
                                                      detail="evidence from a different revision (stale)"))
        elif ev.result == "observed":
            state = OBSERVED
            confidence = 0.6
        elif ev.result == "unavailable":
            state = MATERIALIZED  # unavailable never upgrades to verified
            confidence = 0.5

    # interface divergence overrides a non-failed structural state
    if im and state not in (DIVERGENT,):
        state = DIVERGENT
        confidence = max(confidence, 0.7)

    # partial: some expected refs still missing
    if missing and state in (MATERIALIZED,):
        state = PARTIAL
        confidence = 0.5

    return ElementConvergenceResult(
        blueprint_element_id=el.element_id, state=state, matched_actual_refs=matched,
        missing_actual_refs=missing, evidence_refs=evidence, mismatches=mismatches,
        confidence=confidence,
    )


def evaluate_convergence(
    revision: BlueprintRevision,
    snapshot: list[ActualEntry],
    *,
    project_id: str,
    workspace_id: str,
    twin_revision_id: str,
    verification: dict[str, VerificationEvidence] | None = None,
    hints: list[MappingHint] | None = None,
    now: datetime | None = None,
) -> ConvergenceReport:
    now = now or datetime.now(timezone.utc)
    verification = verification or {}
    snapshot_by_ref = {e.ref: e for e in snapshot}
    matches = match_elements(revision, snapshot, twin_revision_id=twin_revision_id, hints=hints)
    by_id = {e.element_id: e for e in revision.elements}

    results: list[ElementConvergenceResult] = []
    mandatory_gaps: list[GapSummary] = []
    optional_gaps: list[GapSummary] = []
    stale_evidence: list[str] = []

    for eid in sorted(by_id):
        el = by_id[eid]
        res = evaluate_element(el, matches[eid], current_twin_revision_id=twin_revision_id,
                               snapshot_by_ref=snapshot_by_ref, verification=verification)
        results.append(res)
        if res.state == STALE:
            stale_evidence.extend(res.evidence_refs or [res.blueprint_element_id])
        if res.state in (ABSENT, PARTIAL, BLOCKED, DIVERGENT, STALE):
            gap = GapSummary(gap_id=f"gap:{eid}", blueprint_element_id=eid,
                             description=f"{el.name or eid}: {res.state}", mandatory=el.mandatory,
                             missing_refs=res.missing_actual_refs)
            (mandatory_gaps if el.mandatory else optional_gaps).append(gap)

    coverage: dict[str, object] = {
        "total_elements": len(results),
        "verified": sum(1 for r in results if r.state == VERIFIED),
        "mandatory_gaps": len(mandatory_gaps),
    }
    return ConvergenceReport(
        report_id=f"conv:{uuid.uuid4().hex[:10]}", project_id=project_id, workspace_id=workspace_id,
        blueprint_revision_id=revision.revision_id, actual_twin_revision_id=twin_revision_id,
        element_results=results, mandatory_gaps=mandatory_gaps, optional_gaps=optional_gaps,
        stale_evidence=sorted(set(stale_evidence)), requirement_coverage=coverage,
        diagnostics=[], generated_at=now,
    )
