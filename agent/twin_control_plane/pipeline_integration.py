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


def resolve_pipeline_mode(value: str | None = None) -> PipelineMode:
    """Resolve the Twin pipeline mode from an explicit value or the environment.

    Defaults to OFF and treats any unrecognised value as OFF, so the legacy flow is the
    safe default and a misconfiguration can never silently enable active mode."""
    raw = (value if value is not None else os.environ.get(PIPELINE_MODE_ENV, "")).strip().lower()
    try:
        return PipelineMode(raw)
    except ValueError:
        return PipelineMode.OFF


def _stable_brief_id(pool_id: str, requirement: str) -> str:
    base = f"{pool_id}:{requirement}".strip(":") or "twin_brief"
    return "twin_brief_" + base.replace(" ", "_")[:48]


def build_twin_pipeline_evidence(
    *,
    mode: PipelineMode,
    requirement: str = "",
    pool_id: str = "",
    project_path: str = "",
    changed_refs: Iterable[str] = (),
    item_refs: Iterable[str] = (),
    change_class: str = "medium",
    task_category: str = "autonomous_codegen",
) -> dict:
    """Assemble advisory Twin evidence for one autonomous run. Never raises — any internal
    failure is reported as ``available: False`` so the legacy flow is never broken."""
    if mode == PipelineMode.OFF:
        return {"mode": PipelineMode.OFF.value, "engaged": False, "available": False,
                "reason": "pipeline_off"}

    try:
        # Lazy imports: keep model_forge out of the twin_control_plane package import graph
        # so the seam cannot create a module-load import cycle.
        from agent.model_forge.execution_policy import ExecutionPolicySelector, ModelCapabilityProfile
        from agent.model_forge.route_matrix import ChangeClass

        refs = sorted({str(r).strip() for r in changed_refs if str(r).strip()})
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
        shadow_orch = TwinShadowOrchestrator(TwinShadowMode.SHADOW)
        shadow_report: TwinShadowReport | None = shadow_orch.assemble(
            requirement_ref=requirement, plan_item_ref=pool_id,
            execution_policy=policy, twin_brief=brief, changed_refs=refs,
        )
        has_shadow_evidence = shadow_report is not None
        # Active requires shadow evidence; without it we record the gap, not a forced change.
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
            "shadow_report": shadow_report.model_dump(mode="json") if shadow_report else None,
        }
        return evidence
    except Exception as exc:  # pragma: no cover - defensive: never break the legacy flow
        return {"mode": getattr(mode, "value", str(mode)), "engaged": False,
                "available": False, "reason": f"twin_evidence_error:{type(exc).__name__}"}


__all__ = [
    "PIPELINE_MODE_ENV",
    "resolve_pipeline_mode",
    "build_twin_pipeline_evidence",
]
