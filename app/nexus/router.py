from __future__ import annotations

import json
import os
from pathlib import Path
from urllib import parse, request

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.nexus.db import get_conn
from app.nexus.config import load_runtime_config
from app.nexus.evidence import search_evidence_items
from app.nexus.export import nexus_export_router
from app.nexus.ingest import accept_upload
from app.nexus.jobs import list_active_jobs
from app.nexus.market import run_market_mvp
from app.nexus.news import (
    create_watchlist,
    delete_watchlist,
    get_watchlist,
    list_watchlists,
    run_news_mvp,
    update_watchlist,
)
from app.nexus.report import BuildReportRequest, build_job_report, nexus_report_router
from app.nexus.search import search_evidence
from app.nexus.web_scout import get_last_web_search_status
from app.nexus.web_service import execute_web_search_service
from app.services.nexus_execution import (
    NexusExecutionError,
    add_nexus_evidence_from_chunks_service,
    build_nexus_report_service,
    collect_nexus_web_sources_service,
    ingest_nexus_document_service,
    run_nexus_ask_service,
    run_nexus_research_followup_service,
    run_nexus_research_service,
    run_nexus_deep_research_service,
    run_nexus_recursive_research_service,
    run_nexus_search_service,
    run_nexus_sources_search_service,
    run_nexus_web_research_service,
    run_nexus_web_search_service,
)
from app.nexus.research_api import (
    CollectRequest,
    ResearchRunRequest,
    collect_web_sources,
    get_research_job,
    get_research_job_bundle,
    get_research_job_debug,
    get_research_job_answer,
    get_research_job_events,
    get_research_job_evidence,
    get_research_job_sources,
    get_source,
    get_source_chunks,
    get_source_markdown,
    get_source_original,
    get_source_text,
    run_research_async,
)


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
        status = getattr(exc, "code", None)
        if status == 403:
            return False, "SearXNG は起動していますが JSON API が無効です。settings.yml の search.formats に json を追加してコンテナを再起動してください。"
        return False, f"SearXNG 疎通確認に失敗しました: {exc}"


def _resolve_searxng_state(autostart_status: str, probe_ok: bool) -> tuple[str, str]:
    normalized = (autostart_status or "").strip().lower()
    searx_log = os.getenv("CODEAGENT_SEARXNG_LOG_FILE", "/workspace/ca_data/searxng/searxng.log")
    windows_hint = (
        " Windowsでは SearXNG は Docker コンテナ codeagent-searxng で起動します。Docker Desktop を起動し、start.bat を再実行してください。ログ: ca_data/searxng/searxng.log"
        if os.name == "nt"
        else ""
    )
    if normalized in {"not_requested", "disabled"}:
        return "autostart_disabled", "SearXNG auto-start is disabled. Set AUTO_START_SEARXNG=true."
    if normalized == "failed_runtime_missing":
        return "runtime_missing", "SearXNG runtime is not installed in this image."
    if probe_ok:
        return "connected", "SearXNG is connected."
    if normalized in {"ready", "ready_existing", "started_unverified"}:
        return "disconnected", f"Check log: {searx_log}.{windows_hint}"
    if normalized.startswith("failed_"):
        return "disconnected", f"Check log: {searx_log}.{windows_hint}"
    return "starting", "SearXNG is starting."


@nexus_router.get("/health")
def nexus_health() -> dict[str, str]:
    """Nexus ルーターの疎通確認用エンドポイント。"""
    return {"status": "ok"}


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


@nexus_router.get("/jobs/{job_id}")
def nexus_job_status(job_id: str) -> dict:
    return {"job": get_research_job(job_id)["job"]}


@nexus_router.get("/jobs/{job_id}/events")
def nexus_job_events(job_id: str, after: int = Query(-1)) -> dict:
    return get_research_job_events(job_id, after=after)


