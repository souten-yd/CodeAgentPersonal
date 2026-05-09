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
StreamingStatusProvider = Callable[[], dict[str, Any]]


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


def default_streaming_status_payload() -> dict[str, Any]:
    """Return conservative streaming status without reading runtime globals."""
    return {
        "enabled": False,
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


def get_streaming_status_provider(request: Request) -> StreamingStatusProvider | None:
    """Look up the optional app-state provider for streaming status reads."""
    provider = getattr(request.app.state, "streaming_status_provider", None)
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
