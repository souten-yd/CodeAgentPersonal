"""Minimal Atlas PlanPool and Pipeline API integration."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class _AppOnlyRequest:
    """Minimal stand-in for a FastAPI Request usable from a background thread.

    The plan-pool handler's helpers only ever read ``request.app`` / ``request.app.state`` (verified),
    which are app-scoped and thread-safe. This shim exposes just ``.app`` so the existing synchronous
    body can run unchanged off the request lifecycle.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

from agent.atlas_llm_json_adapter import AtlasLLMJsonAdapter

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from agent.atlas_clarification_schema import AtlasClarificationSubmitRequest, AtlasClarificationSubmitResult
from agent.atlas_clarification_execution_blocker import (
    clarification_execution_block_reasons as _clarification_execution_block_reasons,
)
from agent.atlas_clarification_replanning_service import AtlasClarificationReplanningService
from agent.atlas_clarification_service import AtlasClarificationService
from agent.atlas_approval_service import AtlasApprovalService, POOL_CRITICAL_DECISION_ITEM_ID
from agent.atlas_continuation_service import AtlasContinuationService
from agent.atlas_journal import AtlasJournal
from agent.atlas_orchestration_summary import AtlasOrchestrationSummaryBuilder
from agent.atlas_critique_gate_service import AtlasCritiqueGateService
from agent.atlas_clarification_gate_service import AtlasClarificationGateService
from agent.atlas_plan_quality_gate import apply_plan_quality_gate
from agent.atlas_repair_intent_classifier import classify_repair_intent
from agent.atlas_requirement_tracer import AtlasRequirementTracer
from agent.atlas_capability_preference_schema import (
    apply_preferences as _apply_capability_preferences,
    build_feature_summary as _build_capability_summary,
    get_default_preferences as _default_capability_preferences,
    normalize_ui_preferences as _normalize_capability_preferences,
)
from agent.atlas_automation_features import resolve_features as _resolve_automation_features
from agent.atlas_plan_depth_gate import evaluate_plan_depth
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
from agent.atlas_patch_proposal_approval_schema import AtlasPatchProposalApprovalRequest, AtlasPatchProposalApprovalResult
from agent.atlas_patch_proposal_approval_service import AtlasPatchProposalApprovalService
from agent.atlas_patch_proposal_planitem_schema import AtlasPatchProposalPlanItemDraftRequest, AtlasPatchProposalPlanItemDraftResult
from agent.atlas_patch_proposal_planitem_service import AtlasPatchProposalPlanItemDraftService
from agent.atlas_change_snapshot_restore_schema import AtlasChangeSnapshotRestoreRequest, AtlasChangeSnapshotRestoreResult
from agent.atlas_change_snapshot_restore_service import AtlasChangeSnapshotRestoreService
from agent.atlas_workspace_root import resolve_atlas_workspace_root
from agent.atlas_auto_policy_schema import AtlasAutomationDecision
from agent.atlas_auto_policy_presets import atlas_auto_policy_presets
from agent.atlas_automation_gate_service import AtlasAutomationGateService
from agent.atlas_auto_safe_apply_schema import AtlasAutoSafeApplyRequest, AtlasAutoSafeApplyResult
from agent.atlas_auto_safe_apply_service import AtlasAutoSafeApplyService
from agent.atlas_auto_verification_schema import AtlasAutoVerificationRequest, AtlasAutoVerificationResult
from agent.atlas_auto_verification_service import AtlasAutoVerificationService
from agent.atlas_failure_stop_schema import AtlasFailureStopSuggestion
from agent.atlas_failure_stop_service import AtlasFailureStopService
from agent.atlas_verification_allowlist import atlas_verification_allowlist
from agent.atlas_repo_context_schema import AtlasRepoContextRequest
from agent.atlas_repo_context_service import AtlasRepoContextService
from agent.atlas_repo_context_planner_packager import AtlasRepoContextPlannerPackager
from agent.atlas_verification_planning_service import AtlasVerificationPlanningService
from agent.atlas_verification_planning_schema import AtlasVerificationPlanningRequest
from agent.atlas_plan_item_impact_map_service import AtlasPlanItemImpactMapService
from agent.atlas_plan_item_impact_map_schema import AtlasPlanItemImpactMapRequest
from agent.atlas_planner_packaging_v2_service import AtlasPlannerPackagingV2Service
from agent.atlas_planner_packaging_v2_schema import AtlasPlannerPackagingV2Request
from agent.atlas_verification_recommendation_schema import AtlasVerificationRecommendationRequest
from agent.atlas_verification_recommendation_service import AtlasVerificationRecommendationService
from agent.atlas_verification_recommendation_handoff_service import AtlasVerificationRecommendationHandoffService
from agent.atlas_verification_recommendation_handoff_schema import AtlasVerificationRecommendationHandoffRequest
import agent.debug_loop_runner as atlas_debug_loop_runner_module
from app.api.atlas_root import resolve_atlas_ca_data_root
from app.atlas.level1_dry_run_result_artifact_capture import capture_level1_dry_run_result_artifact
from app.atlas.level1_dry_run_endpoint_skeleton import build_level1_dry_run_only_result
from app.atlas.workflow_state_contract import build_read_only_workflow_state
from app.atlas.level1_guarded_execution import Level1GuardedExecutionSkeleton


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
    changed_files: list[str] = Field(default_factory=list)
    target_files: list[str] = Field(default_factory=list)
    enable_repo_context: bool = True
    repo_context_mode: str = "scope_summary"
    capability_preferences: dict = Field(default_factory=dict)
    # Human-in-the-loop automation features (critical_handling / clarification_mode /
    # quality_gate_enforcement / requirement_coverage_enforcement).
    # Empty -> server-side default (atlas_automation_features).
    automation_features: dict = Field(default_factory=dict)


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


class Level1DryRunOnlyRequest(BaseModel):
    workspace_id: str = "default"
    pool_id: str = ""
    item_id: str = ""
    action_id: str = ""
    command_id: str = ""
    risk_level: str = "unknown"
    dry_run_summary: str = ""
    metadata: dict = Field(default_factory=dict)


class Level1DryRunResultArtifactCaptureRequest(BaseModel):
    dry_run_result: dict = Field(default_factory=dict)
    workspace_id: str = "default"


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


class AtlasAutomationDecisionRequest(BaseModel):
    pool_id: str
    item_id: str
    preset_id: str = "manual_only"
    phase: str = "pre_safe_apply"
    workspace_id: str = "default"


class AtlasAutomationDecisionResponse(BaseModel):
    decision: AtlasAutomationDecision
    plan_pool: dict = Field(default_factory=dict)
    orchestration_summary: dict = Field(default_factory=dict)
    continuation_prompt: str = ""


class AtlasAutoSafeApplyAndVerifyRequest(BaseModel):
    pool_id: str
    item_id: str
    preset_id: str = "guarded_low_risk"
    workspace_id: str = "default"
    run_id: str = ""
    command_id: str = ""
    metadata: dict = Field(default_factory=dict)


class AtlasAutoSafeApplyAndVerifyResult(BaseModel):
    auto_safe_apply_result: dict = Field(default_factory=dict)
    auto_verification_result: dict = Field(default_factory=dict)
    status: str = "failed"
    failure_stop_suggestion: dict = Field(default_factory=dict)
    continuation_prompt: str = ""




class AtlasFailureSuggestionRequest(BaseModel):
    pool_id: str
    item_id: str
    run_id: str = ""
    phase: str = "auto_verification"
    workspace_id: str = "default"

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


def _resolve_pool_workspace_root(*, storage: AtlasPlanPoolStorage, ca_data_root: Path, workspace_id: str, pool_id: str) -> Path:
    project_path = ""
    try:
        pool = storage.load_pool(pool_id)
        project_path = str(getattr(pool, "project_path", "") or "")
    except Exception:
        project_path = ""
    return resolve_atlas_workspace_root(ca_data_root=ca_data_root, workspace_id=workspace_id, project_path=project_path)


def _validate_restore_manifest_path(manifest_path: Path, ca_data_root: Path) -> None:
    resolved = manifest_path.expanduser().resolve()
    if not resolved.exists():
        raise HTTPException(status_code=400, detail="manifest_not_found")
    data_root = ca_data_root.resolve()
    snapshot_root = (data_root / "atlas" / "workspaces").resolve()
    if not (resolved == data_root or data_root in resolved.parents or resolved == snapshot_root or snapshot_root in resolved.parents):
        raise HTTPException(status_code=400, detail="manifest_path_outside_allowed_roots")


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
    if normalized in {"waiting_for_clarification", "needs_scope_confirmation"}:
        return "Answer clarification so Atlas can revise the plan and rerun gates."
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


def _sp_str(value: Any, limit: int = 600) -> str:
    s = str(value or "").strip()
    return s[:limit]


def _sp_list(value: Any, *, max_items: int = 20, item_limit: int = 300) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        return []
    out: list[str] = []
    for v in value:
        s = str(v or "").strip()
        if s:
            out.append(s[:item_limit])
        if len(out) >= max_items:
            break
    return out