@nexus_router.get("/evidence")
def nexus_list_evidence(
    project: str = Query("default"),
    job_id: str | None = Query(default=None),
    source_type: str | None = Query(default=None),
    filter: str | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    """UI テーブルへ直接バインド可能な Evidence 一覧。"""
    return search_evidence_items(
        project=project,
        job_id=job_id,
        source_type=source_type,
        filter_text=filter,
        limit=limit,
    )


async def nexus_upload_payload(*, file, project: str = "default") -> dict:
    """アップロードを受け付け、抽出ジョブをバックグラウンドで開始する。"""
    try:
        return await ingest_nexus_document_service(file=file, project=project, accept_upload=accept_upload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def nexus_search_payload(payload: NexusSearchRequest) -> dict:
    """FTS5 + BM25 でライブラリ内チャンクを検索する。"""
    try:
        return run_nexus_search_service(payload, search_evidence=search_evidence)
    except NexusExecutionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


def nexus_web_search_payload(payload: NexusWebSearchRequest) -> dict:
    try:
        return run_nexus_web_search_service(payload, execute_web_search=execute_web_search_service)
    except NexusExecutionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


def nexus_web_research_payload(payload: NexusWebSearchRequest) -> dict:
    return run_nexus_web_research_service(payload, run_research_async=run_research_async)


def nexus_research_payload(payload: ResearchRunRequest) -> dict:
    return run_nexus_research_service(payload, run_research_async=run_research_async)


def nexus_deep_research_payload(payload: ResearchRunRequest) -> dict:
    return run_nexus_deep_research_service(payload, run_research_async=run_research_async)


def nexus_recursive_research_payload(payload: ResearchRunRequest) -> dict:
    return run_nexus_recursive_research_service(payload, run_research_async=run_research_async)


@nexus_router.get("/research/jobs/{job_id}")
def nexus_research_job(job_id: str) -> dict:
    return get_research_job(job_id)


@nexus_router.get("/research/jobs/{job_id}/events")
def nexus_research_job_events(job_id: str, after: int = Query(-1)) -> dict:
    return get_research_job_events(job_id, after=after)


@nexus_router.get("/research/jobs/{job_id}/answer")
def nexus_research_job_answer(job_id: str) -> dict:
    return get_research_job_answer(job_id)


@nexus_router.get("/research/jobs/{job_id}/sources")
def nexus_research_job_sources(job_id: str) -> dict:
    return get_research_job_sources(job_id)


@nexus_router.get("/research/jobs/{job_id}/evidence")
def nexus_research_job_evidence(job_id: str) -> dict:
    return get_research_job_evidence(job_id)


@nexus_router.get("/research/jobs/{job_id}/bundle")
def nexus_research_job_bundle(job_id: str, after: int = Query(-1)) -> dict:
    return get_research_job_bundle(job_id, after=after)


@nexus_router.get("/research/jobs/{job_id}/debug")
def nexus_research_job_debug(job_id: str) -> dict:
    return get_research_job_debug(job_id)


@nexus_router.get("/sources/{source_id}")
def nexus_source(source_id: str) -> dict:
    return get_source(source_id)


@nexus_router.get("/sources/{source_id}/text")
def nexus_source_text(source_id: str) -> FileResponse:
    return get_source_text(source_id)


@nexus_router.get("/sources/{source_id}/markdown")
def nexus_source_markdown(source_id: str) -> FileResponse:
    return get_source_markdown(source_id)


@nexus_router.get("/sources/{source_id}/original")
def nexus_source_original(source_id: str) -> FileResponse:
    return get_source_original(source_id)


@nexus_router.get("/sources/{source_id}/chunks")
def nexus_source_chunks(source_id: str) -> dict:
    return get_source_chunks(source_id)


def _search_chunks(payload: NexusSourceSearchRequest) -> list[dict]:
    scope = (payload.scope or "current_research_job").strip().lower()
    where = ["fts.text MATCH ?"]
    params: list[object] = [payload.query.strip()]
    if payload.source_types:
        where.append("LOWER(s.source_type) IN ({})".format(",".join("?" for _ in payload.source_types)))
        params.extend([t.lower() for t in payload.source_types])
    if payload.source_ids:
        where.append("s.source_id IN ({})".format(",".join("?" for _ in payload.source_ids)))
        params.extend(payload.source_ids)
    if scope == "current_research_job":
        if not payload.job_id:
            raise HTTPException(status_code=400, detail="job_id is required for current_research_job")
        where.append("s.job_id = ?")
        params.append(payload.job_id)
    elif scope == "selected_sources":
        if not payload.source_ids:
            raise HTTPException(status_code=400, detail="source_ids is required for selected_sources")
    elif scope == "evidence":
        where.append("EXISTS (SELECT 1 FROM nexus_evidence ev WHERE ev.chunk_id = sc.chunk_id)")
    elif scope == "library":
        where.append("s.linked_document_id IS NOT NULL")
    elif scope != "all_collected_sources":
        raise HTTPException(status_code=400, detail="unsupported scope")
    params.append(payload.limit)
    sql = f"""
        SELECT s.source_id, sc.document_id, sc.chunk_id, s.title,
               COALESCE(s.final_url, s.url, '') AS url, s.source_type,
               sc.page_start, sc.page_end,
               snippet(nexus_chunks_fts, 1, '<b>', '</b>', ' … ', 24) AS snippet,
               COALESCE(sc.citation_label, '[S]') AS citation_label,
               bm25(nexus_chunks_fts) AS score
        FROM nexus_chunks_fts fts
        JOIN nexus_source_chunks sc ON sc.chunk_id = fts.chunk_id
        JOIN nexus_sources s ON s.source_id = sc.source_id
        WHERE {' AND '.join(where)}
        ORDER BY score
        LIMIT ?
    """
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql, tuple(params)).fetchall()]


