"""Application-state registry for production Project Intelligence (PIR-2)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent.project_intelligence.production_factory import (
    ProductionProjectIntelligenceService,
    build_production_project_intelligence,
)
from agent.project_intelligence.rollout import RolloutConfig

STATE_ATTR = "project_intelligence_service"


def register_project_intelligence_service(
    app: Any,
    *,
    ca_data_dir: str | Path,
    rollout: RolloutConfig | None = None,
    env: dict | None = None,
) -> ProductionProjectIntelligenceService:
    existing = getattr(app.state, STATE_ATTR, None)
    if existing is not None:
        return existing
    service = build_production_project_intelligence(ca_data_dir=ca_data_dir, rollout=rollout, env=env)
    setattr(app.state, STATE_ATTR, service)
    setattr(app.state, "project_intelligence", service.coordinator)
    return service


def get_project_intelligence_service(app: Any) -> ProductionProjectIntelligenceService | None:
    service = getattr(app.state, STATE_ATTR, None)
    return service if isinstance(service, ProductionProjectIntelligenceService) else None


def close_project_intelligence_service(app: Any) -> None:
    service = get_project_intelligence_service(app)
    if service is not None:
        service.close()
        setattr(app.state, STATE_ATTR, None)
        setattr(app.state, "project_intelligence", None)

