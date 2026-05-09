"""Runtime controls API router.

This router owns low-risk read-only runtime status endpoints that have been
split from ``main.py``. Provider lookups preserve production behavior for
``main.app`` while keeping ``create_app()`` safe: fallback responses avoid live
llama-server HTTP probes, model-manager access, and mutable runtime globals.
"""

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Request

router = APIRouter()

RuntimeLlmCtxProvider = Callable[[], dict[str, Any]]
RuntimeLlmPropsProvider = Callable[[], dict[str, Any]]
SearchStatusProvider = Callable[[], dict[str, Any]]
SearchEnableProvider = Callable[[], dict[str, Any]]
SearchDisableProvider = Callable[[], dict[str, Any]]
SearchNumProvider = Callable[[int], dict[str, Any]]
StreamingStatusProvider = Callable[[], dict[str, Any]]
StreamingEnableProvider = Callable[[], dict[str, Any]]
StreamingDisableProvider = Callable[[], dict[str, Any]]
RuntimeLlmCtxSetProvider = Callable[[int], dict[str, Any]]
RuntimeCudaDebugProvider = Callable[[], dict[str, Any]]
AudioRuntimeDebugProvider = Callable[[], dict[str, Any]]
ModelStartupDebugProvider = Callable[[], dict[str, Any]]


def default_runtime_llm_ctx_payload() -> dict[str, Any]:
    """Return a conservative LLM context payload without runtime access."""
    return {
        "n_ctx": 0,
        "ctx_size": 0,
    }


def default_runtime_llm_props_payload() -> dict[str, Any]:
    """Return conservative LLM props without connecting to llama-server."""
    return {
        "n_ctx": 0,
        "n_ctx_runtime": 0,
        "n_ctx_train": 0,
        "raw": {},
        "note": "runtime provider unavailable",
    }


def default_search_status_payload() -> dict[str, Any]:
    """Return conservative search status without reading runtime globals."""
    return {
        "enabled": False,
        "num_results": 5,
    }


def default_search_enable_payload() -> dict[str, Any]:
    """Echo the enable response shape without mutating search state."""
    return {"enabled": True}


def default_search_disable_payload() -> dict[str, Any]:
    """Echo the disable response shape without mutating search state."""
    return {"enabled": False}


def default_search_num_payload(num_results: int) -> dict[str, Any]:
    """Echo the requested search result count without saving it."""
    return {"num_results": num_results}


def default_streaming_status_payload() -> dict[str, Any]:
    """Return conservative streaming status without reading runtime globals."""
    return {
        "enabled": False,
    }


def default_streaming_enable_payload() -> dict[str, Any]:
    """Echo the enable response shape without mutating streaming state."""
    return {"enabled": True}


def default_streaming_disable_payload() -> dict[str, Any]:
    """Echo the disable response shape without mutating streaming state."""
    return {"enabled": False}


def default_llm_ctx_set_payload(ctx_size: int) -> dict[str, Any]:
    """Echo the requested context size without touching model/runtime state."""
    return {"n_ctx": ctx_size}


def default_runtime_cuda_debug_payload() -> dict[str, Any]:
    """Return conservative CUDA diagnostics without live GPU/model probes."""
    return {
        "intended_backend": "unknown",
        "runpod_detected": False,
        "gpu_validation_status": "unavailable",
        "note": "runtime provider unavailable",
    }


def default_audio_runtime_debug_payload() -> dict[str, Any]:
    """Return conservative audio diagnostics without live ASR/TTS probes."""
    return {
        "runtime": "unavailable",
        "asr": {},
        "tts": {},
        "note": "audio runtime provider unavailable",
    }


def default_model_startup_debug_payload() -> dict[str, Any]:
    """Return conservative model startup diagnostics without model-manager access."""
    return {
        "status": "unavailable",
        "hints": [],
        "log_tail": "",
        "note": "model startup provider unavailable",
    }


def get_runtime_llm_ctx_provider(request: Request) -> RuntimeLlmCtxProvider | None:
    """Look up the optional app-state provider for LLM context status reads."""
    provider = getattr(request.app.state, "runtime_llm_ctx_provider", None)
    if callable(provider):
        return provider
    return None


def get_runtime_llm_props_provider(request: Request) -> RuntimeLlmPropsProvider | None:
    """Look up the optional app-state provider for LLM props reads."""
    provider = getattr(request.app.state, "runtime_llm_props_provider", None)
    if callable(provider):
        return provider
    return None


def get_search_status_provider(request: Request) -> SearchStatusProvider | None:
    """Look up the optional app-state provider for search status reads."""
    provider = getattr(request.app.state, "search_status_provider", None)
    if callable(provider):
        return provider
    return None


def get_search_enable_provider(request: Request) -> SearchEnableProvider | None:
    """Look up the optional app-state provider for search enable writes."""
    provider = getattr(request.app.state, "search_enable_provider", None)
    if callable(provider):
        return provider
    return None


def get_search_disable_provider(request: Request) -> SearchDisableProvider | None:
    """Look up the optional app-state provider for search disable writes."""
    provider = getattr(request.app.state, "search_disable_provider", None)
    if callable(provider):
        return provider
    return None


def get_search_num_provider(request: Request) -> SearchNumProvider | None:
    """Look up the optional app-state provider for search result count writes."""
    provider = getattr(request.app.state, "search_num_provider", None)
    if callable(provider):
        return provider
    return None


