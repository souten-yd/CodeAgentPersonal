"""Model settings API router.

This router owns the low-risk read-only model settings endpoints that have been
split from ``main.py``. Provider lookups keep ``create_app()`` useful without
threading new factory arguments through the app factory during the migration.
When the orchestration provider is absent, the fallback response intentionally
avoids model DB, catalog, settings, and hardware access.
"""

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Request

router = APIRouter()

ModelOrchestrationProvider = Callable[[], dict[str, Any]]


def default_model_orchestration_payload() -> dict[str, Any]:
    """Return a conservative read-only orchestration payload."""
    return {
        "feature_mode": "model_orchestration",
        "policy": "ladder_fail_and_quality",
        "quality_check_enabled": True,
        "coder_primary": "",
        "coder_secondary": "",
        "coder_tertiary": "",
        "resolved_ladder": [],
        "models": [],
    }


def get_model_orchestration_provider(
    request: Request,
) -> ModelOrchestrationProvider | None:
    """Look up the optional app-state provider for model orchestration reads."""
    provider = getattr(request.app.state, "model_orchestration_provider", None)
    if callable(provider):
        return provider
    return None


@router.get("/models/orchestration")
def get_model_orchestration_api(request: Request) -> dict[str, Any]:
    provider = get_model_orchestration_provider(request)
    if provider is not None:
        return provider()
    return default_model_orchestration_payload()
