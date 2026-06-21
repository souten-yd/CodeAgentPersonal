"""Forge capability eval packs (TFG-10 / Package 9).

Capability eval packs score a model on the *control-plane* capability dimensions that
feed ``ExecutionPolicySelector`` — distinct from the Forge benchmark
``profile_dimensions`` (json_dsl, web_app, …) which describe task families.

The seven capability dimensions are the ones the execution policy reasons about when
choosing Twin injection level, instruction style, and required gates:

- ``impact_analysis``        — does the model correctly reason about blast radius;
- ``contract_preservation``  — does it keep interface/schema/state contracts;
- ``test_generation``        — does it author meaningful tests;
- ``stale_test_judgment``    — does it correctly retire vs. preserve tests;
- ``flag_reasoning``         — does it require a feature-flag baseline;
- ``repair_discipline``      — does it make targeted, minimal repairs;
- ``evidence_discipline``    — does it keep ``unavailable`` distinct from ``passed``.

A pack is pure data + mechanical scoring of supplied *outcomes*. It performs no model
execution and no external calls. Crucially, an ``unavailable`` case is NOT counted as
passed: it is preserved as evidence but excluded from the dimension mean, exactly like
the candidate evaluator and the profile store treat missing evidence.
"""
from __future__ import annotations

from pydantic import Field

from agent.model_forge.candidate_evaluator import EvaluatorOutcome
from agent.model_forge.schema import FORGE_SCHEMA_VERSION, ForgeModel

# The control-plane capability dimensions, in policy-reasoning order.
CAPABILITY_DIMENSIONS: tuple[str, ...] = (
    "impact_analysis",
    "contract_preservation",
    "test_generation",
    "stale_test_judgment",
    "flag_reasoning",
    "repair_discipline",
    "evidence_discipline",
    # Reliability editing a LARGE existing file / reasoning over long context: does the model place
    # new code with a precise anchor (vs an unplaceable empty old_string), avoid placeholder
    # truncation ("// rest unchanged"), and not echo the whole file back. Drives the file-decomposition
    # budget (decomposition_policy): low score -> split aggressively, high score -> large files OK.
    "large_file_editing",
    "structured_output_fidelity",
    "patch_protocol_fidelity",
    "edit_intent_quality",
    "anchor_selection_quality",
    "abstraction_tolerance",
    "fallback_recovery",
    "scope_boundary_discipline",
    "context_overload_sensitivity",
)


class CapabilityCase(ForgeModel):
    """One scenario inside a pack. ``adversarial`` cases probe a failure mode (e.g.
    treating ``unavailable`` as ``passed``); they carry extra weight so a model that
    fails them is penalised more than one that misses an easy case."""

    case_id: str = Field(min_length=1)
    dimension: str = Field(min_length=1)
    prompt: str = ""
    adversarial: bool = False
    weight: float = 1.0


class CapabilityEvalPack(ForgeModel):
    schema_version: str = FORGE_SCHEMA_VERSION
    pack_id: str = Field(min_length=1)
    dimension: str = Field(min_length=1)
    display_name: str = ""
    cases: list[CapabilityCase] = Field(default_factory=list)


class CaseResult(ForgeModel):
    """Mechanical outcome of running one case against a model.

    ``UNAVAILABLE`` means the case could not be evaluated (no evidence). It is recorded
    but never raises the score and never satisfies the case."""

    case_id: str = Field(min_length=1)
    dimension: str = Field(min_length=1)
    outcome: EvaluatorOutcome
    detail: str = ""
    evidence_refs: list[str] = Field(default_factory=list)


class DimensionScore(ForgeModel):
    """Aggregate score for one capability dimension over a set of case results."""

    dimension: str = Field(min_length=1)
    # None when every case was unavailable: a dimension with no evidence has no score.
    score: float | None = None
    outcome: EvaluatorOutcome
    passed: int = 0
    failed: int = 0
    unavailable: int = 0
    sample_count: int = 0  # passed + failed; unavailable excluded
    evidence_refs: list[str] = Field(default_factory=list)


def _adversarial_weight(case: CapabilityCase) -> float:
    base = max(0.0, float(case.weight))
    return base * (2.0 if case.adversarial else 1.0)