def _planner_metadata_with_repair(req: CreatePlanPoolRequest, changed_files_for_context: list[str]) -> dict:
    """Augment planner metadata with repair intent (PR-8d). When the user prompt is repair-like
    and previous changed files are known, expose them as primary implementation targets so the
    planner prioritizes fixing the affected file rather than drifting to tests/clarification."""
    md = dict(req.metadata)
    repair = classify_repair_intent(req.input or "", previous_changed_files=changed_files_for_context)
    md["repair_intent"] = repair
    if repair.get("is_repair") and repair.get("primary_target_files"):
        md["primary_implementation_targets"] = list(repair["primary_target_files"])
    return md


def _build_strategic_plan_summary(*, requirement: dict, plan: dict, review_result: dict, pool: Any) -> dict:
    """Compact, size-bounded strategic plan for the UI to render a Claude/Codex-style plan card.

    Sourced from the planner's requirement/plan/review dicts (all available at creation). Persisted on
    pool.metadata so it survives the async job and reaches the frontend via GET /plan-pools/{id}
    (which returns the pool). Research/critique are included when the planner surfaced them on the plan.
    """
    requirement = requirement if isinstance(requirement, dict) else {}
    plan = plan if isinstance(plan, dict) else {}
    review_result = review_result if isinstance(review_result, dict) else {}

    steps_raw = plan.get("implementation_steps") if isinstance(plan.get("implementation_steps"), list) else []
    steps: list[dict] = []
    for s in steps_raw[:30]:
        if not isinstance(s, dict):
            continue
        steps.append({
            "title": _sp_str(s.get("title")),
            "description": _sp_str(s.get("description"), 600),
            "target_files": _sp_list(s.get("target_files"), max_items=10, item_limit=200),
            "action_type": _sp_str(s.get("action_type"), 40),
            "risk_level": _sp_str(s.get("risk_level"), 20),
            "verification": _sp_str(s.get("verification"), 300),
            "rollback": _sp_str(s.get("rollback"), 300),
        })
    # Fallback: when the plan dict has no steps (e.g. plan_payload path), derive them from the pool
    # items so the strategic card still shows per-step detail.
    if not steps:
        for it in (getattr(pool, "items", None) or [])[:30]:
            md = getattr(it, "metadata", {}) or {}
            steps.append({
                "title": _sp_str(getattr(it, "title", "")),
                "description": _sp_str(getattr(it, "description", "") or getattr(it, "goal", ""), 600),
                "target_files": _sp_list(getattr(it, "target_files", []), max_items=10, item_limit=200),
                "action_type": _sp_str(md.get("action_type"), 40),
                "risk_level": _sp_str(getattr(it, "risk_level", ""), 20),
                "verification": _sp_str("; ".join(getattr(it, "done_definition", []) or []), 300),
                "rollback": _sp_str("; ".join(getattr(it, "rollback_plan", []) or []), 300),
            })

    findings_raw = review_result.get("findings") if isinstance(review_result.get("findings"), list) else []
    findings: list[dict] = []
    for f in findings_raw[:20]:
        if not isinstance(f, dict):
            continue
        findings.append({
            "title": _sp_str(f.get("title"), 200),
            "severity": _sp_str(f.get("severity"), 20),
            "category": _sp_str(f.get("category"), 40),
            "recommendation": _sp_str(f.get("recommendation"), 300),
        })

    summary: dict = {
        "goal": _sp_str(requirement.get("interpreted_goal") or plan.get("user_goal") or pool.root_goal, 600),
        "requirement_summary": _sp_str(plan.get("requirement_summary") or requirement.get("user_intent"), 600),
        "scope": _sp_list(requirement.get("scope")),
        "out_of_scope": _sp_list(requirement.get("out_of_scope")),
        "assumptions": _sp_list(plan.get("assumptions") or requirement.get("assumptions")),
        "constraints": _sp_list(plan.get("constraints") or requirement.get("constraints")),
        "selected_architecture": _sp_str(plan.get("selected_architecture"), 400),
        "architecture_options": _sp_list(plan.get("architecture_options"), max_items=6, item_limit=300),
        "rejected_architectures": _sp_list(plan.get("rejected_architectures"), max_items=6, item_limit=300),
        "steps": steps,
        "risks": _sp_list(plan.get("risks") or requirement.get("risks")),
        "test_plan": _sp_list(plan.get("test_plan")),
        "verification_plan": _sp_list(plan.get("verification_plan")),
        "done_definition": _sp_list(plan.get("done_definition") or requirement.get("done_definition")),
        "review": {
            "overall_risk": _sp_str(review_result.get("overall_risk"), 20),
            "summary": _sp_str(review_result.get("summary"), 600),
            "recommended_next_action": _sp_str(review_result.get("recommended_next_action"), 40),
            "findings": findings,
        },
    }

    # Research findings / adversarial critique are surfaced by the planner on the plan dict when present.
    research = plan.get("research_findings") if isinstance(plan.get("research_findings"), dict) else {}
    if research:
        summary["research"] = {
            "recommended_approach": _sp_str(research.get("recommended_approach"), 600),
            "key_findings": _sp_list(research.get("key_findings")),
            "relevant_files": _sp_list(research.get("relevant_files"), max_items=15, item_limit=200),
            "risks": _sp_list(research.get("risks")),
        }
    critique = plan.get("adversarial_critique") if isinstance(plan.get("adversarial_critique"), dict) else {}
    if critique:
        c_findings_raw = critique.get("findings") if isinstance(critique.get("findings"), list) else []
        c_findings: list[dict] = []
        for f in c_findings_raw[:20]:
            if not isinstance(f, dict):
                continue
            c_findings.append({
                "angle": _sp_str(f.get("angle"), 40),
                "severity": _sp_str(f.get("severity"), 20),
                "title": _sp_str(f.get("title"), 200),
                "recommendation": _sp_str(f.get("recommendation"), 300),
            })
        summary["adversarial_critique"] = {
            "consensus_risk": _sp_str(critique.get("consensus_risk"), 20),
            "requires_revision": bool(critique.get("requires_revision")),
            "findings": c_findings,
        }
    return summary


def _plan_pool_jobs_dir(ca_data_root: Path) -> Path:
    d = Path(ca_data_root) / "atlas" / "plan_pool_jobs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_plan_pool_job(ca_data_root: Path, pool_id: str, payload: dict) -> None:
    try:
        path = _plan_pool_jobs_dir(ca_data_root) / f"{pool_id}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


@router.post("/plan-pools")
def create_plan_pool(req: CreatePlanPoolRequest, request: Request, sync: int = Query(0)) -> Any:
    root_goal = (req.input or "").strip()
    if not root_goal:
        raise HTTPException(status_code=400, detail="input is empty")

    # Default: run the slow LLM planning on a background thread and return a job handle immediately,
    # so a slow model can't blow past the proxy (Cloudflare/runpod) 524 timeout. ?sync=1 keeps the
    # legacy blocking behavior for tests / direct callers.
    if not sync:
        import threading
        import uuid as _uuid

        register_atlas_llm_json_adapter(request.app)
        ca_data_root, _storage, _journal = _atlas_components(request, workspace_id=req.workspace_id)
        pool_id = f"pool_{_uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        _write_plan_pool_job(ca_data_root, pool_id, {"pool_id": pool_id, "status": "queued", "created_at": now})
        app_ref = request.app

        def _runner() -> None:
            _write_plan_pool_job(ca_data_root, pool_id, {"pool_id": pool_id, "status": "running", "created_at": now})
            try:
                result = _create_plan_pool_core(req, app_ref, forced_pool_id=pool_id)
                _write_plan_pool_job(ca_data_root, pool_id, {
                    "pool_id": result.pool_id, "status": "ready", "created_at": now,
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                })
            except Exception as exc:  # noqa: BLE001 — never leak a raw traceback to the UI.
                _write_plan_pool_job(ca_data_root, pool_id, {
                    "pool_id": pool_id, "status": "failed",
                    "error": "プラン作成に失敗しました。再実行してください。",
                    "error_kind": exc.__class__.__name__,
                    "created_at": now, "finished_at": datetime.now(timezone.utc).isoformat(),
                })

        threading.Thread(target=_runner, daemon=True).start()
        return {"pool_id": pool_id, "status": "queued"}

    return _create_plan_pool_core(req, request.app)


@router.get("/plan-pools/{pool_id}/status")
def get_plan_pool_status(pool_id: str, request: Request, workspace_id: str = Query("default")) -> dict[str, Any]:
    ca_data_root, _storage, _journal = _atlas_components(request, workspace_id=workspace_id)
    path = _plan_pool_jobs_dir(ca_data_root) / f"{pool_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail={"error": "plan_pool_job_not_found", "pool_id": pool_id})
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"pool_id": pool_id, "status": "running"}


