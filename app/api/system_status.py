"""Low-risk system status API router."""

from collections.abc import Callable
from copy import deepcopy
from typing import Any

from fastapi import APIRouter, Request

router = APIRouter()

HealthProvider = Callable[[], dict[str, Any]]
SystemSummaryProvider = Callable[[], dict[str, Any]]
SystemUsageProvider = Callable[[], dict[str, Any]]

HEALTH_DEFAULT_PAYLOAD: dict[str, Any] = {"ok": True, "status": "ok"}
SYSTEM_SUMMARY_DEFAULT_PAYLOAD: dict[str, Any] = {
    "ok": True,
    "runtime": "factory",
    "summary": {},
    "note": "system summary provider unavailable",
}
SYSTEM_USAGE_DEFAULT_PAYLOAD: dict[str, Any] = {
    "ok": True,
    "usage": {},
    "note": "system usage provider unavailable",
}


def default_health_payload() -> dict[str, Any]:
    """Return the lightweight app-factory health payload."""
    return dict(HEALTH_DEFAULT_PAYLOAD)


def default_system_summary_payload() -> dict[str, Any]:
    """Return a conservative summary payload without runtime probes."""
    return deepcopy(SYSTEM_SUMMARY_DEFAULT_PAYLOAD)


def default_system_usage_payload() -> dict[str, Any]:
    """Return a conservative usage payload without CPU/RAM/GPU probes."""
    return deepcopy(SYSTEM_USAGE_DEFAULT_PAYLOAD)


def _get_provider(request: Request, name: str) -> Callable[[], dict[str, Any]] | None:
    provider = getattr(request.app.state, name, None)
    if callable(provider):
        return provider
    return None


@router.get("/health")
def health(request: Request) -> dict[str, Any]:
    provider = _get_provider(request, "health_provider")
    if provider is not None:
        return provider()
    return default_health_payload()


@router.get("/system/summary")
def system_summary(request: Request) -> dict[str, Any]:
    provider = _get_provider(request, "system_summary_provider")
    if provider is not None:
        return provider()
    return default_system_summary_payload()


@router.get("/system/usage")
def system_usage(request: Request) -> dict[str, Any]:
    provider = _get_provider(request, "system_usage_provider")
    if provider is not None:
        return provider()
    return default_system_usage_payload()
