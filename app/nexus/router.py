from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from urllib import parse, request

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.nexus.db import get_conn
from app.nexus.config import load_runtime_config
from app.nexus.evidence import build_library_evidence, list_evidence_table_items
from app.nexus.export import nexus_export_router
from app.nexus.ingest import accept_upload
from app.nexus.jobs import get_job, get_job_events, list_active_jobs
from app.nexus.market import run_market_mvp
from app.nexus.news import (
    create_watchlist,
    delete_watchlist,
    get_watchlist,
    list_watchlists,
    run_news_mvp,
    update_watchlist,
)
from app.nexus.report import nexus_report_router
from app.nexus.search import search_evidence
from app.nexus.web_scout import plan_web_queries, run_web_search


nexus_router = APIRouter()


class NexusSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    scope: str | list[str] | None = None
    doc_types: list[str] = Field(default_factory=list)
    limit: int | None = Field(default=None, ge=1, le=100)
    filters: dict = Field(default_factory=dict)
    top_k: int | None = Field(default=None, ge=1, le=100)
    as_evidence: bool = False


class NexusNewsMvpRequest(BaseModel):
    topic: str = Field(min_length=1)
    mode: str = Field(default="standard")
    max_results_per_query: int | None = Field(default=None, ge=1, le=20)


class NexusMarketMvpRequest(BaseModel):
    symbol_or_theme: str = Field(min_length=1)
    mode: str = Field(default="standard")
    max_results_per_query: int | None = Field(default=None, ge=1, le=20)


class NexusWatchlistCreateRequest(BaseModel):
    project: str = Field(default="default")
    name: str = Field(min_length=1)
    query: str = Field(min_length=1)
    source_type: str = Field(default="news")
    is_active: bool = True


class NexusWatchlistUpdateRequest(BaseModel):
    project: str = Field(default="default")
    name: str | None = None
    query: str | None = None
    source_type: str | None = None
    is_active: bool | None = None
    last_checked_at: str | None = None


class NexusWebSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    mode: str = Field(default="standard")
    depth: str | None = None
    max_queries: int | None = Field(default=None, ge=1, le=20)
    max_results_per_query: int | None = Field(default=None, ge=1, le=20)
    scope: str | list[str] | None = None
    language: str | None = None


def _as_canonical_payload(operation: str, request: dict, result: dict) -> dict:
    return {
        "ok": True,
        "operation": operation,
        "request": request,
        "result": result,
    }


def _with_item_provider_engine(search: dict) -> list[dict]:
    selected_provider = str(search.get("selected_provider") or search.get("provider") or "unknown")
    normalized_items: list[dict] = []
    for item in (search.get("items") or []):
        row = dict(item)
        row["provider"] = str(row.get("provider") or selected_provider)
        row["engine"] = str(row.get("engine") or row.get("provider") or "unknown")
        normalized_items.append(row)
    return normalized_items


def _provider_kind(provider: str) -> str:
    normalized = (provider or "").strip().lower()
    if normalized == "searxng":
        return "free_self_hosted"
    return "paid_or_quota_api"


def _is_provider_enabled(provider: str, cfg) -> bool:
    normalized = (provider or "").strip().lower()
    if normalized == "brave" and cfg.search_free_only and not cfg.search_paid_providers_enabled:
        return False
    return True


def _is_provider_configured(provider: str, cfg) -> tuple[bool, str]:
    normalized = (provider or "").strip().lower()
    if normalized == "brave":
        has_key = bool(cfg.brave_search_api_key)
        if not has_key:
            return False, "BRAVE_SEARCH_API_KEY が未設定です。"
        return True, "設定済みです。"
    if normalized == "searxng":
        if not cfg.searxng_url.strip():
            return False, "NEXUS_SEARXNG_URL が未設定です。"
        return True, "設定済みです。"
    return False, "未対応プロバイダです。"


