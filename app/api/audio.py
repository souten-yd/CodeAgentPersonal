"""Low-risk audio read/status/config API router.

Provider lookups preserve production ``main.app`` behavior while keeping
``create_app()`` safe. Fallback responses here must remain side-effect-free:
no ASR/TTS model loads, CUDA probes, filesystem-heavy scans, SBV2 runtime
prepare, or direct LLM fallback calls.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from fastapi import APIRouter, Request

router = APIRouter()

VoiceStatusProvider = Callable[[], dict[str, Any]]
AsrConfigProvider = Callable[[], dict[str, Any]]
AudioRuntimeDebugProvider = Callable[[], dict[str, Any]]
Sbv2ModelsProvider = Callable[[], dict[str, Any]]
Sbv2PreviewNormalizationProvider = Callable[[dict[str, Any]], dict[str, Any]]


def _get_provider(request: Request, name: str) -> Callable[..., dict[str, Any]] | None:
    provider = getattr(request.app.state, name, None)
    if callable(provider):
        return provider
    return None


def default_voice_status_payload() -> dict[str, Any]:
    """Return conservative voice status without touching ASR runtime state."""
    return {
        "ok": True,
        "status": "uninitialized",
        "device": None,
        "compute_type": None,
        "degraded": False,
        "reason": "provider unavailable",
    }


def default_asr_config_payload() -> dict[str, Any]:
    """Return conservative ASR config without resolving runtime settings."""
    return {
        "ok": True,
        "available": False,
        "status": "unavailable",
        "provider": "unavailable",
    }


def default_audio_runtime_debug_payload() -> dict[str, Any]:
    """Return conservative audio diagnostics without live ASR/TTS probes."""
    return {
        "audio_runtime": {"status": "unavailable", "reason": "provider unavailable"},
        "main_venv_cuda": {"available": False, "reason": "provider unavailable"},
        "ctranslate2_cuda": {"available": False, "reason": "provider unavailable"},
        "sbv2_venv_cuda_probe": {"available": False, "reason": "provider unavailable"},
        "asr_selected": {},
        "tts_selected": {},
        "last_asr_cuda_error": "",
        "last_tts_worker_error": {},
        "audio_cuda_serialize_lock": False,
        "note": "audio runtime provider unavailable",
    }


def default_sbv2_models_payload() -> dict[str, Any]:
    """Return an empty SBV2 model inventory without scanning model folders."""
    return {
        "models": [],
        "model_details": [],
        "available": False,
        "status": "unavailable",
        "reason": "provider unavailable",
    }


def default_sbv2_preview_normalization_payload(req: Mapping[str, Any]) -> dict[str, Any]:
    """Return a no-op normalization preview without invoking SBV2/LLM fallback."""
    raw_text = str(req.get("raw_text") or req.get("text") or "")
    translated_text = str(req.get("translated_text") or "")
    text_source = str(req.get("text_source") or "raw")
    selected_text = translated_text if text_source == "translated" and translated_text else raw_text
    return {
        "ok": True,
        "available": False,
        "status": "unavailable",
        "reason": "provider unavailable",
        "text_source": "translated" if text_source == "translated" and translated_text else "raw",
        "source_reason": "provider_unavailable_noop",
        "model_kind": "unknown",
        "is_jp_extra": False,
        "language": str(req.get("language") or "JP"),
        "effective_language": str(req.get("language") or "JP"),
        "needs_translation": False,
        "translation_target_language": "",
        "original_text": raw_text,
        "translated_text": translated_text,
        "selected_text": selected_text,
        "normalized_text": selected_text,
        "final_text": selected_text,
        "looks_japanese": False,
        "operations": [],
        "warnings": ["provider unavailable"],
    }


@router.get("/voice/status")
def voice_status_api(request: Request) -> dict[str, Any]:
    provider = _get_provider(request, "voice_status_provider")
    if provider is not None:
        return provider()
    return default_voice_status_payload()


@router.get("/asr/config")
def asr_config_api(request: Request) -> dict[str, Any]:
    provider = _get_provider(request, "asr_config_provider")
    if provider is not None:
        return provider()
    return default_asr_config_payload()


@router.get("/audio/runtime/debug")
def get_audio_runtime_debug_api(request: Request) -> dict[str, Any]:
    provider = _get_provider(request, "audio_runtime_debug_provider")
    if provider is not None:
        return provider()
    return default_audio_runtime_debug_payload()


@router.get("/api/tts/style-bert-vits2/models")
def api_style_bert_vits2_models(request: Request) -> dict[str, Any]:
    provider = _get_provider(request, "sbv2_models_provider")
    if provider is not None:
        return provider()
    return default_sbv2_models_payload()


@router.post("/api/tts/style-bert-vits2/preview-normalization")
def api_style_bert_vits2_preview_normalization(
    req: dict[str, Any], request: Request
) -> dict[str, Any]:
    provider = _get_provider(request, "sbv2_preview_normalization_provider")
    if provider is not None:
        return provider(req)
    return default_sbv2_preview_normalization_payload(req)
