"""Settings API router.

This router owns the low-risk settings endpoints that have been split from
``main.py``. Provider lookups keep ``create_app()`` useful without threading new
factory arguments through the app factory during the migration. When the
single-key write provider is absent, the fallback response intentionally does
not write to the database.
"""

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Request

router = APIRouter()

SettingsGetAllProvider = Callable[[], dict[str, Any]]
SettingsGetProvider = Callable[[str], dict[str, Any]]
SettingsSetProvider = Callable[[str, dict[str, Any]], dict[str, Any]]
SettingsDefaultsProvider = Callable[[], dict[str, Any]]

_SETTINGS_FALLBACK_DEFAULTS: dict[str, Any] = {
    "llm_root_folder": "",
    "max_steps": "20",
    "auto_select_option": "true",
    "auto_skill_gen": "true",
    "search_enabled": "true",
    "search_num": "5",
    "streaming_enabled": "true",
    "ctx_size": "4096",
    "summary_max_tokens": "200",
    "read_file_inject_max_chars": "16000",
    "llm_url": "",
    "orchestration_policy": "ladder_fail_and_quality",
    "coder_primary": "",
    "coder_secondary": "",
    "coder_tertiary": "",
    "quality_check_enabled": "true",
    "feature_mode": "model_orchestration",
    "ensemble_execution_mode": "parallel",
    "ensemble_auto_switch_on_low_vram": "true",
    "gpu_static_backend": "auto",
    "gpu_usage_backend": "auto",
}


def default_settings_payload() -> dict[str, Any]:
    """Return a conservative read-only settings map for provider-less apps."""
    return dict(_SETTINGS_FALLBACK_DEFAULTS)


def default_setting_payload(key: str) -> dict[str, Any]:
    """Return the current single-key settings response shape from fallback data."""
    return {"key": key, "value": _SETTINGS_FALLBACK_DEFAULTS.get(key, "")}


def default_setting_set_payload(key: str, req: dict[str, Any]) -> dict[str, Any]:
    """Return a conservative write echo without persisting to the DB.

    Factory-created apps do not install ``settings_set_provider`` yet. Keep the
    historical response shape for callers, but intentionally avoid any storage
    side effects in that provider-less mode.
    """
    return {"ok": True, "key": key, "value": req.get("value", "")}


def get_settings_get_all_provider(request: Request) -> SettingsGetAllProvider | None:
    """Look up the optional app-state provider for the full settings map."""
    provider = getattr(request.app.state, "settings_get_all_provider", None)
    if callable(provider):
        return provider
    return None


def get_settings_get_provider(request: Request) -> SettingsGetProvider | None:
    """Look up the optional app-state provider for a single settings key."""
    provider = getattr(request.app.state, "settings_get_provider", None)
    if callable(provider):
        return provider
    return None


def get_settings_defaults_provider(request: Request) -> SettingsDefaultsProvider | None:
    """Look up the optional app-state provider for the unshadowed defaults map."""
    provider = getattr(request.app.state, "settings_defaults_provider", None)
    if callable(provider):
        return provider
    return None


def get_settings_set_provider(request: Request) -> SettingsSetProvider | None:
    """Look up the optional app-state provider for a single settings write."""
    provider = getattr(request.app.state, "settings_set_provider", None)
    if callable(provider):
        return provider
    return None


def get_settings_defaults_payload(request: Request) -> dict[str, Any]:
    """Return explicit settings defaults from provider or conservative fallback."""
    provider = get_settings_defaults_provider(request)
    if provider is not None:
        return provider()
    return default_settings_payload()


@router.get("/settings-defaults")
def get_settings_defaults_api(request: Request) -> dict[str, Any]:
    return get_settings_defaults_payload(request)


@router.get("/settings")
def get_settings_api(request: Request) -> dict[str, Any]:
    provider = get_settings_get_all_provider(request)
    if provider is not None:
        return provider()
    return default_settings_payload()


@router.get("/settings/{key}")
def get_setting_api(key: str, request: Request) -> dict[str, Any]:
    provider = get_settings_get_provider(request)
    if provider is not None:
        return provider(key)
    return default_setting_payload(key)


@router.put("/settings/{key}")
def set_setting_api(key: str, req: dict[str, Any], request: Request) -> dict[str, Any]:
    provider = get_settings_set_provider(request)
    if provider is not None:
        return provider(key, req)
    return default_setting_set_payload(key, req)