def get_streaming_status_provider(request: Request) -> StreamingStatusProvider | None:
    """Look up the optional app-state provider for streaming status reads."""
    provider = getattr(request.app.state, "streaming_status_provider", None)
    if callable(provider):
        return provider
    return None


def get_streaming_enable_provider(request: Request) -> StreamingEnableProvider | None:
    """Look up the optional app-state provider for streaming enable writes."""
    provider = getattr(request.app.state, "streaming_enable_provider", None)
    if callable(provider):
        return provider
    return None


def get_streaming_disable_provider(request: Request) -> StreamingDisableProvider | None:
    """Look up the optional app-state provider for streaming disable writes."""
    provider = getattr(request.app.state, "streaming_disable_provider", None)
    if callable(provider):
        return provider
    return None


def get_runtime_llm_ctx_set_provider(request: Request) -> RuntimeLlmCtxSetProvider | None:
    """Look up the optional app-state provider for LLM context writes."""
    provider = getattr(request.app.state, "runtime_llm_ctx_set_provider", None)
    if callable(provider):
        return provider
    return None


def get_runtime_cuda_debug_provider(request: Request) -> RuntimeCudaDebugProvider | None:
    """Look up the optional app-state provider for CUDA diagnostic reads."""
    provider = getattr(request.app.state, "runtime_cuda_debug_provider", None)
    if callable(provider):
        return provider
    return None


def get_audio_runtime_debug_provider(request: Request) -> AudioRuntimeDebugProvider | None:
    """Look up the optional app-state provider for audio diagnostic reads."""
    provider = getattr(request.app.state, "audio_runtime_debug_provider", None)
    if callable(provider):
        return provider
    return None


def get_model_startup_debug_provider(request: Request) -> ModelStartupDebugProvider | None:
    """Look up the optional app-state provider for model startup diagnostic reads."""
    provider = getattr(request.app.state, "model_startup_debug_provider", None)
    if callable(provider):
        return provider
    return None


@router.get("/llm/ctx")
def get_runtime_llm_ctx_api(request: Request) -> dict[str, Any]:
    provider = get_runtime_llm_ctx_provider(request)
    if provider is not None:
        return provider()
    return default_runtime_llm_ctx_payload()


@router.get("/llm/props")
def get_runtime_llm_props_api(request: Request) -> dict[str, Any]:
    provider = get_runtime_llm_props_provider(request)
    if provider is not None:
        return provider()
    return default_runtime_llm_props_payload()


@router.get("/search/status")
def get_search_status_api(request: Request) -> dict[str, Any]:
    provider = get_search_status_provider(request)
    if provider is not None:
        return provider()
    return default_search_status_payload()


@router.get("/streaming/status")
def get_streaming_status_api(request: Request) -> dict[str, Any]:
    provider = get_streaming_status_provider(request)
    if provider is not None:
        return provider()
    return default_streaming_status_payload()


@router.post("/llm/ctx")
def set_runtime_llm_ctx_api(req: dict[str, Any], request: Request) -> dict[str, Any]:
    n_ctx = int(req.get("n_ctx", 0))
    provider = get_runtime_llm_ctx_set_provider(request)
    if provider is not None:
        return provider(n_ctx)
    return default_llm_ctx_set_payload(n_ctx)


@router.post("/search/num")
def set_search_num_api(req: dict[str, Any], request: Request) -> dict[str, Any]:
    num_results = int(req.get("num_results", 5))
    provider = get_search_num_provider(request)
    if provider is not None:
        return provider(num_results)
    return default_search_num_payload(num_results)


@router.post("/search/enable")
def enable_search_api(request: Request) -> dict[str, Any]:
    provider = get_search_enable_provider(request)
    if provider is not None:
        return provider()
    return default_search_enable_payload()


@router.post("/search/disable")
def disable_search_api(request: Request) -> dict[str, Any]:
    provider = get_search_disable_provider(request)
    if provider is not None:
        return provider()
    return default_search_disable_payload()


@router.post("/streaming/enable")
def enable_streaming_api(request: Request) -> dict[str, Any]:
    provider = get_streaming_enable_provider(request)
    if provider is not None:
        return provider()
    return default_streaming_enable_payload()


@router.post("/streaming/disable")
def disable_streaming_api(request: Request) -> dict[str, Any]:
    provider = get_streaming_disable_provider(request)
    if provider is not None:
        return provider()
    return default_streaming_disable_payload()


@router.get("/runtime/cuda-debug")
def get_runtime_cuda_debug_api(request: Request) -> dict[str, Any]:
    provider = get_runtime_cuda_debug_provider(request)
    if provider is not None:
        return provider()
    return default_runtime_cuda_debug_payload()


@router.get("/audio/runtime/debug")
def get_audio_runtime_debug_api(request: Request) -> dict[str, Any]:
    provider = get_audio_runtime_debug_provider(request)
    if provider is not None:
        return provider()
    return default_audio_runtime_debug_payload()


@router.get("/debug/model-startup")
def get_model_startup_debug_api(request: Request) -> dict[str, Any]:
    provider = get_model_startup_debug_provider(request)
    if provider is not None:
        return provider()
    return default_model_startup_debug_payload()
