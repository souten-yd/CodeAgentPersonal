"""TwinProof test inventory and proof-gap classifier."""
from __future__ import annotations

from enum import StrEnum
from typing import Iterable

from pydantic import Field

from agent.project_intelligence.contracts import RuntimeObservationRecord
from agent.twin_control_plane.no_data_bootstrap_gate import NoDataBootstrapAssessment
from agent.twin_control_plane.schema_guardian import SchemaGuardianReport
from agent.twin_control_plane.state_mirror import StateMirrorReport
from agent.twin_control_plane.contracts import TwinControlPlaneModel


class TestClassification(StrEnum):
    IMPACTED = "impacted"
    STALE_CANDIDATE = "stale_candidate"
    COVERAGE_GAP = "coverage_gap"
    FLAKY_CANDIDATE = "flaky_candidate"
    REDUNDANT_CANDIDATE = "redundant_candidate"


TestClassification.__test__ = False


class TestInventoryItem(TwinControlPlaneModel):
    test_ref: str = Field(min_length=1)
    classifications: list[TestClassification] = Field(default_factory=list)
    subject_refs: list[str] = Field(default_factory=list)
    observation_results: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    reason: str = ""


class ProofGap(TwinControlPlaneModel):
    gap_id: str = Field(min_length=1)
    gap_type: str = Field(min_length=1)
    message: str = Field(min_length=1)
    refs: list[str] = Field(default_factory=list)
    proof_requirements: list[str] = Field(default_factory=list)


class TwinProofReport(TwinControlPlaneModel):
    report_id: str = Field(min_length=1)
    accepted: bool = False
    test_inventory: list[TestInventoryItem] = Field(default_factory=list)
    proof_gaps: list[ProofGap] = Field(default_factory=list)
    impacted_tests: list[str] = Field(default_factory=list)
    stale_candidates: list[str] = Field(default_factory=list)
    coverage_gaps: list[str] = Field(default_factory=list)
    flaky_candidates: list[str] = Field(default_factory=list)
    redundant_candidates: list[str] = Field(default_factory=list)
    proof_requirements: list[str] = Field(default_factory=list)


def _unique(values: Iterable[str]) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})


def _test_refs_from_observation(obs: RuntimeObservationRecord) -> list[str]:
    refs = [ref for ref in obs.subject_refs if ref.startswith("test://") or "test" in ref.lower()]
    if refs:
        return refs
    if obs.observation_type == "test_execution":
        return [f"test://{obs.observation_id}"]
    return []


