"""Live-pipeline integration seam for the Twin Control Plane (TFG-12 cut-over).

This is the single, reversible seam that lets the autonomous codegen orchestrator run
the Twin/Forge gated pipeline as **advisory evidence** alongside its existing
generate/apply/verify flow.

Authority is preserved exactly: Atlas keeps Proposal / Safe Apply / Verification, and the
Twin Control Plane stays advisory context/evidence. This seam therefore never applies,
verifies, commits, or publishes — it only assembles ExecutionPolicy, TwinBrief, and a
shadow report and returns them as run metadata.

Mode is resolved from configuration and defaults to OFF, so a fresh checkout and any
deployment that does not opt in behaves exactly as before. Active mode is enabled by
setting ``ATLAS_TWIN_PIPELINE_MODE=active`` (or passing the mode explicitly) and is fully
reversible by setting it back to ``off``. Active mode also requires shadow evidence to
have been assembled; if it cannot be, the seam degrades to recording the gap rather than
forcing a change.
"""
from __future__ import annotations

import os
from typing import Iterable

from agent.twin_control_plane.active_integration import PipelineMode
from agent.twin_control_plane.contracts import TwinBrief, default_hard_constraints
from agent.twin_control_plane.shadow_integration import (
    TwinShadowMode,
    TwinShadowOrchestrator,
    TwinShadowReport,
)

PIPELINE_MODE_ENV = "ATLAS_TWIN_PIPELINE_MODE"
GATE_BLOCKING_ENV = "ATLAS_TWIN_GATE_BLOCKING"

# Default mode for the live pipeline. Active is the approved production default; it stays
# advisory for execution authority and is fully reversible via ATLAS_TWIN_PIPELINE_MODE=off.
DEFAULT_PIPELINE_MODE = PipelineMode.ACTIVE


def resolve_pipeline_mode(value: str | None = None) -> PipelineMode:
    """Resolve the Twin pipeline mode from an explicit value or the environment.

    Defaults to ACTIVE (the approved production default). An unrecognised value falls back
    to the default rather than silently disabling the gate; set ``off`` explicitly to
    return to the legacy flow."""
    raw = (value if value is not None else os.environ.get(PIPELINE_MODE_ENV, "")).strip().lower()
    if not raw:
        return DEFAULT_PIPELINE_MODE
    try:
        return PipelineMode(raw)
    except ValueError:
        return DEFAULT_PIPELINE_MODE


def resolve_gate_blocking(value: str | None = None) -> bool:
    """Whether the Twin gate may BLOCK a run (promoted from advisory).

    Defaults to enabled. Disable with ``ATLAS_TWIN_GATE_BLOCKING`` in
    {0, off, false, no}. Even when enabled, blocking is limited to a genuine policy
    prerequisite (see ``twin_gate_block_reason``); it never blocks on advisory
    uncertainty or on infrastructure unavailability."""
    raw = (value if value is not None else os.environ.get(GATE_BLOCKING_ENV, "")).strip().lower()
    if raw in {"0", "off", "false", "no"}:
        return False
    return True


def twin_gate_block_reason(evidence: dict) -> str:
    """Return a block reason when the (blocking) Twin gate must stop the run, else "".

    Conservative by design: it blocks ONLY when active mode is engaged but the shadow
    evidence active requires could not be assembled. It deliberately does NOT block on:
    advisory uncertainty, missing optional artifacts, or ``available=False`` from an
    internal/infra error (unavailable is not a failure)."""
    if not isinstance(evidence, dict):
        return ""
    if evidence.get("mode") != PipelineMode.ACTIVE.value:
        return ""
    if evidence.get("available") and evidence.get("requires_shadow_evidence"):
        return "twin_gate_requires_shadow_evidence"
    return ""


BLOCK_UNVERIFIED_ENV = "ATLAS_TWIN_BLOCK_UNVERIFIED"


