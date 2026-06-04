from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from agent.atlas_automation_features import load_full_automation_state
from agent.atlas_automation_profile_resolver import normalize_automation_profile
from app.api.atlas_root import resolve_atlas_ca_data_root
from app.atlas.patch_transaction import build_latest_patch_transaction_workflow_metadata
from app.atlas.practical_loop_metadata import build_latest_practical_loop_workflow_metadata
from app.atlas.workflow_state_contract import build_read_only_workflow_state

router = APIRouter(prefix="/api/atlas", tags=["atlas"])


def _resolve_read_only_profile_resolution(ca_data_root: Any) -> dict[str, Any]:
    try:
        state = load_full_automation_state(ca_data_root)
        return normalize_automation_profile(preset_id=str(state.get("selected_preset_id") or "review_only"))
    except Exception:
        return normalize_automation_profile(preset_id="review_only")


@router.get("/workflow-state/read-only")
def atlas_workflow_state_read_only(request: Request) -> dict[str, Any]:
    ca_data_root = resolve_atlas_ca_data_root(request)
    profile_resolution = _resolve_read_only_profile_resolution(ca_data_root)
    patch_transaction_metadata = build_latest_patch_transaction_workflow_metadata(data_root=ca_data_root)
    practical_loop_metadata = build_latest_practical_loop_workflow_metadata(data_root=ca_data_root)
    return build_read_only_workflow_state(
        goal="Atlas Next read-only supervision shell",
        project_path="Backend-provided project path when safe workflow_state is available",
        phase="practical_loop_metadata_preview",
        status="Stable backend read-only workflow_state contract available with practical loop metadata.",
        primary_cta_label="Start Atlas",
        available_actions=[{"id": "inspect_workflow_state", "label": "Inspect workflow state payload", "kind": "read_only"}],
        artifacts={
            "rollup": True,
            "dry_run": True,
            "snapshot": True,
            "allowlist": True,
            "risk": True,
            "loop_bound": practical_loop_metadata["bounded_loop"],
            "transaction": patch_transaction_metadata["patch_transaction_available"],
        },
        warnings=[
            "Route is read-only metadata only.",
            "Practical loop metadata is advisory and does not execute actions.",
            "Real-data workflow metadata is safe-if-available and may be unknown when backend state is unavailable.",
        ],
        workflow_metadata={
            "latest_pool_id": practical_loop_metadata["latest_loop_pool_id"] or None,
            "latest_run_id": practical_loop_metadata["latest_loop_run_id"] or None,
            "latest_plan_id": None,
            "latest_requirement_id": None,
            "current_phase": "practical_loop_metadata_preview",
            "latest_status": practical_loop_metadata["practical_loop_status"],
            "continuation_state": "waiting_for_backend_gate",
            "recovery_state": practical_loop_metadata["recovery_state"],
            "plan_pool_available": False,
            "active_plan_available": False,
            "last_report_available": bool(practical_loop_metadata["latest_loop_result_path"]),
            "last_error_summary": None,
            "last_updated_at": None,
            "data_freshness": "latest_safe_artifact" if practical_loop_metadata["latest_loop_result_path"] else "unknown",
            "source_detail": practical_loop_metadata["latest_loop_source_detail"],
            "workflow_snapshot_available": bool(practical_loop_metadata["latest_loop_result_path"]),
            **practical_loop_metadata,
            **patch_transaction_metadata,
        },
        profile_resolution=profile_resolution,
    )
