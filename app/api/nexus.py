"""Provider-backed Nexus API routes.

These endpoints are intentionally routed through providers stored on
``app.state``. The production ``main.app`` registers providers that preserve
current Nexus behavior, while ``create_app()`` can serve lightweight fallback
payloads without touching Nexus storage, SearXNG, LLMs, or background jobs.

PR4.53 responsibility lock: this module owns HTTP routes, request parsing,
provider dispatch, and app-factory fallback payloads only. LLM calls, SearXNG
execution, indexing, recursive/deep research loops, and report generation stay
outside this route layer.
"""

from __future__ import annotations

import inspect
import traceback
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, File, Form, Query, Request, UploadFile
from pydantic import BaseModel, Field

NexusSummaryProvider = Callable[..., Any]
NexusDocumentsProvider = Callable[..., Any]
NexusActiveJobsProvider = Callable[..., Any]
NexusWebStatusProvider = Callable[..., Any]
NexusUploadProvider = Callable[..., Any]
NexusSearchProvider = Callable[..., Any]
NexusWebSearchProvider = Callable[..., Any]
NexusWebResearchProvider = Callable[..., Any]
NexusResearchProvider = Callable[..., Any]
NexusDeepResearchProvider = Callable[..., Any]
NexusRecursiveResearchProvider = Callable[..., Any]
NexusSourcesSearchProvider = Callable[..., Any]
NexusEvidenceAddFromChunksProvider = Callable[..., Any]
NexusResearchFollowupProvider = Callable[..., Any]
NexusWebCollectProvider = Callable[..., Any]
NexusAskProvider = Callable[..., Any]
NexusReportBuildProvider = Callable[..., Any]

router = APIRouter()


class NexusSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    scope: str | list[str] | None = None
    doc_types: list[str] = Field(default_factory=list)
    limit: int | None = Field(default=None, ge=1, le=100)
    filters: dict = Field(default_factory=dict)
    top_k: int | None = Field(default=None, ge=1, le=100)
    as_evidence: bool = False


class NexusWebSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    mode: str = Field(default="standard")
    depth: str | None = None
    max_queries: int | None = Field(default=None, ge=1, le=20)
    max_results_per_query: int | None = Field(default=None, ge=1, le=20)
    scope: str | list[str] | None = None
    language: str | None = None


class NexusResearchRunRequest(BaseModel):
    query: str = Field(min_length=1)
    project: str = Field(default="default")
    mode: str = Field(default="standard")
    depth: str | None = None
    max_queries: int | None = Field(default=None, ge=1, le=20)
    max_results_per_query: int | None = Field(default=None, ge=1, le=20)
    max_sources: int | None = Field(default=None, ge=1, le=200)
    max_downloads: int | None = Field(default=None, ge=1, le=200)
    max_download_mb: int | None = Field(default=None, ge=1, le=500)
    max_total_download_mb: int | None = Field(default=None, ge=1, le=2048)
    scope: str | list[str] | None = None
    language: str | None = None
    manual_urls: list[str] | None = None
    prefer_pdf: bool = True
    official_first: bool = True
    download_timeout_sec: int | None = Field(default=None, ge=1, le=600)
    continue_on_download_error: bool = True
    recursive_search: bool = False
    max_iterations: int = Field(default=1, ge=1, le=5)
    max_followup_queries: int = Field(default=4, ge=1, le=10)
    confidence_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    stop_when_sufficient: bool = True
    # Restore source-profile contract used by app/nexus/research_api.py.
    source_profile: str = Field(default="web")
    news_budget: dict | None = None


class NexusSourceSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    scope: str = Field(default="current_research_job")
    job_id: str | None = None
    source_ids: list[str] = Field(default_factory=list)
    source_types: list[str] = Field(default_factory=list)
    limit: int = Field(default=20, ge=1, le=100)
    collapse_duplicates: bool = False


class NexusEvidenceAddFromChunksRequest(BaseModel):
    job_id: str = Field(min_length=1)
    chunk_ids: list[str] = Field(default_factory=list)
    source_id: str | None = None


class NexusResearchFollowupRequest(BaseModel):
    question: str = Field(min_length=1)
    use_existing_sources_only: bool = True
    limit: int = Field(default=20, ge=1, le=100)
    collapse_duplicates: bool = False
    project: str = Field(default="default")
    mode: str = Field(default="deep")
    max_queries: int | None = Field(default=None, ge=1, le=20)
    max_results_per_query: int | None = Field(default=None, ge=1, le=20)
    max_sources: int | None = Field(default=None, ge=1, le=200)
    max_downloads: int | None = Field(default=None, ge=1, le=200)
    max_iterations: int = Field(default=1, ge=1, le=5)
    confidence_threshold: float = Field(default=0.78, ge=0.0, le=1.0)
    source_profile: str = Field(default="web")


