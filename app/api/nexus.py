"""Read-only Nexus status/list API routes.

These endpoints are intentionally routed through providers stored on
``app.state``.  The production ``main.app`` registers providers that preserve
current Nexus behavior, while ``create_app()`` can serve lightweight fallback
payloads without touching Nexus storage, SearXNG, LLMs, or background jobs.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Query, Request

NexusSummaryProvider = Callable[..., Any]
NexusDocumentsProvider = Callable[..., Any]
NexusActiveJobsProvider = Callable[..., Any]
NexusWebStatusProvider = Callable[..., Any]

router = APIRouter()


def default_nexus_summary_payload(project: str = "default") -> dict[str, Any]:
    """Return a conservative Nexus summary without external side effects."""
    return {
        "documents": 0,
        "chunks": 0,
        "reports": 0,
        "active_jobs": 0,
        "limits": {
            "max_upload_mb": 0,
            "max_upload_bytes": 0,
            "max_download_mb": 0,
            "max_total_download_mb": 0,
            "max_downloads": 0,
            "download_timeout_sec": 0,
        },
    }


def default_nexus_documents_payload(
    project: str = "default",
    q: str = "",
    limit: int = 100,
) -> dict[str, Any]:
    """Return an empty Nexus document list without scanning storage."""
    return {"documents": []}


def default_nexus_active_jobs_payload(limit: int = 50) -> dict[str, Any]:
    """Return an empty Nexus active job list without reading job registries."""
    return {"jobs": []}


def default_nexus_web_status_payload() -> dict[str, Any]:
    """Return conservative web-search status without probing SearXNG/network."""
    unavailable_status = {
        "kind": "unknown",
        "enabled": False,
        "configured": False,
        "message": "Nexus web search status is unavailable in app-factory fallback.",
    }
    return {
        "enable_web": False,
        "provider": "",
        "fallback_providers": [],
        "free_only": True,
        "paid_providers_enabled": False,
        "brave_search_api_key_set": False,
        "searxng_url": "",
        "searxng_configured": False,
        "configured": False,
        "active_provider": "unknown",
        "provider_status": {},
        "provider_status_active": unavailable_status,
        "message": unavailable_status["message"],
        "searxng_state": "unavailable",
        "searxng_state_message": "SearXNG status is unavailable in app-factory fallback.",
        "non_fatal": True,
        "stub": True,
        "provider_errors": {"unknown": [unavailable_status["message"]]},
        "last_provider_errors": {},
        "last_selected_provider": None,
        "last_non_fatal": None,
        "last_message": "",
        "last_search_at": None,
        "runpod_searxng_autostart_status": "",
        "runpod_searxng_autostart_hint": "",
    }


def _provider(request: Request, name: str, fallback: Callable[..., Any]) -> Callable[..., Any]:
    provider = getattr(request.app.state, name, None)
    if callable(provider):
        return provider
    return fallback


@router.get("/nexus/summary")
@router.get("/nexus/dashboard/summary")
def get_nexus_summary_api(
    request: Request,
    project: str = Query("default"),
) -> Any:
    provider = _provider(request, "nexus_summary_provider", default_nexus_summary_payload)
    return provider(project=project)


@router.get("/nexus/documents")
@router.get("/nexus/library/documents")
def get_nexus_documents_api(
    request: Request,
    project: str = Query("default"),
    q: str = Query(""),
    limit: int = Query(100, ge=1, le=500),
) -> Any:
    provider = _provider(request, "nexus_documents_provider", default_nexus_documents_payload)
    return provider(project=project, q=q, limit=limit)


@router.get("/nexus/jobs/active")
def get_nexus_active_jobs_api(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
) -> Any:
    provider = _provider(request, "nexus_active_jobs_provider", default_nexus_active_jobs_payload)
    return provider(limit=limit)


@router.get("/nexus/web/status")
def get_nexus_web_status_api(request: Request) -> Any:
    provider = _provider(request, "nexus_web_status_provider", default_nexus_web_status_payload)
    return provider()