def _create_plan_pool_core(req: CreatePlanPoolRequest, app: Any, *, forced_pool_id: str = "") -> CreatePlanPoolResponse:
    root_goal = (req.input or "").strip()
    request = _AppOnlyRequest(app)
    # Keep the created pool's id equal to the async job id so the client can poll by it and then fetch
    # the pool at the same id.
    if forced_pool_id:
        req = req.model_copy(update={"pool_id": forced_pool_id})

    register_atlas_llm_json_adapter(request.app)
    ca_data_root, storage, journal = _atlas_components(request, workspace_id=req.workspace_id)
    # Bind the pool to the SELECTED project's working directory so generated files land where the
    # project drawer lists/downloads them (ca_data/atlas/projects/{name}/work). Without this the
    # workspace resolver falls back to a divergent ca_data/atlas/workspaces/{name} location and the
    # deliverables end up in a different folder than the project the user sees. Only applied when a
    # concrete project (non-default workspace_id) is given and no explicit project_path was supplied.
    if not (req.project_path or "").strip():
        ws = str(req.workspace_id or "").strip()
        if ws and ws != "default" and "/" not in ws and "\\" not in ws and ".." not in ws:
            work_dir = Path(ca_data_root) / "atlas" / "projects" / ws / "work"
            try:
                work_dir.mkdir(parents=True, exist_ok=True)
                req = req.model_copy(update={"project_path": str(work_dir.resolve())})
            except Exception:
                pass
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
    repo_context_package_payload: dict = {}
    planner_context_text: str = ""
    planner_context_text_v2: str = ""
    planner_packaging_v2_payload: dict = {}
    impacted_test_recommendation_payload: dict = {}
    verification_plan_payload: dict = {}
    plan_item_impact_map_payload: dict = {}
    changed_files_for_context = list(req.changed_files or [])
    target_files_for_context = list(req.target_files or [])
    if not changed_files_for_context and isinstance(req.metadata, dict):
        changed_files_for_context = list(req.metadata.get("changed_files") or [])
    if not target_files_for_context and isinstance(req.metadata, dict):
        target_files_for_context = list(req.metadata.get("target_files") or [])

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
        if req.enable_repo_context and (req.project_path or "").strip():
            try:
                repo_req = AtlasRepoContextRequest(
                    workspace_id=req.workspace_id,
                    project_path=req.project_path,
                    changed_files=changed_files_for_context,
                    target_files=target_files_for_context,
                    goal=root_goal,
                    allow_build_if_missing=False,
                    mode="scope_summary",
                )
                packager = AtlasRepoContextPlannerPackager(data_root=ca_data_root)
                pkg = packager.build_package(repo_req)
                repo_context_package_payload = pkg.model_dump()
                planner_context_text = pkg.planner_context_text
                impacted_test_recommendation_payload = packager.build_impacted_test_recommendation(repo_req).model_dump()
                verification_plan_payload = AtlasVerificationPlanningService(data_root=ca_data_root).build_plan(AtlasVerificationPlanningRequest(workspace_id=req.workspace_id, project_path=req.project_path, goal=root_goal, changed_files=changed_files_for_context, target_files=target_files_for_context)).model_dump()
                plan_item_impact_map_payload = AtlasPlanItemImpactMapService(data_root=ca_data_root).build_map(AtlasPlanItemImpactMapRequest(workspace_id=req.workspace_id, project_path=req.project_path, pool_id=req.pool_id, goal=root_goal, changed_files=changed_files_for_context, target_files=target_files_for_context, plan_pool={})).model_dump()
            except Exception:
                repo_context_package_payload = {"status": "failed_internal", "confidence": "unknown"}
                planner_context_text = "Repo Context status: failed_internal. Advisory only."
                impacted_test_recommendation_payload = {"status": "missing", "executed": False}
                verification_plan_payload = {"status":"missing","metadata":{"executed":False,"advisory_only":True,"auto_verification_triggered":False,"auto_test_execution_triggered":False}}

        
        try:
            planner_packaging_v2_payload = AtlasPlannerPackagingV2Service(data_root=ca_data_root).build_package(AtlasPlannerPackagingV2Request(workspace_id=req.workspace_id, project_path=req.project_path, pool_id=req.pool_id, goal=root_goal, changed_files=changed_files_for_context, target_files=target_files_for_context, plan_pool={}, repo_context_package=repo_context_package_payload, plan_item_impact_map=plan_item_impact_map_payload, context_refresh_v2={}, include_repo_context=req.enable_repo_context, include_plan_item_impact_map=req.enable_repo_context, include_context_refresh_v2=req.enable_repo_context)).model_dump()
            planner_context_text_v2 = planner_packaging_v2_payload.get("planner_context_text", "")
            if planner_context_text_v2:
                planner_context_text = planner_context_text_v2
        except Exception:
            planner_packaging_v2_payload = {"status": "missing", "advisory_only": True, "executed": False}

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
                metadata=_planner_metadata_with_repair(req, changed_files_for_context),
                repo_context_package=repo_context_package_payload,
                planner_context_text=planner_context_text,
                planner_context_text_v2=planner_context_text_v2,
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
    if req.enable_repo_context and (req.project_path or "").strip():
        try:
            repo_context = AtlasRepoContextService(data_root=ca_data_root).build_plan_scope_summary(
                AtlasRepoContextRequest(
                    workspace_id=req.workspace_id,
                    project_path=req.project_path,
                    changed_files=changed_files_for_context,
                    target_files=target_files_for_context,
                    goal=root_goal,
                    mode="scope_summary",
                    allow_build_if_missing=False,
                )
            )
            pool.metadata["repo_context"] = {
                "status": repo_context.status,
                "project_hash": (repo_context.repo_index_snapshot or {}).get("project_hash", ""),
                "index_run_id": (repo_context.repo_index_snapshot or {}).get("index_run_id", ""),
                "target_files": repo_context.target_files[:30],
                "changed_files": repo_context.changed_files[:30],
                "impacted_files": repo_context.impacted_files[:100],
                "related_tests": repo_context.related_tests[:50],
                "confidence": repo_context.confidence,
                "warnings": ((repo_context.repo_index_snapshot or {}).get("warnings", [])[:10]),
                "errors": ((repo_context.repo_index_snapshot or {}).get("errors", [])[:10]),
            }
        except Exception:
            pool.metadata["repo_context"] = {"status": "failed_internal", "confidence": "unknown"}

    if repo_context_package_payload:
        pool.metadata["repo_context_package"] = {
            "status": repo_context_package_payload.get("status", "missing"),
            "index_run_id": repo_context_package_payload.get("index_run_id", ""),
            "impacted_files": list(repo_context_package_payload.get("impacted_files", []))[:50],
            "related_tests": list(repo_context_package_payload.get("related_tests", []))[:30],
            "confidence": repo_context_package_payload.get("confidence", "unknown"),
        }
    if req.enable_repo_context and (req.project_path or "").strip() and pool:
        try:
            plan_item_impact_map_payload = AtlasPlanItemImpactMapService(data_root=ca_data_root).build_map(AtlasPlanItemImpactMapRequest(workspace_id=req.workspace_id, project_path=req.project_path, pool_id=pool.pool_id, goal=root_goal, changed_files=changed_files_for_context, target_files=target_files_for_context, plan_pool=_model_dump(pool))).model_dump()
        except Exception:
            plan_item_impact_map_payload = {"status": "missing", "metadata": {"advisory_only": True, "executed": False, "auto_verification_triggered": False, "auto_test_execution_triggered": False}}

    if req.enable_repo_context and (req.project_path or "").strip() and pool:
        try:
            verification_recommendation_payload = AtlasVerificationRecommendationService(data_root=ca_data_root).recommend(
                AtlasVerificationRecommendationRequest(
                    workspace_id=req.workspace_id,
                    project_path=req.project_path,
                    pool_id=pool.pool_id,
                    goal=root_goal,
                    changed_files=changed_files_for_context,
                    target_files=target_files_for_context,
                    plan_pool=_model_dump(pool),
                    planner_packaging_v2=planner_packaging_v2_payload or {},
                    planner_context_text_v2=planner_context_text_v2,
                    include_planner_packaging_v2=True,
                    allow_build_if_missing=False,
                )
            ).model_dump()
        except Exception:
            verification_recommendation_payload = {"status": "failed", "confidence": "unknown", "warnings": ["verification_recommendation_failed"], "metadata": {"advisory_only": True, "executed": False, "auto_verification_triggered": False, "auto_test_execution_triggered": False, "commands_are_suggestions_only": True}}
        pool.metadata["verification_recommendation"] = {
            "status": verification_recommendation_payload.get("status", "missing"),
            "confidence": verification_recommendation_payload.get("confidence", "unknown"),
            "impacted_files": list(verification_recommendation_payload.get("impacted_files", []))[:30],
            "related_tests": list(verification_recommendation_payload.get("related_tests", []))[:20],
            "recommended_commands": list(verification_recommendation_payload.get("recommended_commands", []))[:5],
            "manual_verification_steps": list(verification_recommendation_payload.get("manual_verification_steps", []))[:10],
            "ci_selection_hints_count": len(list(verification_recommendation_payload.get("ci_selection_hints", []))),
            "evidence_count": len(list(verification_recommendation_payload.get("evidence", []))),
            "advisory_only": True,
            "executed": False,
            "auto_verification_triggered": False,
            "auto_test_execution_triggered": False,
            "commands_are_suggestions_only": True,
        }
        try:
            handoff = AtlasVerificationRecommendationHandoffService(data_root=ca_data_root).build_handoff(
                AtlasVerificationRecommendationHandoffRequest(
                    workspace_id=req.workspace_id,
                    project_path=req.project_path,
                    pool_id=pool.pool_id,
                    goal=root_goal,
                    plan_pool=_model_dump(pool),
                    verification_recommendation=verification_recommendation_payload,
                )
            ).model_dump()
            compact = {
                "status": handoff.get("status", "missing"), "confidence": handoff.get("confidence", "unknown"),
                "approval_summary": handoff.get("approval_summary", ""),
                "impacted_files": list(handoff.get("impacted_files", []))[:20],
                "related_tests": list(handoff.get("related_tests", []))[:15],
                "recommended_commands": list(handoff.get("recommended_commands", []))[:5],
                "manual_verification_steps": list(handoff.get("manual_verification_steps", []))[:10],
                "advisory_only": True, "executed": False, "auto_verification_triggered": False,
                "auto_test_execution_triggered": False, "commands_are_suggestions_only": True,
                "manual_approval_only": True,
            }
            pool.metadata["verification_recommendation_handoff"] = compact
            for item in (pool.items or []):
                md = item.metadata if isinstance(item.metadata, dict) else {}
                im = dict(compact)
                im["item_id"] = item.item_id
                if req.enable_repo_context:
                    im.setdefault("warnings", ["item_specific_verification_recommendation_unavailable"])
                md["verification_recommendation_handoff"] = im
                item.metadata = md
        except Exception:
            pool.metadata["verification_recommendation_handoff"] = {"status": "failed", "advisory_only": True, "executed": False, "manual_approval_only": True}

    if planner_packaging_v2_payload:
        pool.metadata["planner_packaging_v2"] = {"status": planner_packaging_v2_payload.get("status", "missing"), "confidence": planner_packaging_v2_payload.get("confidence", "unknown"), "impacted_files": list(planner_packaging_v2_payload.get("impacted_files", []))[:30], "related_tests": list(planner_packaging_v2_payload.get("related_tests", []))[:20], "recommended_commands": list(planner_packaging_v2_payload.get("recommended_commands", []))[:5], "context_sections": len(list(planner_packaging_v2_payload.get("context_sections", []))), "evidence": len(list(planner_packaging_v2_payload.get("evidence", []))), "advisory_only": True, "executed": False, "auto_verification_triggered": False, "auto_test_execution_triggered": False}
        pool.metadata["planner_context_text_v2"] = str(planner_packaging_v2_payload.get("planner_context_text", ""))[:6000]

    if plan_item_impact_map_payload:
        pool.metadata["plan_item_impact_map"] = {"status": plan_item_impact_map_payload.get("status", "missing"), "item_count": plan_item_impact_map_payload.get("item_count", 0), "confidence": plan_item_impact_map_payload.get("confidence", "unknown"), "warnings": list(plan_item_impact_map_payload.get("warnings", []))[:10], "executed": False, "advisory_only": True, "auto_verification_triggered": False, "auto_test_execution_triggered": False}
        item_map = {str(i.get("item_id") or ""): i for i in list(plan_item_impact_map_payload.get("impacts", []))}
        for item in (pool.items or []):
            md = item.metadata if isinstance(item.metadata, dict) else {}
            impact = item_map.get(str(item.item_id), {})
            md["impact_map"] = {"impacted_files": list(impact.get("impacted_files", []))[:10], "related_tests": list(impact.get("related_tests", []))[:10], "recommended_commands": list(impact.get("recommended_commands", []))[:5], "manual_verification_steps": list(impact.get("manual_verification_steps", []))[:5], "ci_selection_hints": list(impact.get("ci_selection_hints", []))[:5], "confidence": impact.get("confidence", "unknown"), "advisory_only": True, "executed": False, "auto_verification_triggered": False, "auto_test_execution_triggered": False}
            item.metadata = md

    if verification_plan_payload:
        pool.metadata["verification_plan"] = {
            "status": verification_plan_payload.get("status", "missing"),
            "related_tests": list(verification_plan_payload.get("related_tests", []))[:10],
            "recommended_commands": list(verification_plan_payload.get("recommended_commands", []))[:5],
            "manual_steps": list(verification_plan_payload.get("manual_verification_steps", []))[:5],
            "ci_hints": list(verification_plan_payload.get("ci_selection_hints", []))[:5],
            "executed": False, "advisory_only": True,
            "auto_verification_triggered": False, "auto_test_execution_triggered": False,
        }

    if impacted_test_recommendation_payload:
        pool.metadata["impacted_test_recommendation"] = {
            "status": impacted_test_recommendation_payload.get("status", "missing"),
            "related_tests": list(impacted_test_recommendation_payload.get("related_tests", []))[:30],
            "recommended_commands": list(impacted_test_recommendation_payload.get("recommended_commands", []))[:5],
            "confidence": impacted_test_recommendation_payload.get("confidence", "unknown"),
            "executed": False,
        }
        for item in (pool.items or []):
            md = item.metadata if isinstance(item.metadata, dict) else {}
            md["repo_context"] = {
                "impacted_files": list(repo_context_package_payload.get("impacted_files", []))[:10],
                "related_tests": list(impacted_test_recommendation_payload.get("related_tests", []))[:10],
                "confidence": repo_context_package_payload.get("confidence", "unknown"),
            }
            md["recommended_tests"] = list(impacted_test_recommendation_payload.get("related_tests", []))[:10]
            md["recommended_test_commands"] = list(impacted_test_recommendation_payload.get("recommended_commands", []))[:5]
            md["verification_hints"] = {"related_tests": list(verification_plan_payload.get("related_tests", []))[:10], "recommended_commands": list(verification_plan_payload.get("recommended_commands", []))[:5], "manual_steps": list(verification_plan_payload.get("manual_verification_steps", []))[:5], "ci_hints": list(verification_plan_payload.get("ci_selection_hints", []))[:5], "executed": False, "advisory_only": True, "auto_verification_triggered": False, "auto_test_execution_triggered": False}
            item.metadata = md
    # ── Critique gate (PR-8b): block patch generation or record full_auto continuation ──
    # Evaluates the planner's POST-revision adversarial critique. full_auto + non-safety high
    # findings proceed as a recorded policy continuation; supervised/lower presets or any
    # safety-sensitive high finding pause at the approval gate with plan_revision_required.
    # Resolve human-in-the-loop features (request override > server-side default > built-in).
    _features = _resolve_automation_features(
        request_features=dict(req.automation_features or {}), ca_data_root=ca_data_root
    )
    pool.metadata["automation_features"] = _features
    # ── Pre-approval plan-depth gate (WS6-1): reject shallow plans (no implementation items,
    # missing target files, one-line step descriptions) before approval/apply. Blocking only when
    # quality_gate_enforcement="block"; otherwise surfaced as warnings. ──
    _depth = evaluate_plan_depth(pool)
    pool.metadata["plan_depth_gate"] = _depth
    _enforce_quality = _features.get("quality_gate_enforcement") == "block"
    if not _depth["ok"]:
        for _r in _depth["warnings"]:
            if _r not in pool.warnings:
                pool.warnings.append(_r)
        if _enforce_quality:
            pool.metadata["plan_revision_required"] = True
            pool.status = "approval_required"
    quality_gate = apply_plan_quality_gate(
        plan,
        automation_level=req.automation_level,
        preset_id=str(req.metadata.get("preset_id") or ""),
        critical_handling=_features["critical_handling"],
    )
    pool.metadata["critique_gate"] = quality_gate["critique_gate"]
    if quality_gate.get("critical_event"):
        pool.metadata["critical_event"] = quality_gate["critical_event"]
        pool.metadata["critical_event_status"] = "waiting_for_critical_decision"
    if quality_gate["plan_revision_required"]:
        pool.metadata["plan_revision_required"] = True
    if quality_gate["clarification"]:
        pool.metadata["critique_clarification"] = quality_gate["clarification"]
    # ── Structured clarification options (PR-9d): produce option/merit/risk/recommendation items
    # whenever the gate needs a human (plan_revision_required OR an "ask" pause) so the UI can
    # present choices. When clarification_mode=="pause" mark the pool clarification_required. ──
    if quality_gate["plan_revision_required"] or quality_gate["require_approval"]:
        _plan_text = str(plan.get("summary") or plan.get("task_summary") or root_goal)
        _ambiguities = AtlasClarificationGateService().detect_ambiguities(_plan_text)
        _blocking = list((quality_gate.get("critique_gate") or {}).get("blocking_findings") or [])
        _options = [
            {
                "option_id": f"revise_{i}",
                "label": f.get("angle") or f.get("category") or f"Finding {i+1}",
                "description": str(f.get("detail") or f.get("summary") or f),
                "merit": "Addresses a high-severity critique finding before patching.",
                "risk": "Requires plan revision; may delay implementation.",
                "recommendation": "revise" if str(f.get("severity") or "") == "critical" else "review",
            }
            for i, f in enumerate(_blocking)
        ]
        _clarification_eval = AtlasClarificationGateService().evaluate(_ambiguities, options=_options)
        pool.metadata["critique_clarification_options"] = {
            "ambiguity_signals": _ambiguities,
            "options": _options,
            "gate_evaluation": _clarification_eval,
        }
        # When clarification_mode is "pause" and we have something to ask about (options or
        # detected ambiguity), flag the pool so the UI surfaces a Claude-style options question
        # that survives reload. "auto" proceeds with the safe-default assumption (legacy).
        if _features.get("clarification_mode") == "pause" and (_options or _ambiguities):
            pool.metadata["clarification_questions"] = AtlasClarificationService().build_question_queue(
                ambiguity_signals=_ambiguities,
                options=_options,
            )
            pool.metadata["current_question_index"] = 1 if pool.metadata["clarification_questions"] else 0
            pool.metadata["pending_question_count"] = len(pool.metadata["clarification_questions"])
            pool.metadata["answered_question_count"] = 0
            pool.metadata["clarification_required"] = True
            pool.status = "needs_scope_confirmation"
    _direct_clarification_text = str(plan.get("summary") or plan.get("task_summary") or root_goal)
    _direct_ambiguities = AtlasClarificationGateService().detect_ambiguities(_direct_clarification_text)
    if _direct_ambiguities and not pool.metadata.get("clarification_questions"):
        critical_ambiguity = any(
            AtlasClarificationReplanningService.critical_ambiguity_requires_user(signal)
            for signal in _direct_ambiguities
        ) or AtlasClarificationReplanningService.critical_ambiguity_requires_user(_direct_clarification_text)
        if _features.get("clarification_mode") == "pause" or critical_ambiguity:
            pool.metadata["clarification_questions"] = AtlasClarificationService().build_question_queue(
                ambiguity_signals=_direct_ambiguities,
                options=[],
            )
            pool.metadata["current_question_index"] = 1
            pool.metadata["pending_question_count"] = len(pool.metadata["clarification_questions"])
            pool.metadata["answered_question_count"] = 0
            pool.metadata["clarification_required"] = True
            pool.metadata["critique_clarification_options"] = {
                "ambiguity_signals": _direct_ambiguities,
                "options": [],
                "gate_evaluation": {"clarification_required": True, "gate_status": "clarification_required"},
            }
            pool.status = "needs_scope_confirmation"
        else:
            _safe_default_answer = "Proceed with the narrowest low-risk interpretation and record the assumption."
            _safe_default_questions = AtlasClarificationService().build_question_queue(
                ambiguity_signals=_direct_ambiguities,
                options=[],
            )
            _safe_default_progress = {
                "questions": _safe_default_questions,
                "answers": [],
                "current_question_index": 0,
                "pending_count": len(_safe_default_questions),
                "answered_count": 0,
                "latest_decision": {},
            }
            for _safe_default_question in _safe_default_questions:
                _safe_default_progress = AtlasClarificationService().apply_answer_to_question_queue(
                    questions=_safe_default_progress["questions"],
                    answers=_safe_default_progress["answers"],
                    question_id=str(_safe_default_question.get("question_id") or ""),
                    option_id="safest_recommended",
                    answer_text=_safe_default_answer,
                    note="safe default selected because clarification_mode=auto",
                )
            pool.metadata["clarification_questions"] = _safe_default_progress["questions"]
            pool.metadata["clarification_answers"] = _safe_default_progress["answers"]
            pool.metadata["current_question_index"] = _safe_default_progress["current_question_index"]
            pool.metadata["pending_question_count"] = _safe_default_progress["pending_count"]
            pool.metadata["answered_question_count"] = _safe_default_progress["answered_count"]
            pool.metadata["latest_clarification_decision"] = _safe_default_progress["latest_decision"]
            pool.metadata["clarification_decision"] = _safe_default_progress["latest_decision"]
            pool.metadata["plan_revision_required_after_clarification"] = True
            pool.metadata["gate_rerun_required_after_clarification"] = True
            pool.metadata["safe_default_assumption_after_clarification"] = {
                "assumption": _safe_default_answer,
                "ambiguity_signals": _direct_ambiguities,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            }
            pool.metadata["safe_default_clarification_mode"] = "auto"
            AtlasClarificationReplanningService().revise_after_answers(
                pool,
                preset_id=str((pool.metadata or {}).get("preset_id") or req.metadata.get("preset_id") or "guarded_low_risk"),
                automation_level=str(req.automation_level or getattr(pool, "automation_level", "") or ""),
                critical_handling=str(_features.get("critical_handling") or "ask"),
            )
    for _w in quality_gate["warnings"]:
        if _w not in pool.warnings:
            pool.warnings.append(_w)
    if quality_gate["require_approval"] and pool.status != "needs_scope_confirmation":
        pool.status = "waiting_for_critical_decision" if quality_gate.get("critical_event") else "approval_required"

    # ── Requirement trace + repair intent (PR-8d): persist on pool metadata so the autopilot
    # final-status rollup can compute coverage and detect test-only repair plans. ──
    pool.metadata["requirement_trace"] = AtlasRequirementTracer().extract_requirements(root_goal)
    _repair_intent = (req.metadata or {}).get("repair_intent") or classify_repair_intent(
        req.input or "", previous_changed_files=changed_files_for_context
    )
    pool.metadata["repair_intent"] = _repair_intent

    # ── Capability preferences (PR-8e): persist USER PREFERENCE METADATA server-side.
    # These are preferences only — backend/runtime policy stays authoritative. Storing a
    # checked preference NEVER enables shell/run_command/arbitrary browser automation. ──
    _incoming_caps = dict(req.capability_preferences or {})
    if not _incoming_caps and isinstance(req.metadata, dict):
        _incoming_caps = dict(req.metadata.get("capability_preferences") or {})
    _caps = _apply_capability_preferences(
        _default_capability_preferences(), _normalize_capability_preferences(_incoming_caps)
    )
    pool.metadata["feature_preferences"] = _caps
    pool.metadata["feature_summary"] = _build_capability_summary(_caps)

    pool.metadata.update(
        {
            "api_created": True,
            "use_nexus_requested": bool(req.use_nexus),
            "planner_status": planner_status,
            "used_fallback": used_fallback,
            "fallback_reason": fallback_reason,
            "strategic_plan": _build_strategic_plan_summary(
                requirement=requirement, plan=plan, review_result=review_result, pool=pool,
            ),
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
        # PR-9d: surface quality signals and preference summary in the orchestration summary
        # so the UI and API consumers can act on them without digging into pool.metadata.
        "feature_summary": pool.metadata.get("feature_summary") or {},
        "critique_gate": pool.metadata.get("critique_gate") or {},
        "plan_revision_required": bool(pool.metadata.get("plan_revision_required")),
        "critique_clarification_options": pool.metadata.get("critique_clarification_options") or {},
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
    _, storage, journal = _atlas_components(request)
    _sync_pool_from_workspace_snapshot(storage, journal, pool_id)
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
    ca_data_root, storage, journal = _atlas_components(request, workspace_id=req.workspace_id)
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
    ca_data_root, storage, journal = _atlas_components(request, workspace_id=req.workspace_id)
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
    ca_data_root, storage, journal = _atlas_components(request, workspace_id=req.workspace_id)
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
    ca_data_root, storage, journal = _atlas_components(request, workspace_id=req.workspace_id)
    _sync_pool_from_workspace_snapshot(storage, journal, req.pool_id)
    try:
        pool = storage.load_pool(req.pool_id)
    except FileNotFoundError:
        return AtlasPatchProposalResult(pool_id=req.pool_id, item_id=req.item_id, run_id=req.run_id, status="blocked", warnings=["pool_not_found"])
    clarification_blocks = _clarification_execution_block_reasons(pool)
    if clarification_blocks:
        return AtlasPatchProposalResult(
            pool_id=req.pool_id,
            item_id=req.item_id,
            run_id=req.run_id,
            status="blocked",
            warnings=clarification_blocks,
            metadata={"clarification_execution_blocked": True, "blocked_reasons": clarification_blocks},
            plan_pool=pool.model_dump(),
        )
    service = AtlasPatchProposalService(journal=journal, storage=storage, llm_json_fn=_resolve_atlas_llm_json_fn(request))
    result = service.propose_for_item(req)
    try:
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


@router.post("/patch-proposals/decide", response_model=AtlasPatchProposalApprovalResult)
def decide_patch_proposal(req: AtlasPatchProposalApprovalRequest, request: Request) -> AtlasPatchProposalApprovalResult:
    if ".." in req.pool_id or ".." in req.item_id:
        raise HTTPException(status_code=400, detail="invalid identifier")
    ca_data_root, storage, journal = _atlas_components(request, workspace_id=req.workspace_id)
    _sync_pool_from_workspace_snapshot(storage, journal, req.pool_id)
    try:
        pool = storage.load_pool(req.pool_id)
    except FileNotFoundError:
        return AtlasPatchProposalApprovalResult(pool_id=req.pool_id, item_id=req.item_id, proposal_id=req.proposal_id, status="blocked", warnings=["pool_not_found"])
    clarification_blocks = _clarification_execution_block_reasons(pool)
    approval_decisions = {"approve", "approved", "accept", "accepted", "apply", "run", "execute"}
    if clarification_blocks and str(req.decision or "").strip().lower() in approval_decisions:
        return AtlasPatchProposalApprovalResult(
            pool_id=req.pool_id,
            item_id=req.item_id,
            proposal_id=req.proposal_id,
            status="blocked",
            warnings=clarification_blocks,
            metadata={"clarification_execution_blocked": True, "blocked_reasons": clarification_blocks},
            plan_pool=pool.model_dump(),
        )
    service = AtlasPatchProposalApprovalService(journal=journal, storage=storage)
    try:
        result = service.decide(req)
    except FileNotFoundError:
        result = AtlasPatchProposalApprovalResult(pool_id=req.pool_id, item_id=req.item_id, proposal_id=req.proposal_id, status="blocked", warnings=["pool_not_found"])
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
        result.warnings.append("patch_proposal_approval_enrichment_failed")
        result.warnings.append(str(exc) or exc.__class__.__name__)
    return result



@router.post("/patch-proposals/planitem-draft", response_model=AtlasPatchProposalPlanItemDraftResult)
def create_patch_proposal_planitem_draft(req: AtlasPatchProposalPlanItemDraftRequest, request: Request) -> AtlasPatchProposalPlanItemDraftResult:
    if ".." in req.pool_id or ".." in req.item_id:
        raise HTTPException(status_code=400, detail="invalid identifier")
    ca_data_root, storage, journal = _atlas_components(request, workspace_id=req.workspace_id)
    _sync_pool_from_workspace_snapshot(storage, journal, req.pool_id)
    service = AtlasPatchProposalPlanItemDraftService(journal=journal, storage=storage)
    try:
        result = service.create_draft(req)
    except FileNotFoundError:
        result = AtlasPatchProposalPlanItemDraftResult(pool_id=req.pool_id, item_id=req.item_id, proposal_id=req.proposal_id, status="blocked", warnings=["pool_not_found"])
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
        result.warnings.append("patch_proposal_planitem_draft_enrichment_failed")
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
    ca_data_root, storage, journal = _atlas_components(request, workspace_id=req.workspace_id)
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


@router.post("/critical-decisions/decide", response_model=AtlasApprovalDecisionResponse)
def decide_critical_event(req: AtlasApprovalDecisionRequest, request: Request) -> AtlasApprovalDecisionResponse:
    ca_data_root, storage, journal = _atlas_components(request, workspace_id=req.workspace_id)
    try:
        pool = storage.load_pool(req.pool_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="plan pool not found") from exc
    item = pool.get_item(req.item_id)
    pool_critical_event = dict((pool.metadata or {}).get("critical_event") or {})
    is_pool_scope = (
        req.item_id in {"", POOL_CRITICAL_DECISION_ITEM_ID}
        or (item is None and pool_critical_event.get("critical_event"))
    )
    if is_pool_scope:
        critical_event = dict(pool_critical_event or (req.metadata or {}).get("critical_event") or {})
        if not critical_event.get("critical_event") and pool.status != "waiting_for_critical_decision":
            raise HTTPException(status_code=400, detail="critical_decision_requires_critical_event")
        decision_map = {
            "approve": "approved",
            "approved": "approved",
            "reject_ng_safer_replan": "rejected",
            "rejected": "rejected",
            "cancel": "cancelled",
            "cancelled": "cancelled",
            "edit_scope": "needs_revision",
            "needs_revision": "needs_revision",
        }
        mapped_decision = decision_map.get(str(req.decision or "").strip().lower())
        if mapped_decision is None:
            raise HTTPException(status_code=400, detail="invalid_critical_decision")
        service = AtlasApprovalService(journal)
        metadata = {
            **dict(req.metadata or {}),
            "critical_decision_path": True,
            "critical_decision_scope": "pool",
            "critical_decision": str(req.decision or ""),
            "critical_event": critical_event,
        }
        try:
            approval_record = service.decide_pool_critical(
                pool,
                run_id=req.run_id,
                decision=mapped_decision,
                reason=req.reason,
                approver=req.approver,
                metadata=metadata,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        storage.save_pool(pool)
        journal.save_plan_pool(pool)
        recovery = AtlasRecoveryService(journal).recover_pool(pool.pool_id).model_dump()
        orchestration = AtlasOrchestrationSummaryBuilder().build_from_pool_and_state(pool, None, recovery=recovery).model_dump()
        continuation = AtlasContinuationService(journal).build_pool_summary(pool.pool_id, req.run_id).continuation_prompt
        journal.write_checkpoint(pool=pool, next_action=_checkpoint_next_action(pool.status))
        return AtlasApprovalDecisionResponse(pool_id=req.pool_id, item_id=POOL_CRITICAL_DECISION_ITEM_ID, decision=str(req.decision or mapped_decision), status=pool.status, approval_record=approval_record, plan_pool=_model_dump(pool), recovery_summary=recovery, orchestration_summary=orchestration, continuation_prompt=continuation)
    if item is None:
        raise HTTPException(status_code=404, detail="item not found")
    critical_event = dict((item.metadata or {}).get("critical_event") or (req.metadata or {}).get("critical_event") or {})
    if not critical_event.get("critical_event") and item.status != "waiting_for_critical_decision":
        raise HTTPException(status_code=400, detail="critical_decision_requires_critical_event")
    decision_map = {
        "approve": "approved",
        "approved": "approved",
        "reject_ng_safer_replan": "rejected",
        "rejected": "rejected",
        "cancel": "cancelled",
        "cancelled": "cancelled",
        "edit_scope": "needs_revision",
        "needs_revision": "needs_revision",
    }
    mapped_decision = decision_map.get(str(req.decision or "").strip().lower())
    if mapped_decision is None:
        raise HTTPException(status_code=400, detail="invalid_critical_decision")
    service = AtlasApprovalService(journal)
    metadata = {
        **dict(req.metadata or {}),
        "critical_decision_path": True,
        "critical_decision": str(req.decision or ""),
        "critical_event": critical_event,
    }
    try:
        approval_record = service.decide(pool, item_id=req.item_id, run_id=req.run_id, decision=mapped_decision, reason=req.reason, approver=req.approver, metadata=metadata)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    storage.save_pool(pool)
    journal.save_plan_pool(pool)
    recovery = AtlasRecoveryService(journal).recover_pool(pool.pool_id).model_dump()
    orchestration = AtlasOrchestrationSummaryBuilder().build_from_pool_and_state(pool, None, recovery=recovery).model_dump()
    continuation = AtlasContinuationService(journal).build_pool_summary(pool.pool_id, req.run_id).continuation_prompt
    journal.write_checkpoint(pool=pool, next_action=_checkpoint_next_action(pool.status))
    return AtlasApprovalDecisionResponse(pool_id=req.pool_id, item_id=req.item_id, decision=str(req.decision or mapped_decision), status=pool.status, approval_record=approval_record, plan_pool=_model_dump(pool), recovery_summary=recovery, orchestration_summary=orchestration, continuation_prompt=continuation)


class AtlasPlanCancelRequest(BaseModel):
    workspace_id: str = "default"
    reason: str = ""


_CANCELLABLE_ITEM_STATUSES = {"queued", "ready", "pending", "approval_required", "needs_revision", "paused", "waiting", "dependency_waiting"}


@router.post("/plan-pools/{pool_id}/cancel")
def cancel_plan_pool(pool_id: str, req: AtlasPlanCancelRequest, request: Request) -> dict:
    """Cancel a plan: mark the pool cancelled and stop any not-yet-terminal items. This is the
    plan-level counterpart to the per-item approval decisions (approve/reject/needs_revision)."""
    _, storage, journal = _atlas_components(request, workspace_id=req.workspace_id)
    try:
        pool = storage.load_pool(pool_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="plan pool not found") from exc
    cancelled_ids: list[str] = []
    for item in (pool.items or []):
        if str(getattr(item, "status", "")).lower() in _CANCELLABLE_ITEM_STATUSES:
            item.status = "cancelled"
            cancelled_ids.append(item.item_id)
    pool.status = "cancelled"
    pool.metadata["cancelled"] = {"reason": req.reason, "cancelled_item_ids": cancelled_ids}
    pool.metadata.pop("clarification_required", None)
    storage.save_pool(pool)
    journal.save_plan_pool(pool)
    journal.write_checkpoint(pool=pool, next_action=_checkpoint_next_action(pool.status))
    return {"pool_id": pool_id, "status": pool.status, "cancelled_item_ids": cancelled_ids, "plan_pool": _model_dump(pool)}


class AtlasPlanClarifyRequest(BaseModel):
    workspace_id: str = "default"
    question_id: str = ""
    option_id: str = ""
    answer_text: str = ""
    note: str = ""


@router.post("/plan-pools/{pool_id}/clarify")
def clarify_plan_pool(pool_id: str, req: AtlasPlanClarifyRequest, request: Request) -> dict:
    """Record one queued clarification answer while preserving remaining questions."""
    _, storage, journal = _atlas_components(request, workspace_id=req.workspace_id)
    try:
        pool = storage.load_pool(pool_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="plan pool not found") from exc
    clarification = (pool.metadata or {}).get("critique_clarification_options") or {}
    questions = list((pool.metadata or {}).get("clarification_questions") or [])
    if not questions:
        questions = AtlasClarificationService().build_question_queue(
            ambiguity_signals=list(clarification.get("ambiguity_signals") or []),
            options=list(clarification.get("options") or []),
        )
    progress = AtlasClarificationService().apply_answer_to_question_queue(
        questions=questions,
        answers=list((pool.metadata or {}).get("clarification_answers") or []),
        question_id=req.question_id,
        option_id=req.option_id,
        answer_text=req.answer_text,
        note=req.note,
    )
    pool.metadata["clarification_questions"] = progress["questions"]
    pool.metadata["clarification_answers"] = progress["answers"]
    pool.metadata["current_question_index"] = progress["current_question_index"]
    pool.metadata["pending_question_count"] = progress["pending_count"]
    pool.metadata["answered_question_count"] = progress["answered_count"]
    pool.metadata["latest_clarification_decision"] = progress["latest_decision"]
    pool.metadata["clarification_decision"] = progress["latest_decision"]
    pool.metadata["plan_revision_required_after_clarification"] = True
    pool.metadata["gate_rerun_required_after_clarification"] = True
    replan_result: dict[str, Any] = {}
    if progress["pending_count"]:
        pool.metadata["clarification_required"] = True
    else:
        pool.metadata.pop("clarification_required", None)
        replan_result = AtlasClarificationReplanningService().revise_after_answers(
            pool,
            preset_id=str((pool.metadata or {}).get("preset_id") or "guarded_low_risk"),
            automation_level=str(getattr(pool, "automation_level", "") or ""),
            critical_handling=str(((pool.metadata or {}).get("automation_features") or {}).get("critical_handling") or "ask"),
        )
    if pool.status == "ready" and not replan_result:
        pool.status = "approval_required"
    storage.save_pool(pool)
    journal.save_plan_pool(pool)
    blocked_reasons = _clarification_execution_block_reasons(pool)
    return {
        "pool_id": pool_id,
        "status": pool.status,
        "clarification_decision": pool.metadata["clarification_decision"],
        "clarification_questions": pool.metadata["clarification_questions"],
        "pending_question_count": pool.metadata["pending_question_count"],
        "answered_question_count": pool.metadata["answered_question_count"],
        "clarification_replanning": replan_result,
        "revised_plan_snapshot": pool.metadata.get("revised_plan_snapshot"),
        "plan_revision_diff": pool.metadata.get("plan_revision_diff"),
        "gate_rerun_summary": pool.metadata.get("gate_rerun_summary"),
        "revised_plan_summary": pool.metadata.get("revised_plan_summary"),
        "changed_scope_summary": pool.metadata.get("changed_scope_summary"),
        "next_required_user_action": pool.metadata.get("next_required_user_action"),
        "blocked_reasons": blocked_reasons,
        "plan_pool": _model_dump(pool),
    }




@router.post("/change-snapshots/restore", response_model=AtlasChangeSnapshotRestoreResult)
def restore_change_snapshot(req: AtlasChangeSnapshotRestoreRequest, request: Request) -> AtlasChangeSnapshotRestoreResult:
    if ".." in req.pool_id or (req.item_id and ".." in req.item_id):
        raise HTTPException(status_code=400, detail="invalid id")
    ca_data_root, storage, journal = _atlas_components(request, workspace_id=req.workspace_id)
    _validate_restore_manifest_path(Path(req.manifest_path), ca_data_root)
    workspace_root = _resolve_pool_workspace_root(storage=storage, ca_data_root=ca_data_root, workspace_id=req.workspace_id, pool_id=req.pool_id)
    service = AtlasChangeSnapshotRestoreService(journal=journal, workspace_root=workspace_root)
    return service.restore(req)
@router.post("/safe-apply/execute", response_model=AtlasSafeApplyExecutionResult)
def execute_safe_apply(req: AtlasSafeApplyExecutionRequest, request: Request) -> AtlasSafeApplyExecutionResult:
    if ".." in req.pool_id or ".." in req.item_id:
        raise HTTPException(status_code=400, detail="invalid id")
    ca_data_root, storage, journal = _atlas_components(request, workspace_id=req.workspace_id)
    _sync_pool_from_workspace_snapshot(storage, journal, req.pool_id)
    try:
        pool = storage.load_pool(req.pool_id)
    except FileNotFoundError:
        return AtlasSafeApplyExecutionResult(pool_id=req.pool_id, item_id=req.item_id, run_id=req.run_id, status="blocked", warnings=["pool_not_found"])
    clarification_blocks = _clarification_execution_block_reasons(pool)
    if clarification_blocks:
        return AtlasSafeApplyExecutionResult(
            pool_id=req.pool_id,
            item_id=req.item_id,
            run_id=req.run_id,
            status="blocked",
            warnings=clarification_blocks,
            metadata={"clarification_execution_blocked": True, "blocked_reasons": clarification_blocks},
            plan_pool=_model_dump(pool),
            safe_apply_result={"decision": "block", "status": "blocked", "reasons": clarification_blocks},
        )
    adapter_obj = getattr(request.app.state, 'atlas_safe_apply_adapter', None)
    safe_apply_adapter = adapter_obj() if callable(adapter_obj) else adapter_obj
    if safe_apply_adapter is None:
        implementation_executor = getattr(request.app.state, 'atlas_implementation_executor', None)
        safe_apply_adapter = AtlasSafeApplyAdapter(implementation_executor=implementation_executor)
    workspace_root = _resolve_pool_workspace_root(storage=storage, ca_data_root=ca_data_root, workspace_id=req.workspace_id, pool_id=req.pool_id)
    if getattr(safe_apply_adapter, "implementation_executor", None) is not None:
        impl = safe_apply_adapter.implementation_executor
        if hasattr(impl, "workspace_root"):
            try:
                safe_apply_adapter.implementation_executor = impl.__class__(workspace_root=workspace_root)
            except Exception:
                impl.workspace_root = workspace_root
    service = AtlasSafeApplyExecutionService(journal=journal, storage=storage, safe_apply_adapter=safe_apply_adapter, workspace_root=workspace_root)
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


@router.get("/auto-policy/presets")
def atlas_auto_policy_presets_route() -> dict:
    presets = atlas_auto_policy_presets()
    return {"presets": [preset.model_dump() for preset in presets.values()]}


@router.post("/automation/decide", response_model=AtlasAutomationDecisionResponse)
def atlas_automation_decide(request_body: AtlasAutomationDecisionRequest, request: Request) -> AtlasAutomationDecisionResponse:
    _, storage, journal = _atlas_components(request, workspace_id=request_body.workspace_id)
    pool = storage.load_pool(request_body.pool_id)
    item = pool.get_item(request_body.item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="item_not_found")
    presets = atlas_auto_policy_presets()
    preset = presets.get(request_body.preset_id)
    if preset is None:
        raise HTTPException(status_code=404, detail="preset_not_found")
    gate = AtlasAutomationGateService()
    decision = gate.decide_pre_safe_apply(pool, item, preset)
    summary = AtlasOrchestrationSummaryBuilder().build_from_pool_and_state(pool, None)
    continuation = AtlasContinuationService(journal).build_pool_summary(request_body.pool_id, run_id="")
    return AtlasAutomationDecisionResponse(
        decision=decision,
        plan_pool=_model_dump(pool),
        orchestration_summary=_model_dump(summary),
        continuation_prompt=continuation.continuation_prompt,
    )


@router.post("/automation/safe-apply-one", response_model=AtlasAutoSafeApplyResult)
def atlas_automation_safe_apply_one(request_body: AtlasAutoSafeApplyRequest, request: Request) -> AtlasAutoSafeApplyResult:
    _, storage, journal = _atlas_components(request, workspace_id=request_body.workspace_id)
    _sync_pool_from_workspace_snapshot(storage, journal, request_body.pool_id)
    try:
        pool = storage.load_pool(request_body.pool_id)
    except FileNotFoundError:
        return AtlasAutoSafeApplyResult(pool_id=request_body.pool_id, item_id=request_body.item_id, run_id=request_body.run_id, preset_id=request_body.preset_id, status="blocked", warnings=["pool_not_found"])
    clarification_blocks = _clarification_execution_block_reasons(pool)
    if clarification_blocks:
        return AtlasAutoSafeApplyResult(
            pool_id=request_body.pool_id,
            item_id=request_body.item_id,
            run_id=request_body.run_id,
            preset_id=request_body.preset_id,
            status="blocked",
            warnings=clarification_blocks,
            metadata={"clarification_execution_blocked": True, "blocked_reasons": clarification_blocks},
            plan_pool=_model_dump(pool),
        )
    workspace_root = _resolve_pool_workspace_root(storage=storage, ca_data_root=Path(getattr(request.app.state, 'atlas_ca_data_dir', './ca_data')), workspace_id=request_body.workspace_id, pool_id=request_body.pool_id)
    adapter_obj = getattr(request.app.state, 'atlas_safe_apply_adapter', None)
    safe_apply_adapter = adapter_obj() if callable(adapter_obj) else adapter_obj
    if safe_apply_adapter is None:
        implementation_executor = getattr(request.app.state, 'atlas_implementation_executor', None)
        safe_apply_adapter = AtlasSafeApplyAdapter(implementation_executor=implementation_executor)
    if getattr(safe_apply_adapter, "implementation_executor", None) is not None:
        impl = safe_apply_adapter.implementation_executor
        if hasattr(impl, "workspace_root"):
            try:
                safe_apply_adapter.implementation_executor = impl.__class__(workspace_root=workspace_root)
            except Exception:
                impl.workspace_root = workspace_root
    auto_service = AtlasAutoSafeApplyService(automation_gate=AtlasAutomationGateService(), safe_apply_service=AtlasSafeApplyExecutionService(journal=journal, storage=storage, safe_apply_adapter=safe_apply_adapter, workspace_root=workspace_root), journal=journal, storage=storage)
    result = auto_service.execute_one(request_body)
    refreshed_pool = storage.load_pool(request_body.pool_id)
    summary = AtlasOrchestrationSummaryBuilder().build_from_pool_and_state(refreshed_pool, None)
    continuation = AtlasContinuationService(journal).build_pool_summary(request_body.pool_id, request_body.run_id)
    result.plan_pool = _model_dump(refreshed_pool)
    result.orchestration_summary = _model_dump(summary)
    result.continuation_prompt = continuation.continuation_prompt
    return result


@router.get("/workflow-state/read-only")
def atlas_workflow_state_read_only() -> dict[str, Any]:
    return build_read_only_workflow_state(
        goal="Atlas Next read-only supervision shell",
        project_path="Backend-provided project path when safe workflow_state is available",
        phase="read_only_preview",
        status="Stable backend read-only workflow_state contract available (non-executable metadata).",
        primary_cta_label="Read-only preview (metadata only)",
        available_actions=[{"id": "inspect_workflow_state", "label": "Inspect workflow state payload", "kind": "read_only"}],
        artifacts={"rollup": True, "dry_run": True, "snapshot": True, "allowlist": True, "risk": True},
        warnings=[
            "Route is read-only metadata only.",
            "Real-data workflow metadata is safe-if-available and may be unknown when backend state is unavailable.",
        ],
        workflow_metadata={
            "latest_pool_id": None,
            "latest_run_id": None,
            "latest_plan_id": None,
            "latest_requirement_id": None,
            "current_phase": "read_only_preview",
            "latest_status": "unknown",
            "continuation_state": "unknown",
            "recovery_state": "unknown",
            "plan_pool_available": False,
            "active_plan_available": False,
            "last_report_available": False,
            "last_error_summary": None,
            "last_updated_at": None,
            "data_freshness": "unknown",
            "source_detail": "safe_read_only_backend_metadata",
            "workflow_snapshot_available": False,
        },
    )


@router.get("/level1/readiness")
def atlas_level1_readiness_diagnostics() -> dict[str, object]:
    """GET-only metadata diagnostics for the disabled Level-1 backend skeleton."""
    return Level1GuardedExecutionSkeleton.build_disabled_level1_contract()


@router.post("/level1/dry-run-only")
def atlas_level1_dry_run_only_endpoint(req: Level1DryRunOnlyRequest) -> dict[str, Any]:
    """Dry-run-only Level-1 skeleton; returns metadata without side effects."""
    return build_level1_dry_run_only_result(req.model_dump())


@router.post("/level1/dry-run-result-artifact")
def atlas_level1_dry_run_result_artifact_endpoint(
    req: Level1DryRunResultArtifactCaptureRequest,
    request: Request,
) -> dict[str, Any]:
    """Capture dry-run-only result metadata without executing or mutating project files."""
    return capture_level1_dry_run_result_artifact(
        data_root=resolve_atlas_ca_data_root(request),
        dry_run_result={**dict(req.dry_run_result), "workspace_id": req.workspace_id},
    )


@router.get("/verification/allowlist")
def atlas_verification_allowlist_route() -> dict:
    commands = atlas_verification_allowlist()
    return {"commands": [c.model_dump() for c in commands.values()]}


@router.post("/automation/verify-one", response_model=AtlasAutoVerificationResult)
def atlas_automation_verify_one(request_body: AtlasAutoVerificationRequest, request: Request) -> AtlasAutoVerificationResult:
    _, storage, journal = _atlas_components(request, workspace_id=request_body.workspace_id)
    _sync_pool_from_workspace_snapshot(storage, journal, request_body.pool_id)
    runner = _resolve_atlas_test_command_runner(request)
    service = AtlasAutoVerificationService(journal=journal, storage=storage, command_runner=runner)
    result = service.run_after_auto_safe_apply(request_body)
    try:
        refreshed_pool = storage.load_pool(request_body.pool_id)
        summary = AtlasOrchestrationSummaryBuilder().build_from_pool_and_state(refreshed_pool, None)
        continuation = AtlasContinuationService(journal).build_pool_summary(request_body.pool_id, request_body.run_id)
        result.plan_pool = _model_dump(refreshed_pool)
        result.orchestration_summary = _model_dump(summary)
        result.continuation_prompt = continuation.continuation_prompt
    except Exception:
        pass
    return result


@router.post("/automation/safe-apply-one-and-verify", response_model=AtlasAutoSafeApplyAndVerifyResult)
def atlas_automation_safe_apply_one_and_verify(request_body: AtlasAutoSafeApplyAndVerifyRequest, request: Request) -> AtlasAutoSafeApplyAndVerifyResult:
    safe = atlas_automation_safe_apply_one(AtlasAutoSafeApplyRequest(pool_id=request_body.pool_id, item_id=request_body.item_id, preset_id=request_body.preset_id, workspace_id=request_body.workspace_id, run_id=request_body.run_id, metadata=dict(request_body.metadata or {})), request)
    verify = AtlasAutoVerificationResult(pool_id=request_body.pool_id, item_id=request_body.item_id, run_id=request_body.run_id, preset_id=request_body.preset_id, status="skipped", warnings=["safe_apply_not_applied"])
    if safe.status == "applied":
        verify = atlas_automation_verify_one(AtlasAutoVerificationRequest(pool_id=request_body.pool_id, item_id=request_body.item_id, preset_id=request_body.preset_id, workspace_id=request_body.workspace_id, run_id=request_body.run_id, command_id=request_body.command_id, metadata=dict(request_body.metadata or {})), request)
    status = "failed"
    failure_stop_suggestion = {}
    continuation_prompt = str(getattr(verify, "continuation_prompt", "") or getattr(safe, "continuation_prompt", "") or "")
    if safe.status != "applied":
        status = "safe_apply_blocked"
    elif verify.status == "passed":
        status = "applied_and_verified"
    elif verify.status == "failed":
        status = "applied_but_verification_failed"
        _, storage, journal = _atlas_components(request, workspace_id=request_body.workspace_id)
        pool = storage.load_pool(request_body.pool_id)
        item = pool.get_item(request_body.item_id)
        if item is not None:
            suggestion = AtlasFailureStopService(journal=journal).build_for_verification_failure(pool, item, request_body.run_id, verify.model_dump())
            suggestion_payload = suggestion.model_dump()
            safe_snapshot = (safe.model_dump().get("change_snapshot") or {})
            if safe_snapshot.get("manifest_path") and not suggestion_payload.get("snapshot_manifest_path"):
                suggestion_payload["snapshot_manifest_path"] = str(safe_snapshot.get("manifest_path") or "")
                suggestion_payload["changed_files"] = list(safe_snapshot.get("changed_files") or [])
                suggestion_payload["restore_candidate"] = {"manifest_path": suggestion_payload["snapshot_manifest_path"], "changed_files": suggestion_payload["changed_files"], "snapshot_id": str(safe_snapshot.get("snapshot_id") or "")}
            failure_stop_suggestion = suggestion_payload
            continuation_prompt = (continuation_prompt + "\n\nManual next steps: Review verification failure. Inspect changed files. Restore from Change Snapshot manually if needed. Run Debug Review manually if restore is not desired.").strip()
    elif verify.status == "blocked":
        status = "verification_blocked"
    return AtlasAutoSafeApplyAndVerifyResult(auto_safe_apply_result=safe.model_dump(), auto_verification_result=verify.model_dump(), status=status, failure_stop_suggestion=failure_stop_suggestion, continuation_prompt=continuation_prompt)


@router.post("/automation/failure-suggestion", response_model=AtlasFailureStopSuggestion)
def atlas_automation_failure_suggestion(request_body: AtlasFailureSuggestionRequest, request: Request) -> AtlasFailureStopSuggestion:
    _, storage, journal = _atlas_components(request, workspace_id=request_body.workspace_id)
    _sync_pool_from_workspace_snapshot(storage, journal, request_body.pool_id)
    pool = storage.load_pool(request_body.pool_id)
    item = pool.get_item(request_body.item_id)
    if item is None:
        return AtlasFailureStopSuggestion(pool_id=request_body.pool_id, item_id=request_body.item_id, run_id=request_body.run_id, failure_phase="auto_verification", status="blocked", reason="item_not_found", errors=["item_not_found"])
    verification_result = ((item.metadata or {}).get("auto_verification") or {})
    return AtlasFailureStopService(journal=journal).build_for_verification_failure(pool, item, request_body.run_id, verification_result)
