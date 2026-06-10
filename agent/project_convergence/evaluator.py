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

MATERIALIZATION_ONLY = "materialization_only"
STATIC_CONTRACT = "static_contract"
VERIFIED_TEST = "verified_test"
RUNTIME_OBSERVATION = "runtime_observation"
PERFORMANCE_MEASUREMENT = "performance_measurement"
MANUAL_CRITICAL_DECISION = "manual_critical_decision"


def _evidence_policy(el) -> str:
    policy = (el.properties or {}).get("evidence_policy")
    if policy:
        return str(policy)
    if el.element_type == "nfr":
        return PERFORMANCE_MEASUREMENT
    if el.element_type in {"runtime_scenario", "preserve_behavior"}:
        return RUNTIME_OBSERVATION
    if el.element_type in {"test_contract", "command", "entrypoint"}:
        return VERIFIED_TEST
    if el.element_type in {"api_route", "schema", "configuration", "dependency"}:
        return STATIC_CONTRACT
    if el.verification_contract_ids:
        return VERIFIED_TEST
    return MATERIALIZATION_ONLY


def _required_evidence_refs(el) -> list[str]:
    refs = list(el.verification_contract_ids)
    policy = _evidence_policy(el)
    if policy != MATERIALIZATION_ONLY and not refs:
        refs.append(f"evidence:{el.element_id}")
    return refs


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


def _typed_contract_mismatch(el, entry: ActualEntry | None) -> ConvergenceMismatch | None:
    if entry is None:
        return None
    expected_kinds = {
        "api_route": {"route", "api_route"},
        "schema": {"schema", "data_model", "table"},
        "configuration": {"configuration", "config"},
        "dependency": {"dependency", "package"},
        "runtime_scenario": {"runtime", "test", "scenario"},
        "preserve_behavior": {"behavior", "test", "runtime"},
        "nfr": {"nfr", "performance", "metric"},
        "state": {"state"},
        "event": {"event"},
        "recovery": {"recovery"},
        "resource": {"resource", "side_effect"},
    }.get(el.element_type)
    if expected_kinds and entry.kind and entry.kind not in expected_kinds:
        dimension = {
            "api_route": "api_schema",
            "schema": "schema",
            "configuration": "configuration",
            "dependency": "dependency",
            "runtime_scenario": "behavior",
            "preserve_behavior": "behavior",
            "nfr": "nfr",
            "state": "state",
            "event": "event",
            "recovery": "recovery",
            "resource": "resource",
        }[el.element_type]
        return ConvergenceMismatch(
            dimension=dimension,
            expected_ref=el.canonical_ref,
            actual_ref=entry.ref,
            detail=f"expected {el.element_type} actual kind, got {entry.kind}",
        )
    return None


def _policy_satisfied(result: ElementConvergenceResult) -> bool:
    if result.mismatches or result.state in {ABSENT, PARTIAL, BLOCKED, DIVERGENT, STALE}:
        return False
    if result.evidence_policy == MATERIALIZATION_ONLY:
        return result.state in {MATERIALIZED, OBSERVED, VERIFIED}
    return result.state == VERIFIED


