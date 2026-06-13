"""Ensemble settings/VRAM API router (extracted from main.py).

Thin HTTP wrappers over the ensemble helpers that still live in ``main``
(``get_ensemble_resource_status``, ``settings_set_bulk``/``settings_get``,
``_sync_ensemble_settings_to_opencode_json``, ``_apply_ensemble_execution_mode_guard``). Imported
lazily inside each handler; see docs/MAINTAINABILITY_PLAN.md.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["ensemble"])


@router.get("/ensemble/settings")
def get_ensemble_settings_api():
    from main import get_ensemble_resource_status
    status = get_ensemble_resource_status()
    return {
        "execution_mode": status.get("configured_mode", "parallel"),
        "auto_switch_on_low_vram": status.get("auto_switch_on_low_vram", True),
        "status": status,
    }


@router.post("/ensemble/settings")
def save_ensemble_settings_api(req: dict):
    from main import (
        _apply_ensemble_execution_mode_guard,
        _sync_ensemble_settings_to_opencode_json,
        settings_get,
        settings_set_bulk,
    )
    mode = str(req.get("execution_mode", "parallel")).strip().lower() or "parallel"
    if mode not in ("parallel", "serial"):
        raise HTTPException(400, "execution_mode must be parallel or serial")
    auto_switch = bool(req.get("auto_switch_on_low_vram", True))
    settings_set_bulk({
        "ensemble_execution_mode": mode,
        "ensemble_auto_switch_on_low_vram": "true" if auto_switch else "false",
    })
    _sync_ensemble_settings_to_opencode_json()
    status = _apply_ensemble_execution_mode_guard()
    return {"ok": True, "execution_mode": settings_get("ensemble_execution_mode"), "status": status}


@router.get("/ensemble/vram")
def get_ensemble_vram_api():
    from main import get_ensemble_resource_status
    return get_ensemble_resource_status()
