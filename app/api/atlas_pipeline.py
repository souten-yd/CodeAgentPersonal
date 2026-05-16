"""Minimal Atlas PlanPool and Pipeline API integration."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from agent.atlas_journal import AtlasJournal
from agent.atlas_pipeline_runner import AtlasPipelineRunner
from agent.atlas_pipeline_runner_schema import AtlasPipelineRunRequest
from agent.atlas_plan_pool_builder import AtlasPlanPoolBuilder
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


class RecoveryResponse(BaseModel):
    recovery_summary: dict


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


def _checkpoint_next_action(status: str) -> str:
    if status == "completed":
        return "Review the completed Atlas dry-run and decide whether to continue with a gated follow-up."
    if status == "paused":
        return "Review paused Atlas pipeline state before continuing."
    if status == "failed":
        return "Inspect the failed Atlas pipeline state and prepare a debug plan."
    return "Review the latest Atlas checkpoint."


@router.post("/plan-pools", response_model=CreatePlanPoolResponse)
def create_plan_pool(req: CreatePlanPoolRequest, request: Request) -> CreatePlanPoolResponse:
    root_goal = (req.input or "").strip()
    if not root_goal:
        raise HTTPException(status_code=400, detail="input is empty")

    _, storage, journal = _atlas_components(request, workspace_id=req.workspace_id)
    builder = AtlasPlanPoolBuilder()
    if req.plan_payload:
        pool = builder.build_from_plan_payload(
            req.plan_payload,
            root_goal=root_goal,
            project_path=req.project_path,
            project_name=req.project_name,
            planning_depth=req.planning_depth,
            automation_level=req.automation_level,
            execution_strategy=req.execution_strategy,
            pool_id=req.pool_id,
        )
    else:
        pool = builder.build_fallback_pool(
            root_goal=root_goal,
            project_path=req.project_path,
            project_name=req.project_name,
            planning_depth=req.planning_depth,
            automation_level=req.automation_level,
            execution_strategy=req.execution_strategy,
            pool_id=req.pool_id,
        )
    pool.status = "ready"
    pool.metadata.update(
        {
            "api_created": True,
            "use_nexus_requested": bool(req.use_nexus),
            **dict(req.metadata),
        }
    )

    storage.save_pool(pool)
    journal.save_plan_pool(pool)
    checkpoint_path = journal.write_checkpoint(
        pool=pool,
        next_action="Review the generated Atlas PlanPool before starting a dry-run.",
    )
    return CreatePlanPoolResponse(
        pool_id=pool.pool_id,
        status=pool.status,
        item_count=len(pool.items),
        plan_pool=_model_dump(pool),
        checkpoint_path=str(checkpoint_path),
        warnings=list(pool.warnings),
        errors=list(pool.errors),
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
        checkpoint_path = journal.write_checkpoint(
            pool=updated_pool,
            state=state,
            next_action=_checkpoint_next_action(state.status),
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


@router.get("/recovery/latest", response_model=RecoveryResponse)
def get_recovery_latest(request: Request, workspace_id: str = "default") -> RecoveryResponse:
    _, _, journal = _atlas_components(request, workspace_id=workspace_id)
    summary = AtlasRecoveryService(journal).recover_latest()
    return RecoveryResponse(recovery_summary=_model_dump(summary))


@router.get("/recovery/pools/{pool_id}", response_model=RecoveryResponse)
def get_recovery_pool(pool_id: str, request: Request, workspace_id: str = "default") -> RecoveryResponse:
    _, _, journal = _atlas_components(request, workspace_id=workspace_id)
    summary = AtlasRecoveryService(journal).recover_pool(pool_id)
    return RecoveryResponse(recovery_summary=_model_dump(summary))
