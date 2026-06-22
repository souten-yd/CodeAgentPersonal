"""Forge backend API (PFG-19).

Read-mostly Forge surface for the UI. Composes the Forge service against the resolved
Atlas ca_data root. Secrets are never returned; disabled/unavailable provider states are
surfaced truthfully; mutating endpoints (stage/route policy, loadouts, arena run) never
bypass Safe Apply and never auto-cut-over production routing.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from agent.model_forge.eval_packs import CaseResult
from agent.project_twin.context_broker import TwinContextBroker
from agent.project_twin.contracts import ImpactRequest, TwinContextRequest
from agent.project_twin.store import TwinStoreError
from app.api.project_twin import _get_store as _project_twin_store
from app.api.twin_control import (
    TwinSettingsUpdate,
    get_profiles as get_twin_profiles,
    get_settings as get_twin_settings,
    post_settings as post_twin_settings,
)
from agent.model_forge.forge_service import ForgeService
from agent.model_forge.profile_store import ProfileStore
from agent.model_forge.twin_assist_contracts import TwinAssistEvaluationReport, TwinAssistRunRequest
from agent.model_forge.twin_assist_eval_packs import TWIN_ASSIST_PACKS, load_twin_assist_pack
from agent.model_forge.twin_assist_runner import TwinAssistRunner
from agent.model_forge.twin_readiness import TwinReadinessEvaluator
from agent.model_forge.twin_readiness_contracts import TwinReadinessRequest
from agent.model_forge.twin_slot_quality import TwinSlotQualityGate, TwinSlotQualityRequest
from agent.model_forge.twin_assist_postapply import PostApplyE2ERequest, PostApplyE2ERunner
from app.api.atlas_root import resolve_atlas_ca_data_root

router = APIRouter(prefix="/api/forge", tags=["forge"])


def _service(request: Request) -> ForgeService:
    return ForgeService(resolve_atlas_ca_data_root(request))


def _twin_assist_root(request: Request):
    return resolve_atlas_ca_data_root(request) / "model_forge" / "twin_assist_runs"


def _load_twin_assist_report(request: Request, run_id: str) -> TwinAssistEvaluationReport:
    if not run_id.startswith("twin_assist_") or not run_id.replace("_", "").isalnum():
        raise HTTPException(status_code=400, detail="invalid_run_id")
    path = _twin_assist_root(request) / run_id / "report.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="twin_assist_run_not_found")
    return TwinAssistEvaluationReport.model_validate_json(path.read_text(encoding="utf-8"))


class ArenaSpec(BaseModel):
    provider_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    route_id: str = Field(min_length=1)


class ArenaRunRequest(BaseModel):
    stage: str = Field(min_length=1)
    specs: list[ArenaSpec] = Field(default_factory=list)
    source_mode: str | None = None
    privacy_mode: str = "no_external_code"
    preset_id: str = ""
    preset_ids: list[str] = Field(default_factory=list)
    depth: str = "standard"
    task_id: str = ""
    # Optional: evaluate an already-running local model by port. When set, the local provider is
    # pointed here and probed LIVE so the arena's health gate sees it as READY.
    base_url: str = ""
    runtime_kind: str = ""


class StagePolicyRequest(BaseModel):
    stage: str = Field(min_length=1)
    mode: str = Field(min_length=1)
    allow_production_routing: bool = False
    fixed_provider_id: str = ""
    fixed_model_id: str = ""
    fallback_provider_id: str = ""
    fallback_model_id: str = ""
    reason: str = ""


class RoutePolicyRequest(BaseModel):
    change_class: str = Field(min_length=1)
    preferred_route: str = Field(min_length=1)


class LoadoutRequest(BaseModel):
    loadout_id: str = Field(min_length=1)
    display_name: str = ""
    description: str = ""
    source_mode: str = "local_only"
    stage_overrides: dict[str, str] = Field(default_factory=dict)
    provider_preferences: list[str] = Field(default_factory=list)
    method_preferences: dict[str, list[str]] = Field(default_factory=dict)
    method_fallbacks: dict[str, list[str]] = Field(default_factory=dict)
    role_assignments: list[dict] = Field(default_factory=list)
    risky: bool = False


class ForgeSettingsRequest(BaseModel):
    openrouter: dict = Field(default_factory=dict)
    local_provider: dict = Field(default_factory=dict)
    runtime_management: dict = Field(default_factory=dict)


class EvaluationRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    results: list[CaseResult] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)


class RealEvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    base_url: str = Field(min_length=1)
    dimensions: list[str] = Field(min_length=1)
    source_mode: str = "local_only"
    credential_env: str = ""
    timeout_seconds: float = Field(default=120.0, gt=0.0, le=600.0)


class AssistCapabilityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    base_url: str = Field(min_length=1)
    dimensions: list[str] = Field(min_length=1)
    source_mode: str = "local_only"
    credential_env: str = ""
    timeout_seconds: float = Field(default=120.0, gt=0.0, le=600.0)


class InjectionSweepRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    # Optional: when blank the server resolves the local runtime base URL (env / settings / the
    # llama.cpp 8080 / LM Studio 1234 default), so an already-running local model "just works".
    base_url: str = ""
    runtime_kind: str = ""
    dimensions: list[str] = Field(min_length=1)
    levels: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4])
    source_mode: str = "local_only"
    credential_env: str = ""
    timeout_seconds: float = Field(default=120.0, gt=0.0, le=600.0)
    # How far below the peak score still counts as "sufficient" when finding the lowest level.
    tolerance: float = Field(default=0.05, ge=0.0, le=1.0)
    # Strategy switch: "min_sufficient" (minimise injection) or "max_score" (maximise capability).
    objective: str = "min_sufficient"


class EvaluationRerunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str = Field(min_length=1)
    results: list[CaseResult] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)


class EvaluationModelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)


class GenerationPolicyPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider_id: str = ""
    model_id: str = ""
    change_class: str = "medium"
    task_category: str = "autonomous_codegen"
    optimal_routing: bool | None = None


class ForgeTwinSettingsUpdate(TwinSettingsUpdate):
    model_config = ConfigDict(extra="forbid")


class ForgeTwinContextRequest(TwinContextRequest):
    model_config = ConfigDict(extra="forbid")


class ForgeTwinImpactRequest(ImpactRequest):
    model_config = ConfigDict(extra="forbid")


@router.get("/status")
def get_status(request: Request) -> dict:
    return _service(request).status()


@router.get("/twin-assist/cases")
def get_twin_assist_cases(pack_id: str = "full") -> dict:
    try:
        cases = load_twin_assist_pack(pack_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"pack_id": pack_id, "packs": TWIN_ASSIST_PACKS, "cases": [case.model_dump(mode="json") for case in cases]}


@router.post("/twin-assist/run")
def post_twin_assist_run(request: Request, body: TwinAssistRunRequest) -> dict:
    report = TwinAssistRunner(_twin_assist_root(request)).run(body)
    return report.model_dump(mode="json")


@router.get("/twin-assist/runs/{run_id}")
def get_twin_assist_run(request: Request, run_id: str) -> dict:
    return _load_twin_assist_report(request, run_id).model_dump(mode="json")


@router.post("/twin-assist/runs/{run_id}/record-profile")
def post_twin_assist_record_profile(request: Request, run_id: str) -> dict:
    report = _load_twin_assist_report(request, run_id)
    profile = ProfileStore(resolve_atlas_ca_data_root(request) / "model_forge" / "profiles").record_twin_assist_report(report)
    return {"status": "observation_recorded", "production_routing_changed": False, "profile": profile.model_dump(mode="json")}


@router.post("/twin-assist/readiness")
def post_twin_assist_readiness(request: Request, body: TwinReadinessRequest) -> dict:
    report = TwinReadinessEvaluator().evaluate(body)
    path = _twin_assist_root(request) / "readiness" / f"{report.report_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return report.model_dump(mode="json")


@router.post("/twin-assist/slots/evaluate")
def post_twin_assist_slot_quality(body: TwinSlotQualityRequest) -> dict:
    return TwinSlotQualityGate().evaluate(slot=body.slot, project_root=body.project_root, forbidden_refs=body.forbidden_refs).model_dump(mode="json")


@router.post("/twin-assist/e2e/run")
def post_twin_assist_e2e(request: Request, body: PostApplyE2ERequest) -> dict:
    try:
        report = PostApplyE2ERunner(_twin_assist_root(request) / "postapply").run(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return report.model_dump(mode="json")


@router.get("/providers")
def get_providers(request: Request) -> dict:
    return {"providers": _service(request).providers()}


@router.post("/providers/{provider_id}/probe")
def post_provider_probe(request: Request, provider_id: str) -> dict:
    try:
        return {"provider": _service(request).probe_provider(provider_id)}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/models")
def get_models(request: Request) -> dict:
    return {"models": _service(request).models()}


@router.get("/settings")
def get_settings(request: Request) -> dict:
    return {"settings": _service(request).settings()}


@router.post("/settings")
def post_settings(request: Request, body: ForgeSettingsRequest) -> dict:
    try:
        return {"settings": _service(request).save_settings(body.model_dump())}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/providers/openrouter/catalog")
def get_openrouter_catalog(request: Request, force_refresh: bool = False) -> dict:
    return _service(request).openrouter_catalog(force_refresh=force_refresh)


@router.get("/local-catalog")
def get_local_catalog(request: Request, base_url: str = "", runtime_kind: str = "") -> dict:
    """Server-side proxy listing of a local OpenAI-compatible server's models.

    Lets the benchmark "LLM management tool" (Anvil) and the LM Studio option populate a model
    dropdown without a browser cross-origin call. Truthful status on an unreachable server.
    """
    return _service(request).local_catalog(base_url=base_url, runtime_kind=runtime_kind)


@router.get("/profiles")
def get_profiles(request: Request) -> dict:
    return {"profiles": _service(request).profiles_list()}


@router.get("/evaluation/cases")
def get_evaluation_cases(request: Request, dimension: str = "") -> dict:
    return _service(request).evaluation_cases(dimension)


@router.post("/evaluation/run")
def post_evaluation_run(request: Request, body: EvaluationRunRequest) -> dict:
    try:
        return _service(request).run_evaluation(
            provider_id=body.provider_id,
            model_id=body.model_id,
            results=body.results,
            dimensions=body.dimensions,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/evaluation/run-live")
def post_live_evaluation_run(request: Request, body: RealEvaluationRequest) -> dict:
    try:
        return _service(request).run_live_evaluation(**body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/evaluation/assist-capability")
def post_assist_capability(request: Request, body: AssistCapabilityRequest) -> dict:
    """Measure capability with vs without a Twin assist directive (補助有無), per dimension,
    and persist it so the Arena radar can overlay the Twin effect from real data."""
    try:
        return _service(request).assist_capability_profile(**body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/evaluation/injection-sweep")
def post_injection_sweep(request: Request, body: InjectionSweepRequest) -> dict:
    """Benchmark capability across varying Twin injection levels (0..4) and return the
    optimal injection amount per dimension and overall. Advisory; never changes routing."""
    try:
        return _service(request).injection_sweep_profile(**body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/evaluation/injection-sweep")
def get_injection_sweep(request: Request, provider_id: str, model_id: str) -> dict:
    """The last injection sweep persisted for this model, so the UI can restore it across restarts."""
    return {"record": _service(request).load_injection_sweep(provider_id, model_id)}


@router.post("/evaluation/rerun")
def post_evaluation_rerun(request: Request, body: EvaluationRerunRequest) -> dict:
    try:
        return _service(request).rerun_evaluation(body.run_id, results=body.results, dimensions=body.dimensions)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/evaluation/optimize")
def post_evaluation_optimize(request: Request, body: EvaluationModelRequest) -> dict:
    return _service(request).optimize_evaluation_preview(body.provider_id, body.model_id)


@router.get("/evaluation/model-profile")
def get_evaluation_model_profile(request: Request, provider_id: str, model_id: str) -> dict:
    return _service(request).evaluation_model_profile(provider_id, model_id)


@router.post("/atlas-generation-policy/preview")
def post_atlas_generation_policy_preview(request: Request, body: GenerationPolicyPreviewRequest) -> dict:
    """TA14: preview WHY a model/task/change-class would get a route/method/Twin-injection,
    without running generation. Advisory; never changes production routing."""
    from agent.model_forge.atlas_generation_policy import resolve_atlas_generation_policy
    from agent.model_forge.route_matrix import ChangeClass

    try:
        change = ChangeClass(body.change_class)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid_change_class") from exc
    resolution = resolve_atlas_generation_policy(
        change_class=change,
        task_category=body.task_category,
        provider_id=body.provider_id,
        model_id=body.model_id,
        profile_store_dir=str(resolve_atlas_ca_data_root(request) / "model_forge" / "profiles"),
        optimal_routing=body.optimal_routing,
    )
    return resolution.model_dump(mode="json")


@router.get("/atlas-generation-policy/default-presets")
def get_atlas_generation_policy_default_presets() -> dict:
    """TA15: explicit safe-default routing presets for unbenchmarked / optimal-routing-off
    runs, plus a check that they never contradict the RouteMatrix safe candidate set."""
    from agent.model_forge.default_generation_presets import (
        default_generation_presets,
        validate_presets_against_route_matrix,
    )

    violations = validate_presets_against_route_matrix()
    return {
        **default_generation_presets(),
        "route_matrix_consistent": not violations,
        "violations": violations,
    }


@router.get("/twin/settings")
def get_forge_twin_settings() -> dict:
    return {"settings": get_twin_settings(), "reversible": True}


@router.post("/twin/settings")
def post_forge_twin_settings(body: ForgeTwinSettingsUpdate) -> dict:
    return {"settings": post_twin_settings(body), "reversible": True}


@router.get("/twin/profiles")
def get_forge_twin_profiles(request: Request) -> dict:
    return get_twin_profiles(request)


@router.post("/twin/inspect/context")
def post_forge_twin_context(request: Request, body: ForgeTwinContextRequest) -> dict:
    try:
        result = TwinContextBroker(_project_twin_store(request)).build_slice(body)
    except TwinStoreError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.code}) from exc
    return {"read_only": True, "context": result.model_dump(mode="json")}


@router.post("/twin/inspect/impact")
def post_forge_twin_impact(request: Request, body: ForgeTwinImpactRequest) -> dict:
    result = _project_twin_store(request).assess_impact(body)
    return {"read_only": True, "impact": result.model_dump(mode="json")}


@router.get("/leaderboard")
def get_leaderboard(request: Request) -> dict:
    return {"leaderboard": _service(request).leaderboard()}


@router.get("/presets")
def get_presets(request: Request) -> dict:
    return {"presets": _service(request).presets()}


@router.post("/arena/run")
def post_arena_run(request: Request, body: ArenaRunRequest) -> dict:
    try:
        service = _service(request)
        # Local-by-port: point the local provider at the chosen server and probe it live so the
        # arena health gate sees READY (otherwise an unprobed local provider blocks the run).
        if body.base_url or body.runtime_kind:
            service.prepare_local_runtime(body.base_url, body.runtime_kind)
        return service.run_arena(
            stage=body.stage, specs=[s.model_dump() for s in body.specs],
            source_mode=body.source_mode, privacy_mode=body.privacy_mode,
            preset_id=body.preset_id, preset_ids=body.preset_ids,
            benchmark_depth=body.depth, task_id=body.task_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/arena/runs/{arena_run_id}")
def get_arena_run(request: Request, arena_run_id: str) -> dict:
    record = _service(request).get_arena_run(arena_run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="arena_run_not_found")
    return record


@router.post("/arena/candidates/{candidate_id}/proposal-draft")
def post_candidate_proposal_draft(request: Request, candidate_id: str) -> dict:
    try:
        return _service(request).create_candidate_proposal_draft(candidate_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/stage-policy")
def get_stage_policy(request: Request) -> dict:
    return {"stage_policy": _service(request).get_stage_policy()}


@router.post("/stage-policy")
def post_stage_policy(request: Request, body: StagePolicyRequest) -> dict:
    try:
        return _service(request).set_stage_policy(**body.model_dump())
    except PermissionError as exc:
        # No automatic cutover: an active production-routing mode needs acknowledgement.
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/route-policy")
def get_route_policy(request: Request) -> dict:
    return {"route_policy": _service(request).get_route_policy()}


@router.post("/route-policy")
def post_route_policy(request: Request, body: RoutePolicyRequest) -> dict:
    try:
        return _service(request).set_route_policy(
            change_class=body.change_class, preferred_route=body.preferred_route,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/loadouts")
def get_loadouts(request: Request) -> dict:
    return {"loadouts": _service(request).get_loadouts()}


@router.post("/loadouts")
def post_loadout(request: Request, body: LoadoutRequest) -> dict:
    try:
        return _service(request).save_loadout(body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class ApplyLoadoutRequest(BaseModel):
    acknowledge_risky: bool = False


class PortalEvidenceRequest(BaseModel):
    installation_id: str = Field(min_length=1)
    provider_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    dimension: str = "web_app"
    runtime_passed: bool | None = None
    user_decision: str = ""
    evidence_refs: list[str] = Field(default_factory=list)


@router.post("/portal-evidence")
def post_portal_evidence(request: Request, body: PortalEvidenceRequest) -> dict:
    try:
        return _service(request).record_portal_evidence(body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class CutoverRequest(BaseModel):
    stage: str = Field(min_length=1)
    acknowledge: bool = False


@router.get("/cutover")
def get_cutovers(request: Request) -> dict:
    return {"cutovers": _service(request).list_cutovers()}


@router.post("/cutover")
def post_cutover(request: Request, body: CutoverRequest) -> dict:
    try:
        return _service(request).cutover_stage(body.stage, acknowledge=body.acknowledge)
    except PermissionError as exc:
        # No automatic cutover: acknowledgement required.
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        # Missing/regressing shadow evidence blocks cutover.
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/cutover/{stage}/rollback")
def post_cutover_rollback(request: Request, stage: str) -> dict:
    return _service(request).rollback_stage(stage)


class CapsuleForgeMetaRequest(BaseModel):
    package_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    content_hash: str = Field(min_length=1)
    provider_id: str = ""
    model_id: str = ""
    route_id: str = ""
    stage: str = ""
    source_mode: str = ""
    arena_run_id: str = ""
    candidate_id: str = ""
    loadout_id: str = ""
    dimension: str = "greenfield"


class CapsuleReplayRequest(BaseModel):
    package_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    content_hash: str = Field(min_length=1)
    runtime_passed: bool | None = None
    user_decision: str = ""


@router.post("/capsule/forge-meta")
def post_capsule_forge_meta(request: Request, body: CapsuleForgeMetaRequest) -> dict:
    try:
        return _service(request).attach_capsule_forge_meta(body.model_dump())
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/capsule/forge-meta")
def get_capsule_forge_meta(request: Request, package_id: str, version: str, content_hash: str) -> dict:
    meta = _service(request).get_capsule_forge_meta(package_id, version, content_hash)
    return {"available": meta is not None, "forge_meta": meta}


@router.post("/capsule/replay")
def post_capsule_replay(request: Request, body: CapsuleReplayRequest) -> dict:
    try:
        return _service(request).record_capsule_replay(body.model_dump())
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/loadouts/{loadout_id}/apply")
def post_apply_loadout(request: Request, loadout_id: str, body: ApplyLoadoutRequest) -> dict:
    try:
        return _service(request).apply_loadout(loadout_id, acknowledge_risky=body.acknowledge_risky)
    except PermissionError as exc:
        # Risky loadout needs explicit confirmation.
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
