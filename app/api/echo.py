"""Echo read-only/status API router.

This router owns the low-risk Echo status/session read endpoints that have been
split from ``main.py``. Production ``main.app`` installs providers that preserve
existing EchoVault behavior, while provider-less ``create_app()`` returns
conservative, side-effect-free fallbacks that do not scan audio directories,
load ASR/TTS runtimes, open WebSockets, or call LLM/SBV2 components.
"""

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()

EchoSaveStatusProvider = Callable[[], Any]
EchoSessionsProvider = Callable[..., Any]
EchoSessionProvider = Callable[..., Any]


def default_echo_save_status_payload() -> dict[str, Any]:
    """Return the existing save-status shape without touching Echo runtime state."""
    return {
        "saving": False,
        "count": 0,
        "session_ids": [],
        "minutes_generating_count": 0,
        "minutes_generating_session_ids": [],
    }


def default_echo_sessions_payload() -> dict[str, Any]:
    """Return an empty Echo session list without scanning EchoVault storage."""
    return {"files": []}


def default_echo_session_payload(filename: str) -> Any:
    """Safely reject session downloads when no production provider is installed."""
    raise HTTPException(status_code=404, detail="ファイルが見つかりません")


def get_echo_save_status_provider(request: Request) -> EchoSaveStatusProvider | None:
    """Look up the optional app-state provider for Echo save status reads."""
    provider = getattr(request.app.state, "echo_save_status_provider", None)
    if callable(provider):
        return provider
    return None


def get_echo_sessions_provider(request: Request) -> EchoSessionsProvider | None:
    """Look up the optional app-state provider for Echo session list reads."""
    provider = getattr(request.app.state, "echo_sessions_provider", None)
    if callable(provider):
        return provider
    return None


def get_echo_session_provider(request: Request) -> EchoSessionProvider | None:
    """Look up the optional app-state provider for one Echo session file."""
    provider = getattr(request.app.state, "echo_session_provider", None)
    if callable(provider):
        return provider
    return None


@router.get("/echo/save-status")
def get_echo_save_status_api(request: Request) -> Any:
    provider = get_echo_save_status_provider(request)
    if provider is not None:
        return provider()
    return default_echo_save_status_payload()


@router.get("/echo/sessions")
def get_echo_sessions_api(request: Request) -> Any:
    provider = get_echo_sessions_provider(request)
    if provider is not None:
        return provider()
    return default_echo_sessions_payload()


@router.get("/echo/sessions/{filename:path}")
def get_echo_session_api(filename: str, request: Request) -> Any:
    provider = get_echo_session_provider(request)
    if provider is not None:
        return provider(filename)
    return default_echo_session_payload(filename)