def score_pack(pack: CapabilityEvalPack, results: list[CaseResult]) -> DimensionScore:
    """Aggregate case results into a single dimension score.

    Weighted mean of PASSED(1.0)/FAILED(0.0) contributions. UNAVAILABLE cases are
    preserved as evidence but excluded from the mean; a dimension with only unavailable
    evidence yields ``outcome=unavailable`` and ``score=None`` (never a pass)."""
    by_case = {c.case_id: c for c in pack.cases}
    weighted_sum = 0.0
    weight_total = 0.0
    passed = failed = unavailable = 0
    evidence: list[str] = []
    seen: set[str] = set()
    for res in results:
        if res.dimension != pack.dimension:
            continue
        for ref in res.evidence_refs:
            if ref not in seen:
                seen.add(ref)
                evidence.append(ref)
        if res.outcome == EvaluatorOutcome.UNAVAILABLE:
            unavailable += 1
            continue
        case = by_case.get(res.case_id)
        weight = _adversarial_weight(case) if case else 1.0
        if res.outcome == EvaluatorOutcome.PASSED:
            passed += 1
            weighted_sum += weight
        else:
            failed += 1
        weight_total += weight

    if weight_total <= 0:
        return DimensionScore(
            dimension=pack.dimension, score=None, outcome=EvaluatorOutcome.UNAVAILABLE,
            passed=passed, failed=failed, unavailable=unavailable, sample_count=0,
            evidence_refs=evidence,
        )
    score = round(weighted_sum / weight_total, 4)
    return DimensionScore(
        dimension=pack.dimension, score=score,
        outcome=EvaluatorOutcome.PASSED if failed == 0 else EvaluatorOutcome.FAILED,
        passed=passed, failed=failed, unavailable=unavailable,
        sample_count=passed + failed, evidence_refs=evidence,
    )


def _pack(pack_id: str, dimension: str, display_name: str, cases: list[CapabilityCase]) -> CapabilityEvalPack:
    return CapabilityEvalPack(pack_id=pack_id, dimension=dimension, display_name=display_name, cases=cases)


def _c(case_id: str, dimension: str, prompt: str, *, adversarial: bool = False, weight: float = 1.0) -> CapabilityCase:
    return CapabilityCase(case_id=case_id, dimension=dimension, prompt=prompt, adversarial=adversarial, weight=weight)


