"""Twin Control Plane settings + capability evaluation API.

Exposes the Twin pipeline mode/gate switches (so the UI can read/change them without
editing environment files), the control-plane capability profiles that drive Twin
injection, and a capability-evaluation trigger that records evidence to the ProfileStore.

The mode/gate switches are process-scoped environment variables (the same ones the
orchestrator resolves at run time), so changes here are reversible and take effect on the
next run. Nothing here mutates source, applies patches, or publishes.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.atlas_root import resolve_atlas_ca_data_root

router = APIRouter(prefix="/api/twin", tags=["twin-control"])

# (env var, default) for each Twin switch the UI can read/change.
_MODE_ENV = "ATLAS_TWIN_PIPELINE_MODE"
_FLAG_ENVS = {
    "gate_blocking": ("ATLAS_TWIN_GATE_BLOCKING", True),
    "block_unverified": ("ATLAS_TWIN_BLOCK_UNVERIFIED", False),
    "block_schema": ("ATLAS_TWIN_BLOCK_SCHEMA", False),
    "build_project": ("ATLAS_TWIN_BUILD_PROJECT", False),
}


def _current_settings() -> dict:
    from agent.twin_control_plane.pipeline_integration import (
        resolve_block_schema, resolve_block_unverified, resolve_build_project_twin,
        resolve_gate_blocking, resolve_pipeline_mode,
    )
    return {
        "mode": resolve_pipeline_mode().value,
        "gate_blocking": resolve_gate_blocking(),
        "block_unverified": resolve_block_unverified(),
        "block_schema": resolve_block_schema(),
        "build_project": resolve_build_project_twin(),
        "reversible": True,
        "note": "Process-scoped; takes effect on the next autonomous run. Advisory for execution authority.",
    }


class TwinSettingsUpdate(BaseModel):
    mode: str | None = Field(default=None)  # off | shadow | active
    gate_blocking: bool | None = None
    block_unverified: bool | None = None
    block_schema: bool | None = None
    build_project: bool | None = None


@router.get("/settings")
def get_settings() -> dict:
    return _current_settings()


@router.post("/settings")
def post_settings(payload: TwinSettingsUpdate) -> dict:
    if payload.mode is not None:
        mode = str(payload.mode).strip().lower()
        if mode not in {"off", "shadow", "active"}:
            raise HTTPException(status_code=400, detail="mode must be off, shadow, or active")
        os.environ[_MODE_ENV] = mode
    for name, (env, _default) in _FLAG_ENVS.items():
        value = getattr(payload, name)
        if value is not None:
            os.environ[env] = "on" if value else "off"
    return _current_settings()


@router.get("/profiles")
def get_profiles(request: Request) -> dict:
    """Control-plane capability profiles that drive Twin injection (gates / injection level /
    instruction style). These accumulate from production runs and capability evaluations."""
    from agent.model_forge.capability_scoring import build_capability_profile
    from agent.model_forge.profile_store import ProfileStore
    from agent.model_forge.route_fitness import derive_route_fitness

    root = resolve_atlas_ca_data_root(request)
    store = ProfileStore(Path(root) / "model_forge" / "profiles")
    out = []
    for profile in store.list_profiles():
        cap = build_capability_profile(profile, model_id=profile.model_id, provider_id=profile.provider_id)
        fitness = derive_route_fitness(profile.dimension_scores)
        best = max(fitness.items(), key=lambda kv: kv[1])[0].value if fitness else ""
        out.append({
            "model_id": profile.model_id,
            "provider_id": profile.provider_id,
            "version": profile.version,
            "sample_count": profile.sample_count,
            "dimension_scores": profile.dimension_scores,
            "known_weaknesses": list(cap.known_weaknesses),
            # Benchmark x injection: the route the model performs best at + per-route fitness.
            "best_route": best,
            "route_fitness": {r.value: v for r, v in fitness.items()},
        })
    return {"profiles": out, "count": len(out)}


class TwinEvaluateRequest(BaseModel):
    model_id: str
    provider_id: str = "local"
    base_url: str = ""  # local OpenAI-compatible server; required to run a real evaluation


@router.post("/evaluate")
def post_evaluate(payload: TwinEvaluateRequest, request: Request) -> dict:
    """Run the Twin control-plane adversarial capability evaluation against a model and
    record the evidence to the ProfileStore (so it shapes future Twin injection). Returns an
    ``unavailable`` verdict (and records nothing) when the model server is unreachable."""
    from agent.model_forge.profile_store import ProfileStore
    from agent.twin_control_plane.real_llm_eval import (
        build_local_model_chat, run_real_llm_evaluation,
    )
    from agent.twin_control_plane.contracts import (
        ExecutionPolicy, InstructionStyle, ModelCapabilityMode, TwinBrief,
        TwinInjectionLevel, default_hard_constraints,
    )
    from agent.model_forge.route_taxonomy import ForgeRoute

    base_url = payload.base_url or os.environ.get("FORGE_LOCAL_BASE_URL", "http://127.0.0.1:8080")
    chat = build_local_model_chat(base_url=base_url.rstrip("/"), model_id=payload.model_id, timeout_seconds=120.0)
    if not chat("You are terse.", "Reply with the single word READY.").available:
        return {"verdict": "unavailable", "recorded": False,
                "reason": f"model server unreachable at {base_url}"}

    policy = ExecutionPolicy(
        policy_id="twin_eval", route=ForgeRoute.DIRECT_PATCH, model_id=payload.model_id,
        instruction_style=InstructionStyle.CONSTRAINED_PATCH,
        model_capability_mode=ModelCapabilityMode.STANDARD,
        twin_injection_level=TwinInjectionLevel.CONSTRAINED_WITH_TESTS,
        hard_constraints=default_hard_constraints())
    brief = TwinBrief(brief_id="twin_eval", goal="capability evaluation")
    report = run_real_llm_evaluation(chat=chat, policy=policy, brief=brief, model_id=payload.model_id)

    # Record evidence-backed case results to the ProfileStore (per dimension).
    root = resolve_atlas_ca_data_root(request)
    store = ProfileStore(Path(root) / "model_forge" / "profiles")
    recorded = 0
    from agent.model_forge.candidate_evaluator import EvaluatorOutcome
    by_dim: dict[str, list[float]] = {}
    for case in report.to_case_results():
        if case.outcome == EvaluatorOutcome.UNAVAILABLE:
            continue  # unavailable is never a pass; do not move the score
        by_dim.setdefault(case.dimension, []).append(1.0 if case.outcome == EvaluatorOutcome.PASSED else 0.0)
    if by_dim:
        store.record_observation(
            model_id=payload.model_id, provider_id=payload.provider_id,
            dimensions={d: sum(v) / len(v) for d, v in by_dim.items()},
            source="capability_evaluation", evidence_refs=[report.report_id])
        recorded = len(by_dim)
    return {
        "verdict": report.verdict, "recorded": recorded > 0, "dimensions_recorded": recorded,
        "passed": report.passed, "failed": report.failed, "unavailable": report.unavailable,
        "report_id": report.report_id,
    }
