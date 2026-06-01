from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.api.atlas_root import resolve_atlas_ca_data_root
from app.api.atlas_multi_item_autopilot import _service as _build_multi_item_service, _validate_id
from agent.atlas_autonomous_codegen_orchestrator_schema import AtlasAutonomousCodegenRequest
from agent.atlas_autonomous_codegen_orchestrator_service import AtlasAutonomousCodegenOrchestratorService
from agent.atlas_journal import AtlasJournal
from agent.atlas_patch_proposal_service import AtlasPatchProposalService
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage

router = APIRouter(prefix="/api/atlas/autonomous-codegen", tags=["atlas-autonomous-codegen"])


def _orchestrator_service(request: Request | None, workspace_id: str, pool_id: str) -> AtlasAutonomousCodegenOrchestratorService:
    root = resolve_atlas_ca_data_root(request)
    storage = AtlasPlanPoolStorage(root)
    journal = AtlasJournal(root, workspace_id=workspace_id or "default")
    # Patch generation needs the app's LLM json fn; None in tests/offline -> the proposal yields no
    # content and Phase 3 honestly skips uncontented items rather than reporting fake success.
    llm_json_fn = getattr(getattr(getattr(request, "app", None), "state", None), "atlas_llm_json_fn", None)
    patch_proposal_service = AtlasPatchProposalService(journal=journal, storage=storage, llm_json_fn=llm_json_fn)
    # Reuse the multi-item autopilot wiring verbatim so the apply phase inherits the same executor,
    # gates and full_auto relaxation (single source of truth).
    multi_item_service = _build_multi_item_service(request, workspace_id, pool_id=pool_id)
    return AtlasAutonomousCodegenOrchestratorService(
        storage=storage,
        journal=journal,
        patch_proposal_service=patch_proposal_service,
        multi_item_autopilot_service=multi_item_service,
    )


@router.post("/run")
def run(payload: AtlasAutonomousCodegenRequest, request: Request):
    payload.pool_id = _validate_id(payload.pool_id, "pool_id")
    if payload.run_id:
        payload.run_id = _validate_id(payload.run_id, "run_id")
    payload.item_ids = [_validate_id(v, "item_id") for v in (payload.item_ids or [])]
    root = resolve_atlas_ca_data_root(request)
    try:
        AtlasPlanPoolStorage(root).load_pool(payload.pool_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=404, detail={"error": "pool_not_found", "reason": f"pool_not_found:{payload.pool_id}"}) from exc
    try:
        return _orchestrator_service(request, payload.workspace_id, pool_id=payload.pool_id).run(payload).model_dump()
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail={"error": "autonomous_codegen_failed", "reason": f"{exc.__class__.__name__}: {exc}"[:300]},
        ) from exc
