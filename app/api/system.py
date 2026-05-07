"""System status API router."""

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Request

router = APIRouter()

SYSTEM_READINESS_DEFAULT_PAYLOAD: dict[str, Any] = {
    "fastapi": "ready",
    "model_db_exists": False,
    "model_db_status_available": False,
    "model_db_status": {},
    "llm_autoload_eligible": False,
    "autoload_reason": "unknown",
    "llm_running": False,
}

ReadinessProvider = Callable[[], dict[str, Any]]


def default_system_readiness_payload() -> dict[str, Any]:
    """Return the stable readiness response shape without app-specific probes."""
    return dict(SYSTEM_READINESS_DEFAULT_PAYLOAD)


@router.get("/system/readiness")
def system_readiness(request: Request) -> dict[str, Any]:
    provider = getattr(request.app.state, "system_readiness_provider", None)
    if callable(provider):
        return provider()
    return default_system_readiness_payload()
