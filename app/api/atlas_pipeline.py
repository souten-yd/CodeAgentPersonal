"""Minimal Atlas PlanPool and Pipeline API integration."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from agent.atlas_llm_json_adapter import AtlasLLMJsonAdapter

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from agent.atlas_clarification_schema import AtlasClarificationSubmitRequest, AtlasClarificationSubmitResult
from agent.atlas_clarification_service import AtlasClarificationService
from agent.atlas_approval_service import AtlasApprovalService
from agent.atlas_continuation_service import AtlasContinuationService
from agent.atlas_journal import AtlasJournal
from agent.atlas_orchestration_summary import AtlasOrchestrationSummaryBuilder
from agent.atlas_pipeline_runner import AtlasPipelineRunner
from agent.atlas_pipeline_runner_schema import AtlasPipelineRunRequest
from agent.atlas_plan_pool_builder import AtlasPlanPoolBuilder
from agent.atlas_planner_bridge import AtlasPlannerBridge
from agent.atlas_planner_bridge_schema import AtlasPlannerBridgeRequest
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_recovery_service import AtlasRecoveryService
from agent.atlas_safe_apply_adapter import AtlasSafeApplyAdapter
from agent.atlas_safe_apply_execution_schema import AtlasSafeApplyExecutionRequest, AtlasSafeApplyExecutionResult
from agent.atlas_safe_apply_execution_service import AtlasSafeApplyExecutionService
from agent.atlas_verification_gate_schema import AtlasVerificationRequest, AtlasVerificationResult
from agent.atlas_verification_gate_service import AtlasVerificationGateService
from agent.atlas_debug_review_schema import AtlasDebugReviewRequest, AtlasDebugReviewResult
from agent.atlas_debug_review_service import AtlasDebugReviewService
from agent.atlas_patch_proposal_schema import AtlasPatchProposalRequest, AtlasPatchProposalResult
from agent.atlas_patch_proposal_service import AtlasPatchProposalService
import agent.debug_loop_runner as atlas_debug_loop_runner_module


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
    clarification_session_id: str = ""


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
    clarification_session_id: str = ""


class RecoveryResponse(BaseModel):
    recovery_summary: dict
    orchestration_summary: dict = Field(default_factory=dict)
    clarification_session_id: str = ""


class AtlasApprovalDecisionRequest(BaseModel):
    pool_id: str
    item_id: str
    run_id: str = ""
    decision: str
    reason: str = ""
    approver: str = "user"
    workspace_id: str = "default"
    metadata: dict = Field(default_factory=dict)


class AtlasApprovalDecisionResponse(BaseModel):
    pool_id: str
    item_id: str
    decision: str
    status: str
    approval_record: dict = Field(default_factory=dict)
    plan_pool: dict = Field(default_factory=dict)
    recovery_summary: dict = Field(default_factory=dict)
    orchestration_summary: dict = Field(default_factory=dict)
    continuation_prompt: str = ""
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


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




def _sync_pool_from_workspace_snapshot(storage: AtlasPlanPoolStorage, journal: AtlasJournal, pool_id: str) -> None:
    try:
        paths = journal.paths(pool_id=pool_id)
    except ValueError:
        return
    plan_pool_json = Path(paths.plan_pool_json)
    if not plan_pool_json.exists():
        return
    try:
        payload = json.loads(plan_pool_json.read_text(encoding='utf-8'))
    except Exception:
        return
    if str(payload.get('pool_id') or '') != pool_id:
        return
    if not storage.exists(pool_id) or plan_pool_json.stat().st_mtime >= storage.pool_path(pool_id).stat().st_mtime:
        try:
            if hasattr(AtlasPlanPool, 'model_validate'):
                pool = AtlasPlanPool.model_validate(payload)
            else:
                pool = AtlasPlanPool(**payload)
            storage.save_pool(pool)
        except Exception:
            return

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


def _resolve_atlas_test_command_runner(request: Request) -> Any:
    runner = getattr(request.app.state, "atlas_test_command_runner", None)
    if callable(runner):
        return runner()
    return runner


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
                "clarification_session_id": "",
            }
            clarification_service = AtlasClarificationService(journal=journal)
            session = clarification_service.create_session_from_plan_response(root_goal, response_payload, req.model_dump())
            clarification_service.save_session(session)
            response_payload["clarification_session_id"] = session.session_id
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
        clarification_session_id="",
    )




@router.post("/clarifications/answer")
def submit_clarification_answers(req: AtlasClarificationSubmitRequest, request: Request) -> dict[str, Any]:
    register_atlas_llm_json_adapter(request.app)
    ca_data_root, storage, journal = _atlas_components(request, workspace_id=req.workspace_id)
    service = AtlasClarificationService(journal=journal)
    session = service.load_session(req.session_id, req.workspace_id) if req.session_id else None
    if session is None:
        from agent.atlas_clarification_schema import AtlasClarificationSession
        session = AtlasClarificationSession(
            session_id=req.session_id or "clarification_ad_hoc",
            workspace_id=req.workspace_id,
            original_input=req.original_input,
            project_path=req.project_path,
            project_name=req.project_name,
            planner_mode=req.planner_mode,
            requirement_mode=req.requirement_mode,
            planning_depth=req.planning_depth,
            automation_level=req.automation_level,
            execution_strategy=req.execution_strategy,
            metadata=dict(req.metadata),
        )
    session.answers = list(req.answers)
    merged_input = service.merge_answers_into_input(session.original_input, session.questions, session.answers)
    merged_requirement = service.merge_answers_into_requirement(session.requirement, session.answers)
    builder = AtlasPlanPoolBuilder()
    bridge = AtlasPlannerBridge(ca_data_dir=str(ca_data_root), llm_json_fn=_resolve_atlas_llm_json_fn(request), memory_search_fn=_resolve_callable_state(request, "atlas_memory_search_fn"), active_skills_fn=_resolve_callable_state(request, "atlas_active_skills_fn"), builder=builder)
    try:
        result = bridge.create_plan_pool(AtlasPlannerBridgeRequest(input=merged_input, project_path=session.project_path, project_name=session.project_name, planning_depth=session.planning_depth, automation_level=session.automation_level, execution_strategy=session.execution_strategy, requirement_mode=session.requirement_mode, use_nexus=True, mode=_normalize_planner_mode(session.planner_mode), workspace_id=session.workspace_id, metadata=dict(session.metadata)))
        if result.status == "waiting_for_clarification" and result.pool is None:
            session.questions = list(result.questions)
            session.requirement = dict(result.requirement)
            session.status = "waiting_for_clarification"
            service.save_session(session)
            return AtlasClarificationSubmitResult(status="waiting_for_clarification", session=session, questions=list(result.questions), warnings=list(result.warnings), errors=list(result.errors), metadata={"clarification_session_id": session.session_id}).model_dump()
        pool = result.pool
        if pool is None:
            raise RuntimeError("planner bridge did not return a plan pool")
        pool.status = "ready"
        storage.save_pool(pool)
        journal.save_plan_pool(pool)
        summary = AtlasOrchestrationSummaryBuilder().build_from_pool_and_state(pool, None)
        journal.write_checkpoint(pool=pool, next_action=_checkpoint_next_action(pool.status))
        session.status = "planned"
        session.requirement = merged_requirement
        service.save_session(session)
        status = "fallback_used" if result.used_fallback else "planned"
        return AtlasClarificationSubmitResult(status=status, session=session, pool=_model_dump(pool), warnings=list(result.warnings), errors=list(result.errors), metadata={"pool_id": pool.pool_id, "item_count": len(pool.items), "orchestration_summary": _model_dump(summary)}).model_dump()
    except Exception as exc:
        fallback = AtlasPlanPoolBuilder().build_fallback_plan_pool(root_goal=merged_input, project_path=session.project_path, project_name=session.project_name, planning_depth=session.planning_depth, automation_level=session.automation_level, execution_strategy=session.execution_strategy)
        fallback.status = "ready"
        fallback.metadata.update({"source": "fallback", "fallback_reason": str(exc)})
        storage.save_pool(fallback)
        journal.save_plan_pool(fallback)
        summary = AtlasOrchestrationSummaryBuilder().build_from_pool_and_state(fallback, None)
        journal.write_checkpoint(pool=fallback, next_action=_checkpoint_next_action(fallback.status))
        session.status = "fallback_used"
        service.save_session(session)
        return AtlasClarificationSubmitResult(status="fallback_used", session=session, pool=_model_dump(fallback), warnings=["clarification_replan_failed", str(exc)], metadata={"pool_id": fallback.pool_id, "item_count": len(fallback.items), "orchestration_summary": _model_dump(summary)}).model_dump()

@router.get("/plan-pools/{pool_id}")
def get_plan_pool(pool_id: str, request: Request) -> dict[str, Any]:
    _, storage, _ = _atlas_components(request)
    try:
        pool = storage.load_pool(pool_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="plan pool not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    payload = _model_dump(pool)
    return {"plan_pool": payload, **payload}


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
        clarification_session_id="",
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





def _resolve_atlas_debug_loop_runner(request: Request, journal: AtlasJournal):
    runner = getattr(request.app.state, "atlas_debug_loop_runner", None)
    if callable(runner):
        return runner()
    if runner is not None:
        return runner
    runner_cls = getattr(atlas_debug_loop_runner_module, "DebugLoopRunner")
    return runner_cls(journal=journal)
@router.post("/verification/run", response_model=AtlasVerificationResult)
def run_verification(req: AtlasVerificationRequest, request: Request) -> AtlasVerificationResult:
    if ".." in req.pool_id or ".." in req.item_id:
        raise HTTPException(status_code=400, detail="invalid id")
    _, storage, journal = _atlas_components(request, workspace_id=req.workspace_id)
    _sync_pool_from_workspace_snapshot(storage, journal, req.pool_id)
    runner = _resolve_atlas_test_command_runner(request)
    service = AtlasVerificationGateService(journal=journal, storage=storage, test_runner=runner)
    try:
        result = service.verify_item(req)
    except FileNotFoundError:
        result = AtlasVerificationResult(pool_id=req.pool_id, item_id=req.item_id, run_id=req.run_id, status="blocked", warnings=["pool_not_found"])
    try:
        pool = storage.load_pool(req.pool_id)
        recovery = AtlasRecoveryService(journal).recover_pool(pool.pool_id).model_dump()
        orchestration = AtlasOrchestrationSummaryBuilder().build_from_pool_and_state(pool, None, recovery=recovery).model_dump()
        continuation = AtlasContinuationService(journal).build_pool_summary(req.pool_id, req.run_id)
        result.recovery_summary = recovery
        result.orchestration_summary = orchestration
        result.continuation_prompt = continuation.continuation_prompt
    except Exception as exc:
        result.warnings.append("verification_enrichment_failed")
        result.warnings.append(str(exc) or exc.__class__.__name__)
    return result

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




@router.post("/debug-review/run", response_model=AtlasDebugReviewResult)
def run_debug_review(req: AtlasDebugReviewRequest, request: Request) -> AtlasDebugReviewResult:
    if ".." in req.pool_id or ".." in req.item_id:
        raise HTTPException(status_code=400, detail="invalid identifier")
    _, storage, journal = _atlas_components(request, workspace_id=req.workspace_id)
    _sync_pool_from_workspace_snapshot(storage, journal, req.pool_id)
    runner = _resolve_atlas_debug_loop_runner(request, journal)
    service = AtlasDebugReviewService(journal=journal, storage=storage, debug_runner=runner)
    try:
        result = service.review_item(req)
    except FileNotFoundError:
        result = AtlasDebugReviewResult(pool_id=req.pool_id, item_id=req.item_id, run_id=req.run_id, status="blocked", warnings=["pool_not_found"])
    try:
        pool = storage.load_pool(req.pool_id)
        recovery = AtlasRecoveryService(journal).recover_pool(pool.pool_id).model_dump()
        orchestration = AtlasOrchestrationSummaryBuilder().build_from_pool_and_state(
            pool,
            None,
            recovery=recovery,
        ).model_dump()
        continuation = AtlasContinuationService(journal).build_pool_summary(req.pool_id, req.run_id)
        result.plan_pool = pool.model_dump()
        result.recovery_summary = recovery
        result.orchestration_summary = orchestration
        result.continuation_prompt = continuation.continuation_prompt
    except Exception as exc:
        result.warnings.append("debug_review_enrichment_failed")
        result.warnings.append(str(exc) or exc.__class__.__name__)
    return result


@router.post("/patch-proposals/generate", response_model=AtlasPatchProposalResult)
def generate_patch_proposal(req: AtlasPatchProposalRequest, request: Request) -> AtlasPatchProposalResult:
    if ".." in req.pool_id or ".." in req.item_id:
        raise HTTPException(status_code=400, detail="invalid identifier")
    _, storage, journal = _atlas_components(request, workspace_id=req.workspace_id)
    _sync_pool_from_workspace_snapshot(storage, journal, req.pool_id)
    service = AtlasPatchProposalService(journal=journal, storage=storage, llm_json_fn=_resolve_atlas_llm_json_fn(request))
    try:
        result = service.propose_for_item(req)
    except FileNotFoundError:
        result = AtlasPatchProposalResult(pool_id=req.pool_id, item_id=req.item_id, run_id=req.run_id, status="blocked", warnings=["pool_not_found"])
    try:
        pool = storage.load_pool(req.pool_id)
        recovery = AtlasRecoveryService(journal).recover_pool(pool.pool_id).model_dump()
        orchestration = AtlasOrchestrationSummaryBuilder().build_from_pool_and_state(pool, None, recovery=recovery).model_dump()
        continuation = AtlasContinuationService(journal).build_pool_summary(req.pool_id, req.run_id)
        result.plan_pool = pool.model_dump()
        result.recovery_summary = recovery
        result.orchestration_summary = orchestration
        result.continuation_prompt = continuation.continuation_prompt
    except Exception as exc:
        result.warnings.append("patch_proposal_enrichment_failed")
        result.warnings.append(str(exc) or exc.__class__.__name__)
    return result
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


@router.get("/approvals/pools/{pool_id}")
def get_approvals(pool_id: str, request: Request, workspace_id: str = Query("default")) -> dict:
    _, storage, journal = _atlas_components(request, workspace_id=workspace_id)
    _sync_pool_from_workspace_snapshot(storage, journal, pool_id)
    try:
        pool = storage.load_pool(pool_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="plan pool not found") from exc
    service = AtlasApprovalService(journal)
    data = service.list_pool_approvals(pool)
    data["pool_id"] = pool_id
    return data


@router.post("/approvals/decide", response_model=AtlasApprovalDecisionResponse)
def decide_approval(req: AtlasApprovalDecisionRequest, request: Request) -> AtlasApprovalDecisionResponse:
    _, storage, journal = _atlas_components(request, workspace_id=req.workspace_id)
    try:
        pool = storage.load_pool(req.pool_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="plan pool not found") from exc
    service = AtlasApprovalService(journal)
    try:
        approval_record = service.decide(pool, item_id=req.item_id, run_id=req.run_id, decision=req.decision, reason=req.reason, approver=req.approver, metadata=req.metadata)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    storage.save_pool(pool)
    journal.save_plan_pool(pool)
    recovery = AtlasRecoveryService(journal).recover_pool(pool.pool_id).model_dump()
    orchestration = AtlasOrchestrationSummaryBuilder().build_from_pool_and_state(pool, None, recovery=recovery).model_dump()
    continuation = AtlasContinuationService(journal).build_pool_summary(pool.pool_id, req.run_id).continuation_prompt
    journal.write_checkpoint(pool=pool, next_action=_checkpoint_next_action(pool.status))
    return AtlasApprovalDecisionResponse(pool_id=req.pool_id, item_id=req.item_id, decision=req.decision, status=pool.status, approval_record=approval_record, plan_pool=_model_dump(pool), recovery_summary=recovery, orchestration_summary=orchestration, continuation_prompt=continuation)


@router.post("/safe-apply/execute", response_model=AtlasSafeApplyExecutionResult)
def execute_safe_apply(req: AtlasSafeApplyExecutionRequest, request: Request) -> AtlasSafeApplyExecutionResult:
    if ".." in req.pool_id or ".." in req.item_id:
        raise HTTPException(status_code=400, detail="invalid id")
    _, storage, journal = _atlas_components(request, workspace_id=req.workspace_id)
    _sync_pool_from_workspace_snapshot(storage, journal, req.pool_id)
    adapter_obj = getattr(request.app.state, 'atlas_safe_apply_adapter', None)
    safe_apply_adapter = adapter_obj() if callable(adapter_obj) else adapter_obj
    if safe_apply_adapter is None:
        implementation_executor = getattr(request.app.state, 'atlas_implementation_executor', None)
        safe_apply_adapter = AtlasSafeApplyAdapter(implementation_executor=implementation_executor)
    service = AtlasSafeApplyExecutionService(journal=journal, storage=storage, safe_apply_adapter=safe_apply_adapter)
    try:
        result = service.execute_item(req)
    except FileNotFoundError:
        return AtlasSafeApplyExecutionResult(pool_id=req.pool_id, item_id=req.item_id, run_id=req.run_id, status="blocked", warnings=["pool_not_found"])
    except Exception as exc:
        return AtlasSafeApplyExecutionResult(pool_id=req.pool_id, item_id=req.item_id, run_id=req.run_id, status="failed", errors=[str(exc) or exc.__class__.__name__])

    recovery = AtlasRecoveryService(journal).recover_pool(req.pool_id)
    continuation = AtlasContinuationService(journal).build_pool_summary(req.pool_id, req.run_id)
    orchestration = AtlasOrchestrationSummaryBuilder().build_from_pool_and_state(storage.load_pool(req.pool_id), None, recovery=_model_dump(recovery).get("metadata") or {})
    result.recovery_summary = _model_dump(recovery)
    result.orchestration_summary = _model_dump(orchestration)
    result.continuation_prompt = continuation.continuation_prompt
    return result