def evaluate_element(
    el,
    match,
    *,
    current_twin_revision_id: str | None,
    current_source_revision_id: str | None,
    snapshot_by_ref: dict[str, ActualEntry],
    verification: dict[str, VerificationEvidence],
) -> ElementConvergenceResult:
    matched = match.matched_actual_refs
    missing = match.missing_actual_refs
    mismatches: list[ConvergenceMismatch] = []
    evidence: list[str] = []
    evidence_policy = _evidence_policy(el)
    required_evidence = _required_evidence_refs(el)

    # blocked / absent
    if not matched:
        state = BLOCKED if el.mandatory else ABSENT
        return ElementConvergenceResult(
            blueprint_element_id=el.element_id, state=state, evidence_policy=evidence_policy,
            required_evidence_refs=required_evidence, matched_actual_refs=[],
            missing_actual_refs=missing or [r for r in el.expected_actual_refs],
            evidence_refs=[], mismatches=[], confidence=0.8 if state == BLOCKED else 0.6,
        )

    primary = matched[0]
    entry = snapshot_by_ref.get(primary)

    # interface divergence
    im = _interface_mismatch(el, entry)
    if im:
        mismatches.append(im)
    typed = _typed_contract_mismatch(el, entry)
    if typed:
        mismatches.append(typed)

    # verification / runtime dimension
    ev = verification.get(primary)
    state = MATERIALIZED  # structural presence only (file exists != verified)
    confidence = 0.6
    freshness = "not_required" if not required_evidence else "unavailable"
    if ev is not None:
        evidence = list(ev.evidence_refs)
        if ev.result == "failed":
            mismatches.append(ConvergenceMismatch(dimension="runtime", actual_ref=primary,
                                                  detail="runtime observation failed"))
            state = DIVERGENT
            confidence = 0.8
            freshness = "fresh"
        elif ev.result == "passed":
            expected_revision = current_source_revision_id or current_twin_revision_id
            if ev.source_revision == expected_revision:
                state = VERIFIED
                confidence = 0.95
                freshness = "fresh"
            else:
                # stale evidence cannot satisfy verification.
                state = STALE
                confidence = 0.5
                freshness = "stale"
                mismatches.append(ConvergenceMismatch(dimension="verification", actual_ref=primary,
                                                      detail="evidence from a different revision (stale)"))
        elif ev.result == "observed":
            state = OBSERVED
            confidence = 0.6
            freshness = "fresh"
        elif ev.result == "unavailable":
            state = MATERIALIZED  # unavailable never upgrades to verified
            confidence = 0.5
            freshness = "unavailable"

    # interface divergence overrides a non-failed structural state
    if mismatches and state not in (DIVERGENT, STALE):
        state = DIVERGENT
        confidence = max(confidence, 0.7)

    # partial: some expected refs still missing
    if missing and state in (MATERIALIZED,):
        state = PARTIAL
        confidence = 0.5

    return ElementConvergenceResult(
        blueprint_element_id=el.element_id, state=state, evidence_policy=evidence_policy,
        required_evidence_refs=required_evidence, matched_actual_refs=matched,
        missing_actual_refs=missing, evidence_refs=evidence, mismatches=mismatches,
        freshness=freshness, confidence=confidence,
    )


def evaluate_convergence(
    revision: BlueprintRevision,
    snapshot: list[ActualEntry],
    *,
    project_id: str,
    workspace_id: str,
    twin_revision_id: str,
    source_revision_id: str | None = None,
    requirement_revision_id: str | None = None,
    mapping_revision_id: str | None = None,
    evidence_revision_id: str | None = None,
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
                               current_source_revision_id=source_revision_id,
                               snapshot_by_ref=snapshot_by_ref, verification=verification)
        results.append(res)
        if res.state == STALE:
            stale_evidence.extend(res.evidence_refs or [res.blueprint_element_id])
        if res.state in (ABSENT, PARTIAL, BLOCKED, DIVERGENT, STALE) or (el.mandatory and not _policy_satisfied(res)):
            description = f"{el.name or eid}: {res.state}"
            if el.mandatory and not _policy_satisfied(res):
                description = f"{description}; evidence policy {res.evidence_policy} unsatisfied"
            gap = GapSummary(gap_id=f"gap:{eid}", blueprint_element_id=eid,
                             description=description, mandatory=el.mandatory,
                             missing_refs=[*res.missing_actual_refs, *res.required_evidence_refs])
            (mandatory_gaps if el.mandatory else optional_gaps).append(gap)

    coverage: dict[str, object] = {
        "total_elements": len(results),
        "verified": sum(1 for r in results if r.state == VERIFIED),
        "mandatory_gaps": len(mandatory_gaps),
    }
    return ConvergenceReport(
        report_id=f"conv:{uuid.uuid4().hex[:10]}", project_id=project_id, workspace_id=workspace_id,
        blueprint_revision_id=revision.revision_id, actual_twin_revision_id=twin_revision_id,
        actual_source_revision_id=source_revision_id, requirement_revision_id=requirement_revision_id,
        mapping_revision_id=mapping_revision_id, evidence_revision_id=evidence_revision_id,
        element_results=results, mandatory_gaps=mandatory_gaps, optional_gaps=optional_gaps,
        stale_evidence=sorted(set(stale_evidence)), requirement_coverage=coverage,
        diagnostics=[], generated_at=now,
    )