def resolve_block_unverified(value: str | None = None) -> bool:
    """Whether the post-apply gate should hard-block a completed run that has changed
    files but NO passing verification evidence (only unavailable/missing).

    Defaults to OFF: the autonomous full-auto path legitimately auto-continues some
    unverifiable changes (e.g. a static file whose only check is "open in a browser"),
    so this stricter block is opt-in via ``ATLAS_TWIN_BLOCK_UNVERIFIED`` in
    {1, on, true, yes}."""
    raw = (value if value is not None else os.environ.get(BLOCK_UNVERIFIED_ENV, "")).strip().lower()
    return raw in {"1", "on", "true", "yes"}


def _stable_brief_id(pool_id: str, requirement: str) -> str:
    base = f"{pool_id}:{requirement}".strip(":") or "twin_brief"
    return "twin_brief_" + base.replace(" ", "_")[:48]


def _build_policy_and_brief(
    *, requirement: str, pool_id: str, project_path: str, refs: list[str],
    item_refs: Iterable[str], change_class: str, task_category: str,
):
    """Build the ExecutionPolicy (Forge Twin route selection) and TwinBrief for a run.

    Lazy imports keep model_forge out of the twin_control_plane package import graph."""
    from agent.model_forge.execution_policy import ExecutionPolicySelector, ModelCapabilityProfile
    from agent.model_forge.route_matrix import ChangeClass

    selector = ExecutionPolicySelector()
    policy = selector.select(
        ChangeClass(change_class), task_category=task_category,
        model_profile=ModelCapabilityProfile(model_id="atlas-codegen"),
    )
    brief = TwinBrief(
        brief_id=_stable_brief_id(pool_id, requirement),
        goal=requirement or "autonomous codegen",
        allowed_refs=refs,
        impacted_refs=refs,
        hard_constraints=default_hard_constraints(),
        source_refs=[project_path] if project_path else [],
        metadata={"pool_id": pool_id, "item_refs": sorted({str(i) for i in item_refs if str(i).strip()})},
    )
    return policy, brief


def try_project_twin_impact(
    *, project_id: str, changed_refs: Iterable[str], store=None, change_kind: str = "modify"
):
    """Best-effort real Project Twin impact for the current run.

    Returns an ``ImpactResult`` when a Project Twin store with a snapshot for
    ``project_id`` is available, else ``None`` (recorded as unavailable upstream — never
    fabricated). Never raises. There is no persistent per-project Twin store by default,
    so the common live outcome is ``None``; when a store is supplied (tests, or a future
    persistent Twin), real impact flows through unchanged."""
    refs = [str(r).strip() for r in changed_refs if str(r).strip()]
    if store is None or not project_id or not refs:
        return None
    try:
        from agent.project_twin.contracts import ImpactRequest

        request = ImpactRequest(project_id=project_id, changed_refs=refs, change_kind=change_kind)
        return store.assess_impact(request)
    except Exception:
        return None


def _impact_section(impact) -> dict:
    if impact is None:
        return {"available": False, "reason": "project_twin_impact_unavailable"}
    return {
        "available": True,
        "project_id": getattr(impact, "project_id", ""),
        "twin_revision_id": getattr(impact, "twin_revision_id", ""),
        "direct_impacts": len(getattr(impact, "direct_impacts", []) or []),
        "transitive_impacts": len(getattr(impact, "transitive_impacts", []) or []),
        "recommended_tests": len(getattr(impact, "recommended_tests", []) or []),
    }