def _check_searxng_connectivity(url: str) -> tuple[bool, str]:
    base_url = (url or "").strip().rstrip("/")
    if not base_url:
        return False, "NEXUS_SEARXNG_URL が未設定のため疎通確認をスキップしました。"

    params = parse.urlencode({"q": "healthcheck", "format": "json"})
    req = request.Request(
        f"{base_url}/search?{params}",
        headers={"Accept": "application/json"},
        method="GET",
    )
    try:
        with request.urlopen(req, timeout=2) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            if isinstance(payload.get("results"), list):
                return True, "SearXNG 疎通確認に成功しました。"
            return False, "SearXNG から想定外レスポンスを受信しました。"
    except Exception as exc:  # noqa: BLE001
        return False, f"SearXNG 疎通確認に失敗しました: {exc}"


def _resolve_searxng_state(autostart_status: str, probe_ok: bool) -> tuple[str, str]:
    normalized = (autostart_status or "").strip().lower()
    if normalized in {"not_requested", "disabled"}:
        return "autostart_disabled", "SearXNG auto-start is disabled. Set AUTO_START_SEARXNG=true."
    if normalized == "failed_runtime_missing":
        return "runtime_missing", "SearXNG runtime is not installed in this image."
    if probe_ok:
        return "connected", "SearXNG is connected."
    if normalized in {"ready", "ready_existing", "started_unverified"}:
        return "disconnected", "Check log: /workspace/ca_data/searxng/searxng.log"
    if normalized.startswith("failed_"):
        return "disconnected", "Check log: /workspace/ca_data/searxng/searxng.log"
    return "starting", "SearXNG is starting."


@nexus_router.get("/health")
def nexus_health() -> dict[str, str]:
    """Nexus ルーターの疎通確認用エンドポイント。"""
    return {"status": "ok"}


@nexus_router.get("/summary")
@nexus_router.get("/dashboard/summary")
def nexus_summary(project: str = Query("default")) -> dict:
    """Dashboardカード表示向けのサマリー。"""
    with get_conn() as conn:
        docs_row = conn.execute(
            "SELECT COUNT(*) AS c FROM nexus_documents WHERE project = ?",
            (project,),
        ).fetchone()
        chunks_row = conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM nexus_chunks c
            JOIN nexus_documents d ON d.id = c.document_id
            WHERE d.project = ?
            """,
            (project,),
        ).fetchone()
        reports_row = conn.execute(
            "SELECT COUNT(*) AS c FROM nexus_reports WHERE project = ?",
            (project,),
        ).fetchone()

    active_jobs = sum(1 for job in list_active_jobs(limit=500) if job.status in ("queued", "running"))
    cfg = load_runtime_config()
    return {
        "documents": int(docs_row["c"] if docs_row else 0),
        "chunks": int(chunks_row["c"] if chunks_row else 0),
        "reports": int(reports_row["c"] if reports_row else 0),
        "active_jobs": active_jobs,
        "limits": {
            "max_upload_mb": cfg.max_upload_mb,
            "max_upload_bytes": cfg.max_upload_mb * 1024 * 1024,
        },
    }


@nexus_router.get("/documents")
@nexus_router.get("/library/documents")
def nexus_list_documents(
    project: str = Query("default"),
    q: str = Query(""),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    """Library文書一覧（検索つき）。"""
    keyword = q.strip().lower()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT d.id, d.project, d.filename, d.size, d.content_type, d.path, d.extracted_text_path,
                   d.markdown_path, d.sha256, d.created_at,
                   COALESCE(COUNT(c.chunk_id), 0) AS chunk_count
            FROM nexus_documents d
            LEFT JOIN nexus_chunks c ON c.document_id = d.id
            WHERE d.project = ?
            GROUP BY d.id
            ORDER BY d.created_at DESC
            LIMIT ?
            """,
            (project, limit),
        ).fetchall()

    documents: list[dict] = []
    for row in rows:
        filename = str(row["filename"] or "")
        if keyword and keyword not in filename.lower():
            continue
        documents.append(
            {
                "id": row["id"],
                "project": row["project"],
                "filename": filename,
                "size": int(row["size"] or 0),
                "content_type": row["content_type"],
                "created_at": row["created_at"],
                "chunk_count": int(row["chunk_count"] or 0),
                "extracted_text_path": str(row["extracted_text_path"] or ""),
                "markdown_path": str(row["markdown_path"] or ""),
                "has_extracted_text": bool(row["extracted_text_path"]),
                "has_markdown": bool(row["markdown_path"]),
            }
        )
    return {"documents": documents}