def nexus_sources_search_payload(payload: NexusSourceSearchRequest) -> dict:
    return run_nexus_sources_search_service(payload, search_chunks=_search_chunks)


def _fetch_chunk_rows_for_evidence(chunk_ids: list[str]) -> list[dict]:
    q_marks = ",".join("?" for _ in chunk_ids)
    sql = f"""
        SELECT sc.chunk_id, sc.document_id, sc.source_id, sc.citation_label, sc.page_start, sc.page_end,
               c.text, c.title AS chunk_title, s.source_type, s.title, COALESCE(s.final_url, s.url, '') AS url,
               COALESCE(s.retrieved_at, s.created_at, '') AS retrieved_at
        FROM nexus_source_chunks sc
        LEFT JOIN nexus_chunks c ON c.chunk_id = sc.chunk_id
        LEFT JOIN nexus_sources s ON s.source_id = sc.source_id
        WHERE sc.chunk_id IN ({q_marks})
    """
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql, tuple(chunk_ids)).fetchall()]


def nexus_evidence_add_from_chunks_payload(payload: NexusEvidenceAddFromChunksRequest) -> dict:
    return add_nexus_evidence_from_chunks_service(payload, fetch_chunk_rows=_fetch_chunk_rows_for_evidence)


def nexus_research_followup_payload(job_id: str, payload: NexusResearchFollowupRequest) -> dict:
    return run_nexus_research_followup_service(
        job_id,
        payload,
        search_chunks=_search_chunks,
        source_search_request_factory=NexusSourceSearchRequest,
    )


def nexus_web_collect_payload(payload: CollectRequest) -> dict:
    return collect_nexus_web_sources_service(payload, collect_web_sources=collect_web_sources)


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


def nexus_ask_payload(payload: NexusSearchRequest) -> dict:
    try:
        return run_nexus_ask_service(payload, search_evidence=search_evidence)
    except NexusExecutionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


def nexus_report_build_payload(payload: BuildReportRequest) -> dict:
    return build_nexus_report_service(payload, build_report=build_job_report)


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
