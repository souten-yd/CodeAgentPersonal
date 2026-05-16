"""Model settings API router.

This router owns the low-risk read-only model settings endpoints that have been
split from ``main.py``. Provider lookups keep ``create_app()`` useful without
threading new factory arguments through the app factory during the migration.
When a provider is absent, fallback responses intentionally avoid model DB,
catalog, settings, model-manager, runtime, and hardware access.
"""

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Request

router = APIRouter()

ModelOrchestrationProvider = Callable[[], dict[str, Any]]
ModelRolesProvider = Callable[[], dict[str, Any]]
ModelDbListProvider = Callable[[], dict[str, Any]]
ModelDbStatusProvider = Callable[[], dict[str, Any]]
ModelManagerStatusProvider = Callable[[], dict[str, Any]]


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


def default_model_roles_payload() -> dict[str, Any]:
    """Return a conservative read-only model roles payload."""
    return {
        "roles": [],
        "planner_key": "",
        "assignments": {},
        "models": [],
    }


def default_model_db_list_payload() -> dict[str, Any]:
    """Return a conservative model DB list payload without DB access."""
    return {
        "models": [],
        "count": 0,
    }


def default_model_db_status_payload() -> dict[str, Any]:
    """Return a conservative model DB status payload without DB access."""
    return {
        "db_exists": False,
        "has_models": False,
        "total": 0,
        "benchmarked": 0,
        "has_vlm": False,
        "db_path": "",
    }


def default_model_manager_status_payload() -> dict[str, Any]:
    """Return conservative model manager status without runtime access."""
    return {
        "status": "unavailable",
        "current_key": "",
        "catalog": {},
        "last_model_load_status": "idle",
        "last_model_load_error": None,
        "gpu_validation_status": "unavailable",
        "last_gpu_validation_status": "unavailable",
        "gpu_validation_reason": "runtime provider unavailable",
        "last_gpu_validation_reason": "runtime provider unavailable",
        "gpu_validation_path": None,
        "last_gpu_validation_path": None,
        "cuda_init_failed": False,
        "no_usable_gpu": False,
        "llama_log_parser_stale_suspected": False,
        "llama_readiness_signals": {},
    }


def get_model_orchestration_provider(
    request: Request,
) -> ModelOrchestrationProvider | None:
    """Look up the optional app-state provider for model orchestration reads."""
    provider = getattr(request.app.state, "model_orchestration_provider", None)
    if callable(provider):
        return provider
    return None


def get_model_roles_provider(request: Request) -> ModelRolesProvider | None:
    """Look up the optional app-state provider for model role reads."""
    provider = getattr(request.app.state, "model_roles_provider", None)
    if callable(provider):
        return provider
    return None


def get_model_db_list_provider(request: Request) -> ModelDbListProvider | None:
    """Look up the optional app-state provider for model DB list reads."""
    provider = getattr(request.app.state, "model_db_list_provider", None)
    if callable(provider):
        return provider
    return None


def get_model_db_status_provider(
    request: Request,
) -> ModelDbStatusProvider | None:
    """Look up the optional app-state provider for model DB status reads."""
    provider = getattr(request.app.state, "model_db_status_provider", None)
    if callable(provider):
        return provider
    return None


def get_model_manager_status_provider(
    request: Request,
) -> ModelManagerStatusProvider | None:
    """Look up the optional app-state provider for model manager status reads."""
    provider = getattr(request.app.state, "model_manager_status_provider", None)
    if callable(provider):
        return provider
    return None


@router.get("/models/orchestration")
def get_model_orchestration_api(request: Request) -> dict[str, Any]:
    provider = get_model_orchestration_provider(request)
    if provider is not None:
        return provider()
    return default_model_orchestration_payload()


@router.get("/models/roles")
def get_model_role_assignments_api(request: Request) -> dict[str, Any]:
    provider = get_model_roles_provider(request)
    if provider is not None:
        return provider()
    return default_model_roles_payload()


@router.get("/models/db")
def list_models_db_api(request: Request) -> dict[str, Any]:
    provider = get_model_db_list_provider(request)
    if provider is not None:
        return provider()
    return default_model_db_list_payload()


@router.get("/models/db/status")
def get_model_db_status_api(request: Request) -> dict[str, Any]:
    provider = get_model_db_status_provider(request)
    if provider is not None:
        return provider()
    return default_model_db_status_payload()


@router.get("/model/status")
def get_model_manager_status_api(request: Request) -> dict[str, Any]:
    provider = get_model_manager_status_provider(request)
    if provider is not None:
        return provider()
    return default_model_manager_status_payload()
