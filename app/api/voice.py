"""Voice (ASR) API router (extracted from main.py).

Thin HTTP wrappers over the ASR/voice helpers that still live in ``main`` (``voice_load``,
``voice_unload``, ``voice_transcribe``, ``_apply_asr_runtime_settings``, ``_resolve_asr_profile``,
``_voice_model_exists``) and the already-extracted transcribe service body. Imported lazily inside
each handler; see docs/MAINTAINABILITY_PLAN.md. Behavior (CUDA fallback, response shape, debug entry
format) is preserved.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

router = APIRouter(tags=["voice"])


@router.post("/voice/load")
def voice_load_api(req: dict):
    from main import _apply_asr_runtime_settings, voice_load
    _apply_asr_runtime_settings(req)
    model_name = str(req.get("model", "small")).strip() or "small"
    device = req.get("device")
    if device not in ("cpu", "cuda"):
        device = None
    return voice_load(model_name, device=device)


@router.post("/voice/unload")
def voice_unload_api():
    from main import voice_unload
    return voice_unload()


# PR4.62: ASR transcribe service body extracted; route owner now lives in this router.
# Preserve CUDA fallback, response shape, model load timing, and debug entry format.
@router.post("/voice/transcribe")
def voice_transcribe_api(req: dict):
    from main import (
        IS_RUNPOD_RUNTIME,
        AudioRuntimeHttpError,
        VoiceTranscribeServiceDependencies,
        _apply_asr_runtime_settings,
        _resolve_asr_profile,
        _voice_model_exists,
        run_voice_transcribe_service_body,
        voice_transcribe,
    )
    deps = VoiceTranscribeServiceDependencies(
        apply_asr_runtime_settings=_apply_asr_runtime_settings,
        resolve_asr_profile=_resolve_asr_profile,
        voice_model_exists=_voice_model_exists,
        transcribe_audio=voice_transcribe,
        is_runpod_runtime=lambda: IS_RUNPOD_RUNTIME,
        json_dumps=json.dumps,
    )
    try:
        response = run_voice_transcribe_service_body(req, deps)
    except AudioRuntimeHttpError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    return StreamingResponse(
        response.body_iterator,
        media_type=response.media_type,
        headers=dict(response.headers),
    )