class NexusCollectRequest(BaseModel):
    job_id: str = Field(min_length=1)
    project: str = Field(default="default")
    search_items: list[dict] = Field(default_factory=list)
    manual_urls: list[str] = Field(default_factory=list)
    max_download_mb: int | None = Field(default=None, ge=1, le=2048)
    max_total_download_mb: int | None = Field(default=None, ge=1, le=2048)
    max_downloads: int | None = Field(default=None, ge=1, le=200)
    download_timeout_sec: int | None = Field(default=None, ge=1, le=600)
    continue_on_download_error: bool = True


class BuildReportRequest(BaseModel):
    job_id: str = Field(min_length=1)
    report_type: str = Field(default="general", min_length=1)
    title: str | None = None


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
        "last_diagnostics": [],
        "last_search_at": None,
        "searxng_engine_profile": "safe_research",
        "searxng_keep_only_engines": [],
        "searxng_health_engine": "wikipedia",
        "runpod_searxng_autostart_status": "",
        "runpod_searxng_autostart_hint": "",
    }


def _unavailable(operation_name: str, **extra: Any) -> dict[str, Any]:
    payload = {
        "ok": False,
        "status": "unavailable",
        "message": f"nexus {operation_name} provider unavailable",
    }
    payload.update(extra)
    return payload


def default_nexus_upload_payload(*, file: UploadFile | None = None, project: str = "default") -> dict[str, Any]:
    return _unavailable("upload", document_id=None, job_id=None)


def default_nexus_search_payload(payload: NexusSearchRequest) -> dict[str, Any]:
    return _unavailable(
        "search",
        query=payload.query,
        scope=payload.scope,
        doc_types=payload.doc_types,
        limit=payload.limit if payload.limit is not None else payload.top_k,
        top_k=payload.top_k,
        filters=payload.filters,
        applied_filters={},
        results=[],
        evidence=[] if payload.as_evidence else [],
    )


def default_nexus_web_search_payload(payload: NexusWebSearchRequest) -> dict[str, Any]:
    search = {
        "items": [],
        "total_items": 0,
        "provider": None,
        "selected_provider": None,
        "attempted_providers": [],
        "fallback_used": False,
        "skipped_providers": {},
        "provider_errors": {"unknown": ["nexus web.search provider unavailable"]},
        "configured": False,
        "non_fatal": True,
        "message": "nexus web.search provider unavailable",
    }
    return _unavailable(
        "web.search",
        job_id=None,
        operation="web.search",
        request=payload.model_dump(),
        result={
            "job_id": None,
            "queries": [],
            "generated_queries": [],
            "effective_query_plan": {},
            "provider": None,
            "selected_provider": None,
            "attempted_providers": [],
            "fallback_used": False,
            "skipped_providers": {},
            "provider_errors": search["provider_errors"],
            "configured": False,
            "non_fatal": True,
            "message": search["message"],
            "saved_evidence": 0,
            "search": search,
            "items": [],
            "total_items": 0,
        },
    )


def default_nexus_web_research_payload(payload: NexusWebSearchRequest) -> dict[str, Any]:
    return _unavailable(
        "web.research",
        job_id=None,
        operation="web.research",
        request=payload.model_dump(),
        result={"job_id": None, "summary": "", "status": "unavailable"},
    )


def default_nexus_research_payload(payload: NexusResearchRunRequest) -> dict[str, Any]:
    return _unavailable("research", job_id=None, status="unavailable")


def default_nexus_deep_research_payload(payload: NexusResearchRunRequest) -> dict[str, Any]:
    return _unavailable("deep research", job_id=None, status="unavailable")


def default_nexus_recursive_research_payload(payload: NexusResearchRunRequest) -> dict[str, Any]:
    return _unavailable("recursive research", job_id=None, status="unavailable")


def default_nexus_sources_search_payload(payload: NexusSourceSearchRequest) -> dict[str, Any]:
    return _unavailable(
        "sources search",
        query=payload.query,
        scope=payload.scope,
        collapse_duplicates=payload.collapse_duplicates,
        results=[],
    )


def default_nexus_evidence_add_from_chunks_payload(payload: NexusEvidenceAddFromChunksRequest) -> dict[str, Any]:
    return _unavailable("evidence add-from-chunks", job_id=payload.job_id, added=0)


def default_nexus_research_followup_payload(job_id: str, payload: NexusResearchFollowupRequest) -> dict[str, Any]:
    return _unavailable(
        "research followup",
        job_id=job_id,
        question=payload.question,
        use_existing_sources_only=True,
        answer="",
        results=[],
    )