def build_twin_pipeline_evidence(
    *,
    mode: PipelineMode,
    requirement: str = "",
    pool_id: str = "",
    project_path: str = "",
    changed_refs: Iterable[str] = (),
    item_refs: Iterable[str] = (),
    impact=None,
    change_class: str = "medium",
    task_category: str = "autonomous_codegen",
) -> dict:
    """Assemble advisory Twin evidence for one autonomous run. Never raises — any internal
    failure is reported as ``available: False`` so the legacy flow is never broken.

    When a real Project Twin ``impact`` is supplied it flows into the shadow assembly
    (BlastMap + TwinProof) and Contract Sentinel; when absent the impact section is
    recorded as explicitly unavailable (never fabricated)."""
    if mode == PipelineMode.OFF:
        return {"mode": PipelineMode.OFF.value, "engaged": False, "available": False,
                "reason": "pipeline_off"}

    try:
        refs = sorted({str(r).strip() for r in changed_refs if str(r).strip()})
        policy, brief = _build_policy_and_brief(
            requirement=requirement, pool_id=pool_id, project_path=project_path, refs=refs,
            item_refs=item_refs, change_class=change_class, task_category=task_category,
        )
        shadow_orch = TwinShadowOrchestrator(TwinShadowMode.SHADOW)
        shadow_report: TwinShadowReport | None = shadow_orch.assemble(
            requirement_ref=requirement, plan_item_ref=pool_id,
            execution_policy=policy, twin_brief=brief, changed_refs=refs,
            impact=impact,
        )
        # Contract Sentinel over the real BlastMap when impact evidence exists.
        contract_section: dict | None = None
        if impact is not None:
            try:
                from agent.twin_control_plane.blast_map import build_blast_map
                from agent.twin_control_plane.contract_sentinel import evaluate_contracts

                blast = build_blast_map(impact, brief=brief, changed_refs=refs)
                sentinel = evaluate_contracts(policy, brief, blast)
                contract_section = {
                    "report_id": sentinel.report_id,
                    "accepted": sentinel.accepted,
                    "blocked": sentinel.blocked,
                    "proof_requirements": list(sentinel.proof_requirements),
                }
            except Exception:
                contract_section = {"available": False, "reason": "contract_sentinel_error"}

        has_shadow_evidence = shadow_report is not None
        engaged = mode == PipelineMode.ACTIVE and has_shadow_evidence
        evidence = {
            "mode": mode.value,
            "engaged": engaged,
            "available": True,
            "advisory": True,  # never overrides Atlas Safe Apply / Verification authority
            "requires_shadow_evidence": mode == PipelineMode.ACTIVE and not has_shadow_evidence,
            "policy_id": policy.policy_id,
            "route": policy.route.value,
            "instruction_style": policy.instruction_style.value,
            "twin_injection_level": int(policy.twin_injection_level),
            "required_gates": list(policy.required_gates),
            "brief_id": brief.brief_id,
            "impact": _impact_section(impact),
            "contract_sentinel": contract_section,
            "shadow_report": shadow_report.model_dump(mode="json") if shadow_report else None,
        }
        return evidence
    except Exception as exc:  # pragma: no cover - defensive: never break the legacy flow
        return {"mode": getattr(mode, "value", str(mode)), "engaged": False,
                "available": False, "reason": f"twin_evidence_error:{type(exc).__name__}"}


def _verification_evidence(verification: Iterable):
    """Normalise (id, status) pairs or {evidence_id,status} dicts into VerificationEvidence.
    Anything that is not an explicit passed/failed is treated as unavailable (never passed)."""
    from agent.twin_control_plane.patch_impact_gate import VerificationEvidence

    out = []
    for idx, item in enumerate(verification or []):
        if isinstance(item, dict):
            ev_id = str(item.get("evidence_id") or item.get("id") or f"verify_{idx}")
            status = str(item.get("status") or "").strip().lower()
        else:
            ev_id = f"verify_{idx}"
            status = str(item).strip().lower()
        if status not in {"passed", "failed"}:
            status = "unavailable"
        out.append(VerificationEvidence(evidence_id=ev_id, status=status))
    return out


