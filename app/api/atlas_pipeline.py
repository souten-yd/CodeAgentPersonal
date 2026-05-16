"""Minimal Atlas PlanPool and Pipeline API integration."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from agent.atlas_llm_json_adapter import AtlasLLMJsonAdapter

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from agent.atlas_continuation_service import AtlasContinuationService
from agent.atlas_journal import AtlasJournal
from agent.atlas_orchestration_summary import AtlasOrchestrationSummaryBuilder
from agent.atlas_pipeline_runner import AtlasPipelineRunner
from agent.atlas_pipeline_runner_schema import AtlasPipelineRunRequest
from agent.atlas_plan_pool_builder import AtlasPlanPoolBuilder
from agent.atlas_planner_bridge import AtlasPlannerBridge
from agent.atlas_planner_bridge_schema import AtlasPlannerBridgeRequest
from agent.atlas_plan_pool_schema import AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_recovery_service import AtlasRecoveryService


router = APIRouter(prefix="/api/atlas", tags=["atlas"])


class CreatePlanPoolRequest(BaseModel):
    input: str
    project_path: str = ""
    project_name: str = "CodeAgentPersonal"
    planning_depth: str = "standard"
    automation_level: str = "plan_then_ask"
    execution_strategy: str = "sequential"
    planner_mode: str = "auto"
    requirement_mode: str = "ask_when_needed"
    use_nexus: bool = True
    pool_id: str = ""
    plan_payload: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)
    workspace_id: str = "default"


class CreatePlanPoolResponse(BaseModel):
    pool_id: str
    status: str
    item_count: int
    plan_pool: dict
    checkpoint_path: str
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    planner_status: str = ""
    used_fallback: bool = False
    fallback_reason: str = ""
    questions: list[dict] = Field(default_factory=list)
    requirement: dict = Field(default_factory=dict)
    plan: dict = Field(default_factory=dict)
    review_result: dict = Field(default_factory=dict)
    orchestration_summary: dict = Field(default_factory=dict)


class PipelineDryRunRequest(BaseModel):
    pool_id: str
    run_id: str = ""
    max_items: int | None = None
    pause_after_each_item: bool = False
    stop_on_failure: bool = True
    workspace_id: str = "default"
    metadata: dict = Field(default_factory=dict)


class PipelineDryRunResponse(BaseModel):
    run_id: str
    pool_id: str
    status: str
    current_item_id: str
    completed_item_ids: list[str]
    failed_item_ids: list[str]
    blocked_item_ids: list[str]
    item_results: list[dict]
    events: list[dict]
    checkpoint_path: str
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    orchestration_summary: dict = Field(default_factory=dict)


class RecoveryResponse(BaseModel):
    recovery_summary: dict
    orchestration_summary: dict = Field(default_factory=dict)


class ContinuationResponse(BaseModel):
    workspace_id: str
    pool_id: str = ""
    run_id: str = ""
    status: str = ""
    current_goal: str = ""
    current_item_id: str = ""
    current_item_title: str = ""
    completed_count: int = 0
    failed_count: int = 0
    blocked_count: int = 0
    total_items: int = 0
    last_event_type: str = ""
    last_event_message: str = ""
    next_action: str = ""
    checkpoint_md_path: str = ""
    plan_pool_md_path: str = ""
    state_json_path: str = ""
    events_ndjson_path: str = ""
    continuation_prompt: str = ""
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


def _model_dump(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return dict(value)


def resolve_atlas_ca_data_root(request: Request | None = None) -> Path:
    if request is not None:
        state_value = getattr(request.app.state, "atlas_ca_data_dir", "")
        if state_value:
            return Path(str(state_value)).expanduser().resolve()
    env_value = os.environ.get("CODEAGENT_CA_DATA_DIR") or os.environ.get("CA_DATA")
    if env_value:
        return Path(env_value).expanduser().resolve()
    return Path("ca_data").resolve()


def _atlas_components(request: Request, workspace_id: str = "default") -> tuple[Path, AtlasPlanPoolStorage, AtlasJournal]:
    root = resolve_atlas_ca_data_root(request)
    return root, AtlasPlanPoolStorage(root), AtlasJournal(root, workspace_id=workspace_id or "default")





def _normalize_chat_completions_endpoint(raw_url: str) -> str:
    value = str(raw_url or "").strip()
    if not value:
        return ""
    if value.endswith("/v1/chat/completions"):
        return value
    if value.endswith("/v1"):
        return value + "/chat/completions"
    return value.rstrip("/") + "/v1/chat/completions"


def _resolve_atlas_llm_backend_base_url(app: Any) -> str:
    state = app.state
    for attr in ("llm_base_url", "model_backend_url"):
        raw = getattr(state, attr, "")
        endpoint = _normalize_chat_completions_endpoint(str(raw or ""))
        if endpoint:
            return endpoint.replace("/v1/chat/completions", "").rstrip("/")
    for key in ("CODEAGENT_LLM_BASE_URL", "OPENAI_BASE_URL", "LLAMA_SERVER_URL", "LLM_BASE_URL", "CODEAGENT_LLM_CHAT", "LLM_URL"):
        endpoint = _normalize_chat_completions_endpoint(os.environ.get(key, ""))
        if endpoint:
            return endpoint.replace("/v1/chat/completions", "").rstrip("/")
    return ""


def register_atlas_llm_json_adapter(app: Any) -> None:
    current = getattr(app.state, "atlas_llm_json_fn", None)
    if callable(current):
        return
    model = str(os.environ.get("CODEAGENT_MODEL") or os.environ.get("OPENAI_MODEL") or "").strip()
    base_url = _resolve_atlas_llm_backend_base_url(app)
    if not base_url:
        return
    app.state.atlas_llm_json_fn = AtlasLLMJsonAdapter(base_url=base_url, model=model)

def _resolve_callable_state(request: Request, name: str) -> Any:
    value = getattr(request.app.state, name, None)
    return value if callable(value) else None


def _resolve_atlas_llm_json_fn(request: Request) -> Any:
    return _resolve_callable_state(request, "atlas_llm_json_fn")


def _normalize_planner_mode(value: str) -> str:
    candidate = str(value or "auto").strip().lower()
    return candidate if candidate in {"auto", "real_planner", "fallback_only"} else "auto"


def _checkpoint_next_action(status: str) -> str:
    normalized = str(status or "").lower()
    if normalized == "waiting_for_clarification":
        return "Review planner questions and refine the goal before creating a PlanPool."
    if normalized == "ready":
        return "Start Dry-run to validate the generated PlanPool."
    if normalized in {"stale", "interrupted"}:
        return "Start a new dry-run from the recovered PlanPool."
    if normalized in {"paused", "approval_required"}:
        return "Review approval-required items before continuing."
    if normalized in {"completed", "completed_with_warnings"}:
        return "Review final report or create the next PlanPool."
    if normalized == "failed":
        return "Inspect failed items and prepare a debug follow-up."
    if normalized == "blocked":
        return "Review blocked items and policy reasons."
    return "Review the latest Atlas checkpoint."


@router.post("/plan-pools", response_model=CreatePlanPoolResponse)
def create_plan_pool(req: CreatePlanPoolRequest, request: Request) -> CreatePlanPoolResponse:
    root_goal = (req.input or "").strip()
    if not root_goal:
        raise HTTPException(status_code=400, detail="input is empty")

    register_atlas_llm_json_adapter(request.app)
    ca_data_root, storage, journal = _atlas_components(request, workspace_id=req.workspace_id)
    builder = AtlasPlanPoolBuilder()
    planner_status = "planned"
    used_fallback = False
    fallback_reason = ""
    questions: list[dict] = []
    requirement: dict = {}
    plan: dict = {}
    review_result: dict = {}
    bridge_warnings: list[str] = []
    bridge_errors: list[str] = []

    if req.plan_payload:
        payload = dict(req.plan_payload)
        payload.setdefault("metadata", {})
        if isinstance(payload["metadata"], dict):
            payload["metadata"].setdefault("source", "plan_payload")
        pool = builder.build_from_plan_payload(
            payload,
            root_goal=root_goal,
            project_path=req.project_path,
            project_name=req.project_name,
            planning_depth=req.planning_depth,
            automation_level=req.automation_level,
            execution_strategy=req.execution_strategy,
            pool_id=req.pool_id,
        )
        pool.metadata["source"] = "plan_payload"
        planner_status = "skipped"
    else:
        bridge = AtlasPlannerBridge(
            ca_data_dir=str(ca_data_root),
            llm_json_fn=_resolve_atlas_llm_json_fn(request),
            memory_search_fn=_resolve_callable_state(request, "atlas_memory_search_fn"),
            active_skills_fn=_resolve_callable_state(request, "atlas_active_skills_fn"),
            builder=builder,
        )
        bridge_result = bridge.create_plan_pool(
            AtlasPlannerBridgeRequest(
                input=root_goal,
                project_path=req.project_path,
                project_name=req.project_name,
                planning_depth=req.planning_depth,
                automation_level=req.automation_level,
                execution_strategy=req.execution_strategy,
                requirement_mode=req.requirement_mode,
                use_nexus=req.use_nexus,
                mode=_normalize_planner_mode(req.planner_mode),
                pool_id=req.pool_id,
                workspace_id=req.workspace_id,
                metadata=dict(req.metadata),
            )
        )
        planner_status = bridge_result.status
        used_fallback = bridge_result.used_fallback
        fallback_reason = bridge_result.fallback_reason
        questions = list(bridge_result.questions)
        requirement = dict(bridge_result.requirement)
        plan = dict(bridge_result.plan)
        review_result = dict(bridge_result.review_result)
        bridge_warnings = list(bridge_result.warnings)
        bridge_errors = list(bridge_result.errors)
        if bridge_result.status == "waiting_for_clarification" and bridge_result.pool is None:
            response_payload = {
                "pool_id": "",
                "status": "waiting_for_clarification",
                "item_count": 0,
                "plan_pool": {},
                "checkpoint_path": "",
                "warnings": bridge_warnings,
                "errors": bridge_errors,
                "planner_status": planner_status,
                "used_fallback": False,
                "fallback_reason": "",
                "questions": questions,
                "requirement": requirement,
                "plan": plan,
                "review_result": review_result,
            }
            response_payload["orchestration_summary"] = _model_dump(
                AtlasOrchestrationSummaryBuilder().build_from_create_plan_response(response_payload)
            )
            return CreatePlanPoolResponse(**response_payload)
        if bridge_result.pool is None:
            raise HTTPException(status_code=500, detail="planner bridge did not return a PlanPool")
        pool = bridge_result.pool

    pool.status = "ready"
    pool.metadata.update(
        {
            "api_created": True,
            "use_nexus_requested": bool(req.use_nexus),
            "planner_status": planner_status,
            "used_fallback": used_fallback,
            "fallback_reason": fallback_reason,
            **dict(req.metadata),
        }
    )

    storage.save_pool(pool)
    journal.save_plan_pool(pool)
    summary = AtlasOrchestrationSummaryBuilder().build_from_pool_and_state(pool, None)
    checkpoint_path = journal.write_checkpoint(
        pool=pool,
        next_action=_checkpoint_next_action(pool.status),
    )
    warnings = list(dict.fromkeys([*bridge_warnings, *list(pool.warnings)]))
    errors = list(dict.fromkeys([*bridge_errors, *list(pool.errors)]))
    summary.warnings = warnings
    summary.errors = errors
    summary.metadata.update({
        "planner_status": planner_status,
        "used_fallback": used_fallback,
        "fallback_reason": fallback_reason,
        "question_count": len(questions),
    })
    return CreatePlanPoolResponse(
        pool_id=pool.pool_id,
        status=pool.status,
        item_count=len(pool.items),
        plan_pool=_model_dump(pool),
        checkpoint_path=str(checkpoint_path),
        warnings=warnings,
        errors=errors,
        planner_status=planner_status,
        used_fallback=used_fallback,
        fallback_reason=fallback_reason,
        questions=questions,
        requirement=requirement,
        plan=plan,
        review_result=review_result,
        orchestration_summary=_model_dump(summary),
    )


@router.get("/plan-pools/{pool_id}")
def get_plan_pool(pool_id: str, request: Request) -> dict[str, Any]:
    _, storage, _ = _atlas_components(request)
    try:
        pool = storage.load_pool(pool_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="plan pool not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _model_dump(pool)


@router.get("/plan-pools/{pool_id}/markdown")
def get_plan_pool_markdown(pool_id: str, request: Request, workspace_id: str = "default") -> dict[str, str]:
    _, storage, journal = _atlas_components(request, workspace_id=workspace_id)
    markdown_path = Path(journal.paths(pool_id=pool_id).plan_pool_md)
    try:
        if not markdown_path.exists():
            pool = storage.load_pool(pool_id)
            markdown_path = journal.write_plan_pool_markdown(pool)
        return {"pool_id": pool_id, "markdown": markdown_path.read_text(encoding="utf-8")}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="plan pool markdown not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/pipeline/dry-run", response_model=PipelineDryRunResponse)
def run_pipeline_dry_run(req: PipelineDryRunRequest, request: Request) -> PipelineDryRunResponse:
    _, storage, journal = _atlas_components(request, workspace_id=req.workspace_id)
    try:
        pool = storage.load_pool(req.pool_id)
        runner = AtlasPipelineRunner(storage=storage)
        state = runner.run_dry_run(
            AtlasPipelineRunRequest(
                run_id=req.run_id,
                pool_id=req.pool_id,
                ca_data_root=str(resolve_atlas_ca_data_root(request)),
                execution_strategy=pool.execution_strategy,
                max_items=req.max_items,
                dry_run=True,
                stop_on_failure=req.stop_on_failure,
                pause_after_each_item=req.pause_after_each_item,
                metadata={"api_request": True, **dict(req.metadata)},
            )
        )
        journal.save_pipeline_state(pool.pool_id, state)
        for event in state.events:
            journal.append_event(pool.pool_id, state.run_id, event)
        updated_pool = storage.load_pool(pool.pool_id)
        summary = AtlasOrchestrationSummaryBuilder().build_from_pool_and_state(updated_pool, state)
        checkpoint_path = journal.write_checkpoint(
            pool=updated_pool,
            state=state,
            next_action=summary.next_action or _checkpoint_next_action(state.status),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="plan pool not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return PipelineDryRunResponse(
        run_id=state.run_id,
        pool_id=state.pool_id,
        status=state.status,
        current_item_id=state.current_item_id,
        completed_item_ids=list(state.completed_item_ids),
        failed_item_ids=list(state.failed_item_ids),
        blocked_item_ids=list(state.blocked_item_ids),
        item_results=[_model_dump(item_result) for item_result in state.item_results],
        events=[_model_dump(event) for event in state.events],
        checkpoint_path=str(checkpoint_path),
        warnings=list(state.warnings),
        errors=list(state.errors),
        orchestration_summary=_model_dump(summary),
    )


@router.get("/pipeline/status/{run_id}")
def get_pipeline_status(
    run_id: str,
    request: Request,
    pool_id: str = Query(..., min_length=1),
    workspace_id: str = "default",
) -> dict[str, Any]:
    _, _, journal = _atlas_components(request, workspace_id=workspace_id)
    try:
        state = journal.load_pipeline_state(pool_id, run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="pipeline state not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "run_id": state.run_id,
        "pool_id": state.pool_id,
        "state": _model_dump(state),
        "events": journal.read_events(pool_id, run_id, limit=25),
    }


@router.get("/pipeline/events/{pool_id}/{run_id}")
def get_pipeline_events(
    pool_id: str,
    run_id: str,
    request: Request,
    workspace_id: str = "default",
    limit: int = 100,
) -> dict[str, Any]:
    _, _, journal = _atlas_components(request, workspace_id=workspace_id)
    return {"pool_id": pool_id, "run_id": run_id, "events": journal.read_events(pool_id, run_id, limit=max(1, limit))}


@router.get("/continuation/latest", response_model=ContinuationResponse)
def get_continuation_latest(request: Request, workspace_id: str = "default") -> ContinuationResponse:
    try:
        _, _, journal = _atlas_components(request, workspace_id=workspace_id)
        summary = AtlasContinuationService(journal).build_latest_summary()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ContinuationResponse(**_model_dump(summary))


@router.get("/continuation/pools/{pool_id}", response_model=ContinuationResponse)
def get_continuation_pool(
    pool_id: str,
    request: Request,
    run_id: str = "",
    workspace_id: str = "default",
) -> ContinuationResponse:
    try:
        _, _, journal = _atlas_components(request, workspace_id=workspace_id)
        summary = AtlasContinuationService(journal).build_pool_summary(pool_id, run_id=run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ContinuationResponse(**_model_dump(summary))


@router.get("/recovery/latest", response_model=RecoveryResponse)
def get_recovery_latest(request: Request, workspace_id: str = "default") -> RecoveryResponse:
    _, _, journal = _atlas_components(request, workspace_id=workspace_id)
    summary = AtlasRecoveryService(journal).recover_latest()
    orchestration_summary = AtlasOrchestrationSummaryBuilder().build_from_recovery(summary)
    return RecoveryResponse(recovery_summary=_model_dump(summary), orchestration_summary=_model_dump(orchestration_summary))


@router.get("/recovery/pools/{pool_id}", response_model=RecoveryResponse)
def get_recovery_pool(pool_id: str, request: Request, workspace_id: str = "default") -> RecoveryResponse:
    _, _, journal = _atlas_components(request, workspace_id=workspace_id)
    summary = AtlasRecoveryService(journal).recover_pool(pool_id)
    orchestration_summary = AtlasOrchestrationSummaryBuilder().build_from_recovery(summary)
    return RecoveryResponse(recovery_summary=_model_dump(summary), orchestration_summary=_model_dump(orchestration_summary))
