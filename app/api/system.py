"""System status API router."""

import os
from collections.abc import Callable
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

ReadinessProvider = Callable[[], dict[str, Any]]
UsageProvider = Callable[[], dict[str, Any]]
UsageDebugProvider = Callable[[], dict[str, Any]]


def default_system_readiness_payload() -> dict[str, Any]:
    """Return the stable readiness response shape without app-specific probes."""
    return dict(SYSTEM_READINESS_DEFAULT_PAYLOAD)


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
