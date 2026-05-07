"""System status API router."""

import os
from collections.abc import Callable
from copy import deepcopy
from typing import Any

from fastapi import APIRouter, Request

from app.env_detection import detect_gpu_profile, detect_os_profile, detect_runpod

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

SYSTEM_USAGE_DEFAULT_PAYLOAD: dict[str, Any] = {
    "cpu_percent": 0.0,
    "ram_total_mb": 0,
    "ram_used_mb": 0,
    "gpu_backend": "unavailable",
    "gpu_backend_selected": "unavailable",
    "gpus": [],
    "updated_at": "",
}

SYSTEM_USAGE_DEBUG_FINAL_USAGE_DEFAULT_PAYLOAD: dict[str, Any] = {
    "gpus": [],
    "vram_confidence": "unknown",
    "vram_source_backend": "unavailable",
    "updated_at": "",
}

SYSTEM_USAGE_DEBUG_DEFAULT_PAYLOAD: dict[str, Any] = {
    "gpu_backend_selected": "unavailable",
    "gpu_backend": "unavailable",
    "raw_parse_summary": [],
    "parse_source": "unavailable",
    "nvidia_smi_failure_reason": "",
    "adopted_values": {},
    "final_usage": SYSTEM_USAGE_DEBUG_FINAL_USAGE_DEFAULT_PAYLOAD,
}

ReadinessProvider = Callable[[], dict[str, Any]]
UsageProvider = Callable[[], dict[str, Any]]
UsageDebugProvider = Callable[[], dict[str, Any]]


def default_system_readiness_payload() -> dict[str, Any]:
    """Return the stable readiness response shape without app-specific probes."""
    return dict(SYSTEM_READINESS_DEFAULT_PAYLOAD)


def default_system_usage_unavailable_payload() -> dict[str, Any]:
    """Return a conservative usage response shape for provider-less apps."""
    return deepcopy(SYSTEM_USAGE_DEFAULT_PAYLOAD)


def default_system_usage_debug_unavailable_payload() -> dict[str, Any]:
    """Return a conservative usage debug response shape for provider-less apps."""
    return deepcopy(SYSTEM_USAGE_DEBUG_DEFAULT_PAYLOAD)


def get_system_usage_provider(request: Request) -> UsageProvider | None:
    """Look up the optional app-state system usage provider."""
    provider = getattr(request.app.state, "system_usage_provider", None)
    if callable(provider):
        return provider
    return None


def get_system_usage_debug_provider(request: Request) -> UsageDebugProvider | None:
    """Look up the optional app-state system usage debug provider."""
    provider = getattr(request.app.state, "system_usage_debug_provider", None)
    if callable(provider):
        return provider
    return None


@router.get("/system/readiness")
def system_readiness(request: Request) -> dict[str, Any]:
    provider = getattr(request.app.state, "system_readiness_provider", None)
    if callable(provider):
        return provider()
    return default_system_readiness_payload()


@router.get("/system/env")
def system_env() -> dict[str, Any]:
    """Runtime environment probe (must not raise HTTP 500)."""
    style_bert_vits2_device = os.environ.get("CODEAGENT_STYLE_BERT_VITS2_DEVICE", "")
    try:
        return {
            "runpod": detect_runpod(),
            "os": detect_os_profile(),
            "gpu": detect_gpu_profile(),
            "style_bert_vits2_device": style_bert_vits2_device,
        }
    except Exception as e:
        return {
            "error": "failed_to_detect_environment",
            "detail": str(e),
            "runpod": False,
            "os": {},
            "gpu": {},
            "style_bert_vits2_device": style_bert_vits2_device,
        }
