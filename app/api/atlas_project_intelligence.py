"""Read-only Project Intelligence production health API (PIR-2)."""

from __future__ import annotations

from fastapi import APIRouter, Request

from agent.project_intelligence.service_registry import get_project_intelligence_service
from app.api.atlas_root import resolve_atlas_ca_data_root

router = APIRouter(prefix="/api/atlas/project-intelligence", tags=["atlas-project-intelligence"])


@router.get("/health")
def atlas_project_intelligence_health(request: Request) -> dict:
    service = get_project_intelligence_service(request.app)
    if service is None:
        return {
            "status": "unregistered",
            "data_dir": str(resolve_atlas_ca_data_root(request) / "project_intelligence"),
            "rollout": {"mode": "off", "enabled": False, "shadow": False, "active_phases": []},
            "preflight": {"ok": True, "mode": "off", "implementation_classes": {}},
            "rollout_state": {"transitions": [], "rollback_history": []},
        }
    return service.health()