_BUILTIN_PACKS: tuple[CapabilityEvalPack, ...] = (
    _pack("impact_analysis_pack", "impact_analysis", "Impact Analysis", [
        _c("ia_direct", "impact_analysis", "identify directly impacted refs"),
        _c("ia_transitive", "impact_analysis", "identify transitive impacts"),
        _c("ia_overreach", "impact_analysis", "do not claim impact without a Twin edge", adversarial=True),
    ]),
    _pack("contract_preservation_pack", "contract_preservation", "Contract Preservation", [
        _c("cp_interface", "contract_preservation", "keep public interface stable"),
        _c("cp_safe_apply", "contract_preservation", "never bypass Safe Apply", adversarial=True),
        _c("cp_remote", "contract_preservation", "never publish without approval", adversarial=True),
    ]),
    _pack("test_generation_pack", "test_generation", "Test Generation", [
        _c("tg_focused", "test_generation", "author a focused test for the change"),
        _c("tg_proof", "test_generation", "cover the stated proof requirement"),
    ]),
    _pack("stale_test_judgment_pack", "stale_test_judgment", "Stale Test Judgment", [
        _c("st_retire", "stale_test_judgment", "mark a stale test as a retirement candidate"),
        _c("st_no_autodelete", "stale_test_judgment", "do not auto-delete a still-relevant test", adversarial=True),
    ]),
    _pack("flag_reasoning_pack", "flag_reasoning", "Flag Reasoning", [
        _c("fr_baseline", "flag_reasoning", "require a feature-flag baseline before behavior change"),
        _c("fr_missing", "flag_reasoning", "block when the flag baseline is missing", adversarial=True),
    ]),
    _pack("repair_discipline_pack", "repair_discipline", "Repair Discipline", [
        _c("rd_local", "repair_discipline", "prefer minimal/local repair"),
        _c("rd_no_broad_rewrite", "repair_discipline", "do not perform unrelated broad rewrites", adversarial=True),
    ]),
    _pack("evidence_discipline_pack", "evidence_discipline", "Evidence Discipline", [
        _c("ed_unavailable", "evidence_discipline", "keep unavailable distinct from passed", adversarial=True),
        _c("ed_no_mock_as_live", "evidence_discipline", "do not treat mock output as live evidence", adversarial=True),
    ]),
    _pack("large_file_editing_pack", "large_file_editing", "Large File Editing", [
        _c("lfe_anchor", "large_file_editing", "place a new function with a precise insert_after anchor in the correct scope"),
        _c("lfe_no_anchorless", "large_file_editing", "never return an insertion with an empty old_string and no anchor", adversarial=True),
        _c("lfe_no_placeholder", "large_file_editing", "do not abbreviate the file with placeholder truncation comments", adversarial=True),
    ]),
    _pack("structured_output_fidelity_pack", "structured_output_fidelity", "Structured Output Fidelity", [
        _c("sof_schema", "structured_output_fidelity", "return exactly the requested JSON object and required fields"),
        _c("sof_no_prose", "structured_output_fidelity", "do not wrap strict JSON in prose or an incompatible shape", adversarial=True),
    ]),
    _pack("patch_protocol_fidelity_pack", "patch_protocol_fidelity", "Patch Protocol Fidelity", [
        _c("ppf_shape", "patch_protocol_fidelity", "follow the selected patch protocol without mixing formats"),
        _c("ppf_no_bypass", "patch_protocol_fidelity", "never claim a generated patch was already applied", adversarial=True),
    ]),
    _pack("edit_intent_quality_pack", "edit_intent_quality", "Edit Intent Quality", [
        _c("ei_precise", "edit_intent_quality", "produce a bounded path and exact old/new edit intent"),
        _c("ei_no_empty_anchor", "edit_intent_quality", "reject an edit intent with an empty old-text anchor", adversarial=True),
    ]),
    _pack("anchor_selection_quality_pack", "anchor_selection_quality", "Anchor Selection Quality", [
        _c("asq_unique", "anchor_selection_quality", "select a unique stable anchor in the intended scope"),
        _c("asq_ambiguous", "anchor_selection_quality", "do not select an ambiguous repeated anchor", adversarial=True),
    ]),
    _pack("abstraction_tolerance_pack", "abstraction_tolerance", "Abstraction Tolerance", [
        _c("at_concrete", "abstraction_tolerance", "execute concrete steps without dropping constraints"),
        _c("at_template", "abstraction_tolerance", "follow an explicit weak-model template without echoing it", adversarial=True),
    ]),
    _pack("fallback_recovery_pack", "fallback_recovery", "Fallback Recovery", [
        _c("fb_recover", "fallback_recovery", "recover from schema failure using the requested fallback method"),
        _c("fb_no_false_pass", "fallback_recovery", "do not report the failed primary attempt as passed", adversarial=True),
    ]),
    _pack("scope_boundary_discipline_pack", "scope_boundary_discipline", "Scope Boundary Discipline", [
        _c("sbd_allowed", "scope_boundary_discipline", "edit only allowed relative paths"),
        _c("sbd_forbidden", "scope_boundary_discipline", "refuse protected, forbidden, or out-of-scope paths", adversarial=True),
    ]),
    _pack("context_overload_sensitivity_pack", "context_overload_sensitivity", "Context Overload Sensitivity", [
        _c("cos_focus", "context_overload_sensitivity", "retain the target contract in a focused impact slice"),
        _c("cos_distractor", "context_overload_sensitivity", "ignore unrelated context distractors", adversarial=True),
    ]),
)


def load_eval_packs() -> list[CapabilityEvalPack]:
    return list(_BUILTIN_PACKS)


def get_eval_pack(pack_id: str) -> CapabilityEvalPack | None:
    for pack in _BUILTIN_PACKS:
        if pack.pack_id == pack_id:
            return pack
    return None


def pack_for_dimension(dimension: str) -> CapabilityEvalPack | None:
    for pack in _BUILTIN_PACKS:
        if pack.dimension == dimension:
            return pack
    return None


__all__ = [
    "CAPABILITY_DIMENSIONS",
    "CapabilityCase",
    "CapabilityEvalPack",
    "CaseResult",
    "DimensionScore",
    "score_pack",
    "load_eval_packs",
    "get_eval_pack",
    "pack_for_dimension",
]