def default_nexus_web_collect_payload(payload: NexusCollectRequest) -> dict[str, Any]:
    return _unavailable("web collect", job_id=payload.job_id, sources=[], collected=0)


def default_nexus_ask_payload(payload: NexusSearchRequest) -> dict[str, Any]:
    return _unavailable(
        "ask",
        operation="ask",
        request=payload.model_dump(),
        result={"answer": "", "applied_filters": {}, "results": [], "evidence": []},
    )


def default_nexus_report_build_payload(payload: BuildReportRequest) -> dict[str, Any]:
    return _unavailable(
        "report build",
        job_id=payload.job_id,
        report_id=None,
        report_type=payload.report_type,
        title=payload.title,
        markdown_path="",
        json_path="",
        html_path="",
        report_md_path="",
        report_json_path="",
        report_html_path="",
    )


def _provider(request: Request, name: str, fallback: Callable[..., Any]) -> Callable[..., Any]:
    provider = getattr(request.app.state, name, None)
    if callable(provider):
        return provider
    return fallback


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


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


@router.post("/nexus/upload")
async def nexus_upload_api(request: Request, file: UploadFile = File(...), project: str = Form("default")) -> Any:
    provider = _provider(request, "nexus_upload_provider", default_nexus_upload_payload)
    return await _maybe_await(provider(file=file, project=project))


@router.post("/nexus/search")
def nexus_search_api(request: Request, payload: NexusSearchRequest) -> Any:
    provider = _provider(request, "nexus_search_provider", default_nexus_search_payload)
    return provider(payload)


@router.post("/nexus/web/search")
def nexus_web_search_api(request: Request, payload: NexusWebSearchRequest) -> Any:
    provider = _provider(request, "nexus_web_search_provider", default_nexus_web_search_payload)
    return provider(payload)


@router.post("/nexus/web/research")
def nexus_web_research_api(request: Request, payload: NexusWebSearchRequest) -> Any:
    provider = _provider(request, "nexus_web_research_provider", default_nexus_web_research_payload)
    return provider(payload)


@router.post("/nexus/research/run")
def nexus_research_run_api(request: Request, payload: NexusResearchRunRequest) -> Any:
    mode = str(payload.mode or "").strip().lower()
    depth = str(payload.depth or "").strip().lower()
    if payload.recursive_search:
        provider_name = "nexus_recursive_research_provider"
        provider = _provider(request, provider_name, default_nexus_recursive_research_payload)
    elif mode == "deep" or depth == "deep":
        provider_name = "nexus_deep_research_provider"
        provider = _provider(request, provider_name, default_nexus_deep_research_payload)
    else:
        provider_name = "nexus_research_provider"
        provider = _provider(request, provider_name, default_nexus_research_payload)
    try:
        return provider(payload)
    except Exception as exc:  # noqa: BLE001
        print(f"[NexusResearch] /nexus/research/run failed provider={provider_name} error={exc!r}")
        print(traceback.format_exc())
        request_payload = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
        return {
            "ok": False,
            "status": "error",
            "error": "nexus_research_run_failed",
            "provider": provider_name,
            "message": str(exc),
            "request": request_payload,
        }


@router.post("/nexus/sources/search")
def nexus_sources_search_api(request: Request, payload: NexusSourceSearchRequest) -> Any:
    provider = _provider(request, "nexus_sources_search_provider", default_nexus_sources_search_payload)
    return provider(payload)


@router.post("/nexus/evidence/add-from-chunks")
def nexus_evidence_add_from_chunks_api(request: Request, payload: NexusEvidenceAddFromChunksRequest) -> Any:
    provider = _provider(
        request,
        "nexus_evidence_add_from_chunks_provider",
        default_nexus_evidence_add_from_chunks_payload,
    )
    return provider(payload)


@router.post("/nexus/research/jobs/{job_id}/followup")
def nexus_research_followup_api(request: Request, job_id: str, payload: NexusResearchFollowupRequest) -> Any:
    provider = _provider(request, "nexus_research_followup_provider", default_nexus_research_followup_payload)
    return provider(job_id, payload)


@router.post("/nexus/web/collect")
def nexus_web_collect_api(request: Request, payload: NexusCollectRequest) -> Any:
    provider = _provider(request, "nexus_web_collect_provider", default_nexus_web_collect_payload)
    return provider(payload)


@router.post("/nexus/ask")
def nexus_ask_api(request: Request, payload: NexusSearchRequest) -> Any:
    provider = _provider(request, "nexus_ask_provider", default_nexus_ask_payload)
    return provider(payload)


@router.post("/nexus/report/build")
def nexus_report_build_api(request: Request, payload: BuildReportRequest) -> Any:
    provider = _provider(request, "nexus_report_build_provider", default_nexus_report_build_payload)
    return provider(payload)