def affected_elements(revision: BlueprintRevision, changed_refs: set[str]) -> set[str]:
    """Elements directly touched by changed refs plus their downstream dependents.

    An interface change ripples to dependents; an unrelated change does not reach them, so
    incremental reevaluation stays bounded and a local change never re-evaluates everything.
    """
    direct = {
        el.element_id for el in revision.elements
        if (set(el.expected_actual_refs) & changed_refs) or (el.canonical_ref in changed_refs)
    }
    dependents: dict[str, set[str]] = {}
    for el in revision.elements:
        for dep in el.depends_on_element_ids:
            dependents.setdefault(dep, set()).add(el.element_id)
    out = set(direct)
    frontier = list(direct)
    while frontier:
        cur = frontier.pop()
        for d in dependents.get(cur, set()):
            if d not in out:
                out.add(d)
                frontier.append(d)
    return out


def incremental_evaluate(
    revision: BlueprintRevision,
    snapshot: list[ActualEntry],
    *,
    changed_refs: set[str],
    prior_report: ConvergenceReport,
    project_id: str,
    workspace_id: str,
    twin_revision_id: str,
    source_revision_id: str | None = None,
    requirement_revision_id: str | None = None,
    mapping_revision_id: str | None = None,
    evidence_revision_id: str | None = None,
    verification: dict[str, VerificationEvidence] | None = None,
    hints: list[MappingHint] | None = None,
    now: datetime | None = None,
) -> ConvergenceReport:
    """Re-evaluate only the affected elements; reuse prior results for the rest.

    The affected subset is guaranteed to agree with a full re-evaluation (same inputs),
    so the bounded report is consistent with the full report for affected elements.
    """
    now = now or datetime.now(timezone.utc)
    verification = verification or {}
    snapshot_by_ref = {e.ref: e for e in snapshot}
    affected = affected_elements(revision, changed_refs)
    matches = match_elements(revision, snapshot, twin_revision_id=twin_revision_id, hints=hints)
    by_id = {e.element_id: e for e in revision.elements}
    prior = {r.blueprint_element_id: r for r in prior_report.element_results}

    results: list[ElementConvergenceResult] = []
    mandatory_gaps: list[GapSummary] = []
    optional_gaps: list[GapSummary] = []
    stale_evidence: list[str] = []
    for eid in sorted(by_id):
        el = by_id[eid]
        if eid in affected or eid not in prior:
            res = evaluate_element(el, matches[eid], current_twin_revision_id=twin_revision_id,
                                   current_source_revision_id=source_revision_id,
                                   snapshot_by_ref=snapshot_by_ref, verification=verification)
        else:
            res = prior[eid]
        results.append(res)
        if res.state == STALE:
            stale_evidence.extend(res.evidence_refs or [eid])
        if res.state in (ABSENT, PARTIAL, BLOCKED, DIVERGENT, STALE) or (el.mandatory and not _policy_satisfied(res)):
            description = f"{el.name or eid}: {res.state}"
            if el.mandatory and not _policy_satisfied(res):
                description = f"{description}; evidence policy {res.evidence_policy} unsatisfied"
            gap = GapSummary(gap_id=f"gap:{eid}", blueprint_element_id=eid,
                             description=description, mandatory=el.mandatory,
                             missing_refs=[*res.missing_actual_refs, *res.required_evidence_refs])
            (mandatory_gaps if el.mandatory else optional_gaps).append(gap)

    coverage = {"total_elements": len(results),
                "verified": sum(1 for r in results if r.state == VERIFIED),
                "mandatory_gaps": len(mandatory_gaps), "reevaluated": sorted(affected)}
    return ConvergenceReport(
        report_id=f"conv:{uuid.uuid4().hex[:10]}", project_id=project_id, workspace_id=workspace_id,
        blueprint_revision_id=revision.revision_id, actual_twin_revision_id=twin_revision_id,
        actual_source_revision_id=source_revision_id, requirement_revision_id=requirement_revision_id,
        mapping_revision_id=mapping_revision_id, evidence_revision_id=evidence_revision_id,
        element_results=results, mandatory_gaps=mandatory_gaps, optional_gaps=optional_gaps,
        stale_evidence=sorted(set(stale_evidence)), requirement_coverage=coverage,
        diagnostics=[], generated_at=now,
    )