def build_twinproof(
    *,
    runtime_observations: Iterable[RuntimeObservationRecord] = (),
    related_test_refs: Iterable[str] = (),
    impacted_refs: Iterable[str] = (),
    stale_test_refs: Iterable[str] = (),
    no_data: NoDataBootstrapAssessment | None = None,
    schema_guardian: SchemaGuardianReport | None = None,
    state_mirror: StateMirrorReport | None = None,
) -> TwinProofReport:
    """Build Test Inventory and proof gaps from observations and gate reports."""
    impacted = set(_unique(impacted_refs))
    stale = set(_unique(stale_test_refs))
    observations = list(runtime_observations)
    by_test: dict[str, TestInventoryItem] = {}

    for test_ref in _unique(related_test_refs):
        by_test[test_ref] = TestInventoryItem(test_ref=test_ref, reason="related_test_ref")

    for obs in observations:
        for test_ref in _test_refs_from_observation(obs):
            item = by_test.setdefault(test_ref, TestInventoryItem(test_ref=test_ref, reason="runtime_observation"))
            item.subject_refs = _unique([*item.subject_refs, *obs.subject_refs])
            item.observation_results = _unique([*item.observation_results, obs.result])
            item.evidence_refs = _unique([*item.evidence_refs, *obs.evidence_refs, obs.observation_id])

    subject_to_tests: dict[tuple[str, ...], list[str]] = {}
    for item in by_test.values():
        classes: set[TestClassification] = set(item.classifications)
        subjects = set(item.subject_refs)
        if impacted and subjects & impacted:
            classes.add(TestClassification.IMPACTED)
        if item.test_ref in stale:
            classes.add(TestClassification.STALE_CANDIDATE)
        if {"passed", "failed"} <= set(item.observation_results):
            classes.add(TestClassification.FLAKY_CANDIDATE)
        coverage_subjects = tuple(ref for ref in item.subject_refs if not ref.startswith("test://") and "test" not in ref.lower())
        if coverage_subjects:
            subject_to_tests.setdefault(coverage_subjects, []).append(item.test_ref)
        item.classifications = sorted(classes, key=lambda c: c.value)

    for refs, tests in subject_to_tests.items():
        if len(tests) <= 1:
            continue
        for test_ref in sorted(tests)[1:]:
            item = by_test[test_ref]
            item.classifications = sorted(set([*item.classifications, TestClassification.REDUNDANT_CANDIDATE]), key=lambda c: c.value)

    covered_refs = {ref for item in by_test.values() for ref in item.subject_refs}
    gaps: list[ProofGap] = []
    for ref in sorted(impacted - covered_refs):
        gaps.append(ProofGap(
            gap_id=f"twinproof.coverage_gap:{ref}",
            gap_type=TestClassification.COVERAGE_GAP.value,
            message="Impacted ref lacks related runtime/test coverage.",
            refs=[ref],
            proof_requirements=[f"Add or identify focused test coverage for {ref}."],
        ))

    if no_data and no_data.bootstrap_required:
        gaps.append(ProofGap(
            gap_id="twinproof.no_data_bootstrap",
            gap_type="no_data",
            message="No-data bootstrap requirements must be proven.",
            refs=[req.requirement_id for req in no_data.requirements],
            proof_requirements=[req.proof_requirement for req in no_data.requirements],
        ))
    if schema_guardian and (schema_guardian.blocked or schema_guardian.migration_required or not schema_guardian.accepted):
        gaps.append(ProofGap(
            gap_id="twinproof.schema_guardian",
            gap_type="schema",
            message="Schema Guardian findings require compatibility or migration proof.",
            refs=[finding.finding_id for finding in schema_guardian.findings],
            proof_requirements=list(schema_guardian.proof_requirements),
        ))
    if state_mirror and (state_mirror.blocked or not state_mirror.accepted):
        gaps.append(ProofGap(
            gap_id="twinproof.state_mirror",
            gap_type="state",
            message="StateMirror findings require backend/UI/persistence/runtime proof.",
            refs=[finding.finding_id for finding in state_mirror.findings],
            proof_requirements=list(state_mirror.proof_requirements),
        ))

    inventory = sorted(by_test.values(), key=lambda item: item.test_ref)
    proof_requirements = _unique(req for gap in gaps for req in gap.proof_requirements)
    return TwinProofReport(
        report_id="twinproof:test_inventory",
        accepted=not gaps and not any(TestClassification.FLAKY_CANDIDATE in item.classifications for item in inventory),
        test_inventory=inventory,
        proof_gaps=gaps,
        impacted_tests=_unique(item.test_ref for item in inventory if TestClassification.IMPACTED in item.classifications),
        stale_candidates=_unique(item.test_ref for item in inventory if TestClassification.STALE_CANDIDATE in item.classifications),
        coverage_gaps=_unique(gap.refs[0] for gap in gaps if gap.gap_type == TestClassification.COVERAGE_GAP.value and gap.refs),
        flaky_candidates=_unique(item.test_ref for item in inventory if TestClassification.FLAKY_CANDIDATE in item.classifications),
        redundant_candidates=_unique(item.test_ref for item in inventory if TestClassification.REDUNDANT_CANDIDATE in item.classifications),
        proof_requirements=proof_requirements,
    )


__all__ = [
    "ProofGap",
    "TestClassification",
    "TestInventoryItem",
    "TwinProofReport",
    "build_twinproof",
]
