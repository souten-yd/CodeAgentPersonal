from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from app.api.atlas_root import resolve_atlas_ca_data_root
from app.atlas.patch_transaction import build_latest_patch_transaction_workflow_metadata
from app.atlas.workflow_state_contract import build_read_only_workflow_state

router = APIRouter(prefix="/api/atlas", tags=["atlas"])


@router.get("/workflow-state/read-only")
def atlas_workflow_state_read_only(request: Request) -> dict[str, Any]:
    ca_data_root = resolve_atlas_ca_data_root(request)
    patch_transaction_metadata = build_latest_patch_transaction_workflow_metadata(data_root=ca_data_root)
    return build_read_only_workflow_state(
        goal="Atlas Next read-only supervision shell",
        project_path="Backend-provided project path when safe workflow_state is available",
        phase="read_only_preview",
        status="Stable backend read-only workflow_state contract available (non-executable metadata).",
        primary_cta_label="Read-only preview (metadata only)",
        available_actions=[{"id": "inspect_workflow_state", "label": "Inspect workflow state payload", "kind": "read_only"}],
        artifacts={
            "rollup": True,
            "dry_run": True,
            "snapshot": True,
            "allowlist": True,
            "risk": True,
            "transaction": patch_transaction_metadata["patch_transaction_available"],
        },
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
            **patch_transaction_metadata,
        },
    )