@nexus_router.get("/documents/{document_id}")
def nexus_get_document(document_id: str, project: str = Query("default")) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT d.id, d.project, d.filename, d.size, d.content_type, d.created_at,
                   d.extracted_text_path, d.markdown_path,
                   COALESCE(COUNT(c.chunk_id), 0) AS chunk_count
            FROM nexus_documents d
            LEFT JOIN nexus_chunks c ON c.document_id = d.id
            WHERE d.id = ? AND d.project = ?
            GROUP BY d.id
            """,
            (document_id, project),
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="document not found")

    return {
        "document": {
            "id": row["id"],
            "project": row["project"],
            "filename": str(row["filename"] or ""),
            "size": int(row["size"] or 0),
            "content_type": row["content_type"],
            "created_at": row["created_at"],
            "chunk_count": int(row["chunk_count"] or 0),
            "extracted_text_path": str(row["extracted_text_path"] or ""),
            "markdown_path": str(row["markdown_path"] or ""),
            "has_extracted_text": bool(row["extracted_text_path"]),
            "has_markdown": bool(row["markdown_path"]),
        }
    }


@nexus_router.delete("/documents/{document_id}")
@nexus_router.delete("/library/documents/{document_id}")
def nexus_delete_document(document_id: str, project: str = Query("default")) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, path, extracted_text_path, markdown_path FROM nexus_documents WHERE id = ? AND project = ?",
            (document_id, project),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="document not found")

        conn.execute("DELETE FROM nexus_documents WHERE id = ?", (document_id,))
        conn.commit()

    path = Path(str(row["path"]))
    raw_extracted_text_path = str(row["extracted_text_path"] or "").strip()
    raw_markdown_path = str(row["markdown_path"] or "").strip()
    try:
        if path.exists():
            path.unlink()
        parent = path.parent
        if parent.exists() and parent.name == document_id:
            parent.rmdir()
        if raw_extracted_text_path and Path(raw_extracted_text_path).exists():
            extracted_text_path = Path(raw_extracted_text_path)
            extracted_text_path.unlink()
        if raw_markdown_path and Path(raw_markdown_path).exists():
            markdown_path = Path(raw_markdown_path)
            markdown_path.unlink()
        if raw_extracted_text_path:
            extracted_parent = Path(raw_extracted_text_path).parent
            if extracted_parent.exists() and extracted_parent.name == document_id:
                for child in extracted_parent.iterdir():
                    if child.is_dir():
                        try:
                            child.rmdir()
                        except OSError:
                            pass
                extracted_parent.rmdir()
    except OSError:
        # DB削除を優先し、ファイル削除失敗は非致命扱い
        pass

    return {"ok": True, "document_id": document_id}


@nexus_router.get("/library/documents/{document_id}/download")
def nexus_download_document(document_id: str, project: str = Query("default")) -> FileResponse:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT filename, path FROM nexus_documents WHERE id = ? AND project = ?",
            (document_id, project),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="document not found")

    path = Path(str(row["path"]))
    if not path.exists():
        raise HTTPException(status_code=404, detail="file missing")

    return FileResponse(path, filename=str(row["filename"]))


@nexus_router.get("/library/documents/{document_id}/download/text")
def nexus_download_extracted_text(document_id: str, project: str = Query("default")) -> FileResponse:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT extracted_text_path FROM nexus_documents WHERE id = ? AND project = ?",
            (document_id, project),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="document not found")

    raw_path = str(row["extracted_text_path"] or "").strip()
    if not raw_path:
        raise HTTPException(status_code=404, detail="extracted text not ready")
    path = Path(raw_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="extracted text missing")

    return FileResponse(path, filename=f"{document_id}.txt")


@nexus_router.get("/library/documents/{document_id}/download/markdown")
def nexus_download_extracted_markdown(document_id: str, project: str = Query("default")) -> FileResponse:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT markdown_path FROM nexus_documents WHERE id = ? AND project = ?",
            (document_id, project),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="document not found")

    raw_path = str(row["markdown_path"] or "").strip()
    if not raw_path:
        raise HTTPException(status_code=404, detail="markdown not ready")
    path = Path(raw_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="markdown missing")

    return FileResponse(path, filename=f"{document_id}.md")


@nexus_router.get("/jobs/active")
def nexus_active_jobs(limit: int = Query(50, ge=1, le=500)) -> dict:
    jobs = [job.model_dump(mode="json") for job in list_active_jobs(limit=limit)]
    return {"jobs": jobs}


@nexus_router.get("/jobs/{job_id}")
def nexus_job_status(job_id: str) -> dict:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return {"job": job.model_dump(mode="json")}


@nexus_router.get("/jobs/{job_id}/events")
def nexus_job_events(job_id: str, after: int = Query(-1)) -> dict:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")

    events = [event.model_dump(mode="json") for event in get_job_events(job_id, after=after)]
    return {"job_id": job_id, "events": events}


@nexus_router.get("/evidence")
def nexus_list_evidence(
    job_id: str = Query(..., min_length=1),
    source_type: str | None = Query(default=None),
    filter: str | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    """UI テーブルへ直接バインド可能な Evidence 一覧。"""
    return list_evidence_table_items(
        job_id=job_id,
        source_type=source_type,
        filter_text=filter,
        limit=limit,
    )


@nexus_router.post("/upload")
async def nexus_upload(file: UploadFile = File(...), project: str = Form("default")) -> dict:
    """アップロードを受け付け、抽出ジョブをバックグラウンドで開始する。"""
    try:
        return await accept_upload(file=file, project=project)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@nexus_router.post("/search")
def nexus_search(payload: NexusSearchRequest) -> dict:
    """FTS5 + BM25 でライブラリ内チャンクを検索する。"""
    query = payload.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="query must not be empty")

    limit = payload.limit if payload.limit is not None else (payload.top_k if payload.top_k is not None else 10)
    results, applied_filters = search_evidence(
        query=query,
        limit=limit,
        scope=payload.scope,
        doc_types=payload.doc_types,
        filters=payload.filters,
    )
    response: dict = {
        "query": query,
        "scope": payload.scope,
        "doc_types": payload.doc_types,
        "limit": limit,
        "top_k": payload.top_k,
        "filters": payload.filters,
        "applied_filters": applied_filters,
        "results": results,
    }
    if payload.as_evidence:
        response["evidence"] = [asdict(item) for item in build_library_evidence(results)]
    return response


@nexus_router.post("/web/search")
def nexus_web_search(payload: NexusWebSearchRequest) -> dict:
    query = payload.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="query must not be empty")
    requested_depth = (payload.depth or payload.mode or "standard").strip() or "standard"
    queries = plan_web_queries(
        query,
        mode=payload.mode,
        depth=requested_depth,
        max_queries=payload.max_queries,
        scope=payload.scope,
        language=payload.language,
    )
    search = run_web_search(
        queries,
        mode=payload.mode,
        depth=requested_depth,
        max_results_per_query=payload.max_results_per_query,
        scope=payload.scope,
        language=payload.language,
    )
    items = _with_item_provider_engine(search)
    search["items"] = items
    search["total_items"] = int(search.get("total_items") or len(items))
    return _as_canonical_payload(
        "web.search",
        payload.model_dump(),
        {
            "queries": queries,
            "generated_queries": search.get("generated_queries", queries),
            "effective_query_plan": search.get("effective_query_plan", {}),
            "provider": search.get("provider"),
            "selected_provider": search.get("selected_provider"),
            "attempted_providers": search.get("attempted_providers", []),
            "fallback_used": bool(search.get("fallback_used", False)),
            "skipped_providers": search.get("skipped_providers", {}),
            "provider_errors": search.get("provider_errors", {}),
            "configured": bool(search.get("configured", False)),
            "non_fatal": bool(search.get("non_fatal", False)),
            "message": search.get("message", ""),
            "search": search,
            "items": items,
            "total_items": search.get("total_items", len(items)),
        },
    )


@nexus_router.get("/web/status")
def nexus_web_status() -> dict:
    cfg = load_runtime_config()
    providers: list[str] = []
    for provider_name in [cfg.web_search_provider, *cfg.search_fallback_providers]:
        normalized = (provider_name or "").strip().lower()
        if normalized and normalized not in providers:
            providers.append(normalized)

    active_provider = providers[0] if providers else (cfg.web_search_provider or "").strip().lower()

    runpod_searxng_autostart_status = os.getenv("RUNPOD_SEARXNG_AUTOSTART_STATUS", "")
    runpod_searxng_autostart_hint = os.getenv("RUNPOD_SEARXNG_AUTOSTART_HINT", "")
    searxng_configured = bool(cfg.searxng_url.strip())
    searxng_probe_ok = True
    searxng_probe_message = "SearXNG 疎通確認をスキップしました。"
    if searxng_configured:
        searxng_probe_ok, searxng_probe_message = _check_searxng_connectivity(cfg.searxng_url)
    searxng_state, searxng_state_message = _resolve_searxng_state(runpod_searxng_autostart_status, searxng_probe_ok)

    provider_status: dict[str, dict[str, str | bool]] = {}
    for provider_name in providers:
        enabled = _is_provider_enabled(provider_name, cfg)
        provider_configured, provider_message = _is_provider_configured(provider_name, cfg)
        configured = provider_configured
        message_parts = [provider_message]
        if provider_name == "searxng":
            configured = configured and searxng_probe_ok
            message_parts = [searxng_state_message, searxng_probe_message]
        if not enabled:
            message_parts.append("free-only 設定のため有償/クォータ制プロバイダは無効です。")
        provider_status[provider_name] = {
            "kind": _provider_kind(provider_name),
            "enabled": enabled,
            "configured": configured,
            "message": " ".join(part for part in message_parts if part),
        }

    active_provider_status = provider_status.get(
        active_provider,
        {
            "kind": _provider_kind(active_provider),
            "enabled": _is_provider_enabled(active_provider, cfg),
            "configured": False,
            "message": "プロバイダ状態を取得できませんでした。",
        },
    )

    status_message = str(active_provider_status.get("message", ""))
    if active_provider == "searxng":
        status_message = searxng_state_message
    status_non_fatal = not bool(active_provider_status.get("configured", False))
    status_provider_errors: dict[str, list[str]] = {}
    if status_non_fatal:
        status_provider_errors[active_provider or "unknown"] = [status_message or "provider unavailable"]

    return {
        "enable_web": cfg.enable_web,
        "provider": cfg.web_search_provider,
        "fallback_providers": list(cfg.search_fallback_providers),
        "free_only": cfg.search_free_only,
        "paid_providers_enabled": cfg.search_paid_providers_enabled,
        "brave_search_api_key_set": bool(cfg.brave_search_api_key),
        "searxng_url": cfg.searxng_url,
        "searxng_configured": searxng_configured,
        "configured": bool(active_provider_status.get("configured", False)),
        "active_provider": active_provider,
        "provider_status": provider_status,
        "provider_status_active": active_provider_status,
        "message": status_message,
        "searxng_state": searxng_state,
        "searxng_state_message": searxng_state_message,
        "non_fatal": status_non_fatal,
        "stub": status_non_fatal,
        "provider_errors": status_provider_errors,
        "runpod_searxng_autostart_status": runpod_searxng_autostart_status,
        "runpod_searxng_autostart_hint": runpod_searxng_autostart_hint,
    }


@nexus_router.post("/web/research")
def nexus_web_research(payload: NexusWebSearchRequest) -> dict:
    query = payload.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="query must not be empty")
    requested_depth = (payload.depth or payload.mode or "standard").strip() or "standard"
    queries = plan_web_queries(
        query,
        mode=payload.mode,
        depth=requested_depth,
        max_queries=payload.max_queries,
        scope=payload.scope,
        language=payload.language,
    )
    search = run_web_search(
        queries,
        mode=payload.mode,
        depth=requested_depth,
        max_results_per_query=payload.max_results_per_query,
        scope=payload.scope,
        language=payload.language,
    )
    items = _with_item_provider_engine(search)
    search["items"] = items
    search["total_items"] = int(search.get("total_items") or len(items))
    highlights = [str(item.get("title") or item.get("snippet") or "") for item in items[:5]]
    return _as_canonical_payload(
        "web.research",
        payload.model_dump(),
        {
            "queries": queries,
            "generated_queries": search.get("generated_queries", queries),
            "effective_query_plan": search.get("effective_query_plan", {}),
            "provider": search.get("provider"),
            "selected_provider": search.get("selected_provider"),
            "attempted_providers": search.get("attempted_providers", []),
            "fallback_used": bool(search.get("fallback_used", False)),
            "skipped_providers": search.get("skipped_providers", {}),
            "provider_errors": search.get("provider_errors", {}),
            "configured": bool(search.get("configured", False)),
            "non_fatal": bool(search.get("non_fatal", False)),
            "message": search.get("message", ""),
            "search": search,
            "items": items,
            "total_items": search.get("total_items", len(items)),
            "highlights": highlights,
            "summary": f"{query} に関するWeb調査（MVP）",
        },
    )


@nexus_router.post("/news/search")
@nexus_router.post("/news/scan")
@nexus_router.post("/news/mvp")
def nexus_news_mvp(payload: NexusNewsMvpRequest) -> dict:
    try:
        legacy = run_news_mvp(
            topic=payload.topic,
            mode=payload.mode,
            max_results_per_query=payload.max_results_per_query,
        )
        return _as_canonical_payload("news.search", payload.model_dump(), legacy)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@nexus_router.post("/market/research")
@nexus_router.post("/market/compare")
@nexus_router.post("/market/mvp")
def nexus_market_mvp(payload: NexusMarketMvpRequest) -> dict:
    try:
        legacy = run_market_mvp(
            symbol_or_theme=payload.symbol_or_theme,
            mode=payload.mode,
            max_results_per_query=payload.max_results_per_query,
        )
        return _as_canonical_payload("market.research", payload.model_dump(), legacy)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@nexus_router.post("/ask")
def nexus_ask(payload: NexusSearchRequest) -> dict:
    query = payload.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="query must not be empty")
    limit = payload.limit if payload.limit is not None else (payload.top_k if payload.top_k is not None else 10)
    results, applied_filters = search_evidence(
        query=query,
        limit=limit,
        scope=payload.scope,
        doc_types=payload.doc_types,
        filters=payload.filters,
    )
    top = results[0] if results else None
    answer = (
        f"上位候補: {top.get('chunk', {}).get('title')}" if top else "該当する候補が見つかりませんでした。"
    )
    return _as_canonical_payload(
        "ask",
        payload.model_dump(),
        {
            "answer": answer,
            "applied_filters": applied_filters,
            "results": results,
            "evidence": [asdict(item) for item in build_library_evidence(results)] if payload.as_evidence else [],
        },
    )


@nexus_router.get("/news/watchlists")
def nexus_list_watchlists(
    project: str = Query("default"),
    include_inactive: bool = Query(True),
) -> dict:
    return {
        "watchlists": list_watchlists(project=project, include_inactive=include_inactive),
    }


@nexus_router.get("/news/watchlists/{watchlist_id}")
def nexus_get_watchlist(watchlist_id: str, project: str = Query("default")) -> dict:
    row = get_watchlist(watchlist_id, project=project)
    if row is None:
        raise HTTPException(status_code=404, detail="watchlist not found")
    return {"watchlist": row}


@nexus_router.post("/news/watchlists")
def nexus_create_watchlist(payload: NexusWatchlistCreateRequest) -> dict:
    try:
        return {"watchlist": create_watchlist(**payload.model_dump())}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@nexus_router.patch("/news/watchlists/{watchlist_id}")
def nexus_update_watchlist(watchlist_id: str, payload: NexusWatchlistUpdateRequest) -> dict:
    try:
        row = update_watchlist(watchlist_id, **payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="watchlist not found")
    return {"watchlist": row}


@nexus_router.delete("/news/watchlists/{watchlist_id}")
def nexus_delete_watchlist(watchlist_id: str, project: str = Query("default")) -> dict:
    deleted = delete_watchlist(watchlist_id, project=project)
    if not deleted:
        raise HTTPException(status_code=404, detail="watchlist not found")
    return {"ok": True, "watchlist_id": watchlist_id}


# 既存インポート互換
router = nexus_router

nexus_router.include_router(nexus_report_router)
nexus_router.include_router(nexus_export_router)