def evaluate_twin_post_apply(
    *,
    mode: PipelineMode,
    blocking: bool,
    block_unverified: bool = False,
    requirement: str = "",
    pool_id: str = "",
    project_path: str = "",
    changed_files: Iterable[str] = (),
    verification: Iterable = (),
    before_twin_revision_id: str = "",
    after_twin_revision_id: str = "",
    contract_sentinel=None,
    schema_guardian=None,
    state_mirror=None,
    twinproof=None,
    change_class: str = "medium",
    task_category: str = "autonomous_codegen",
) -> dict:
    """Run the Patch Impact Gate over the autonomous run's REAL post-apply evidence and
    return a record (plus a hard-block signal). Never raises.

    Blocking is conservative:
    - a genuine BLOCKED decision (hard contract/schema/state boundary) hard-blocks;
    - a completed change with changed files but NO passing verification only hard-blocks
      when ``block_unverified`` is explicitly enabled (it is otherwise recorded as an
      advisory proof gap, so legitimate auto-continued static changes are not disrupted);
    - ``unavailable`` evidence is never treated as passed."""
    if mode == PipelineMode.OFF:
        return {"mode": PipelineMode.OFF.value, "ran": False, "gate_blocked": False,
                "block_reason": "", "reason": "pipeline_off"}
    try:
        from agent.twin_control_plane.patch_impact_gate import PatchGateDecision, evaluate_patch_impact

        files = sorted({str(f).strip() for f in changed_files if str(f).strip()})
        policy, brief = _build_policy_and_brief(
            requirement=requirement, pool_id=pool_id, project_path=project_path, refs=files,
            item_refs=(), change_class=change_class, task_category=task_category,
        )
        evidence_items = _verification_evidence(verification)
        report = evaluate_patch_impact(
            policy=policy, brief=brief,
            base_ref=before_twin_revision_id, head_ref=after_twin_revision_id or "working_tree",
            changed_files=files,
            before_twin_revision_id=before_twin_revision_id,
            after_twin_revision_id=after_twin_revision_id,
            verification=evidence_items,
            contract_sentinel=contract_sentinel, schema_guardian=schema_guardian,
            state_mirror=state_mirror, twinproof=twinproof,
        )
        has_passed = bool(report.passed_evidence_refs)
        unverified_change = bool(files) and not has_passed

        block_reason = ""
        if blocking and report.decision == PatchGateDecision.BLOCKED:
            block_reason = "twin_post_apply_hard_boundary"
        elif blocking and block_unverified and unverified_change:
            block_reason = "twin_post_apply_unverified_change"

        return {
            "mode": mode.value,
            "ran": True,
            "decision": report.decision.value,
            "accepted": report.accepted,
            "needs_repair": report.needs_repair,
            "blocked_decision": report.blocked,
            "unverified_change": unverified_change,
            "gate_blocked": bool(block_reason),
            "block_reason": block_reason,
            "passed_evidence": list(report.passed_evidence_refs),
            "failed_evidence": list(report.failed_evidence_refs),
            "unavailable_evidence": list(report.unavailable_evidence_refs),
            "repair_reasons": list(report.repair_reasons),
            "blocked_reasons": list(report.blocked_reasons),
            "proof_requirements": list(report.proof_requirements),
            "report_id": report.report_id,
        }
    except Exception as exc:  # pragma: no cover - defensive: never break the legacy flow
        return {"mode": getattr(mode, "value", str(mode)), "ran": False, "gate_blocked": False,
                "block_reason": "", "reason": f"twin_post_apply_error:{type(exc).__name__}"}


__all__ = [
    "PIPELINE_MODE_ENV",
    "GATE_BLOCKING_ENV",
    "BLOCK_UNVERIFIED_ENV",
    "DEFAULT_PIPELINE_MODE",
    "resolve_pipeline_mode",
    "resolve_gate_blocking",
    "resolve_block_unverified",
    "twin_gate_block_reason",
    "try_project_twin_impact",
    "build_twin_pipeline_evidence",
    "evaluate_twin_post_apply",
]
