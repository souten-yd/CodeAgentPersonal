from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import threading
import uuid

from fastapi import HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.nexus.config import load_runtime_config
from app.nexus.db import get_conn
from app.nexus.downloader import safe_download, save_download_artifacts
from app.nexus.evidence import list_evidence_items
from app.nexus.jobs import create_job, get_job, get_job_events, update_job
from app.nexus.research_agent import ResearchAgentInput, _download_sources_parallel, run_research_job
from app.nexus.source_collector import collect_source_candidates, rank_source_candidates
from app.nexus.source_registry import register_or_update_sources

TERMINAL_JOB_STATUSES = {"completed", "degraded", "failed", "cancelled"}


def is_terminal_job(job: dict) -> bool:
    return str(job.get("status") or "").lower() in TERMINAL_JOB_STATUSES


class ResearchRunRequest(BaseModel):
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


class CollectRequest(BaseModel):
    job_id: str = Field(min_length=1)
    project: str = Field(default="default")
    search_items: list[dict] = Field(default_factory=list)
    manual_urls: list[str] = Field(default_factory=list)
    max_download_mb: int | None = Field(default=None, ge=1, le=2048)
    max_total_download_mb: int | None = Field(default=None, ge=1, le=2048)
    max_downloads: int | None = Field(default=None, ge=1, le=200)
    download_timeout_sec: int | None = Field(default=None, ge=1, le=600)
    continue_on_download_error: bool = True


def _resolve_max_download_mb(requested_max_download_mb: int | None) -> int:
    if requested_max_download_mb is not None:
        return max(1, requested_max_download_mb)
    runtime_cfg = load_runtime_config()
    return max(1, runtime_cfg.max_download_mb)


def _source_not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="source not found")


def _normalize_source_row(row: dict) -> dict:
    normalized = dict(row)
    try:
        normalized["source_score"] = float(normalized.get("source_score") or 0.0)
    except (TypeError, ValueError):
        normalized["source_score"] = 0.0
    raw_breakdown = normalized.get("source_score_breakdown")
    if isinstance(raw_breakdown, str):
        try:
            parsed = json.loads(raw_breakdown)
        except (TypeError, ValueError):
            parsed = {}
        normalized["source_score_breakdown"] = parsed if isinstance(parsed, dict) else {}
    elif not isinstance(raw_breakdown, dict):
        normalized["source_score_breakdown"] = {}
    return normalized


def run_research(payload: ResearchRunRequest) -> dict:
    query = payload.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="query must not be empty")

    try:
        result = run_research_job(
            ResearchAgentInput(
                query=query,
                project=payload.project,
                mode=payload.mode,
                depth=payload.depth,
                max_queries=payload.max_queries,
                max_results_per_query=payload.max_results_per_query,
                max_sources=payload.max_sources,
                max_downloads=payload.max_downloads,
                max_download_mb=payload.max_download_mb,
                max_total_download_mb=payload.max_total_download_mb,
                scope=payload.scope,
                language=payload.language,
                manual_urls=payload.manual_urls,
                prefer_pdf=payload.prefer_pdf,
                official_first=payload.official_first,
                download_timeout_sec=payload.download_timeout_sec,
                continue_on_download_error=payload.continue_on_download_error,
                recursive_search=payload.recursive_search,
                max_iterations=payload.max_iterations,
                max_followup_queries=payload.max_followup_queries,
                confidence_threshold=payload.confidence_threshold,
                stop_when_sufficient=payload.stop_when_sufficient,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job_id = str(result.get("job_id") or "")
    if is_terminal:
        is_stalled = False
        stalled_reason = ""
        suggested_action = ""

    return {
        "job_id": job_id,
        "job": get_research_job(job_id).get("job"),
        "queries": result.get("queries", []),
        "answer": result.get("answer", {}),
        "sources": result.get("sources", []),
    }


def run_research_async(payload: ResearchRunRequest) -> dict:
    query = payload.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="query must not be empty")

    agent_input = ResearchAgentInput(
        query=query,
        project=payload.project,
        mode=payload.mode,
        depth=payload.depth,
        max_queries=payload.max_queries,
        max_results_per_query=payload.max_results_per_query,
        max_sources=payload.max_sources,
        max_downloads=payload.max_downloads,
        max_download_mb=payload.max_download_mb,
        max_total_download_mb=payload.max_total_download_mb,
        scope=payload.scope,
        language=payload.language,
        manual_urls=payload.manual_urls,
        prefer_pdf=payload.prefer_pdf,
        official_first=payload.official_first,
        download_timeout_sec=payload.download_timeout_sec,
        continue_on_download_error=payload.continue_on_download_error,
        recursive_search=payload.recursive_search,
        max_iterations=payload.max_iterations,
        max_followup_queries=payload.max_followup_queries,
        confidence_threshold=payload.confidence_threshold,
        stop_when_sufficient=payload.stop_when_sufficient,
    )
    job_id = f"research_{uuid.uuid4().hex}"
    existing = get_job(job_id)
    if existing is None:
        create_job(job_id, title=query, message="research queued", status="queued")

    def _worker() -> None:
        try:
            run_research_job(agent_input, job_id=job_id)
        except Exception as exc:  # noqa: BLE001
            update_job(job_id, status="failed", progress=1.0, message="research failed", error=str(exc))

    thread = threading.Thread(target=_worker, name=f"nexus-research-{job_id}", daemon=True)
    thread.start()
    return {"job_id": job_id, "job": get_research_job(job_id).get("job")}


def get_research_job(job_id: str) -> dict:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return {"job_id": job_id, "job": job.model_dump(mode="json")}


def get_research_job_events(job_id: str, after: int = -1) -> dict:
    _ = get_research_job(job_id)
    events = [event.model_dump(mode="json") for event in get_job_events(job_id, after=after)]
    return {"job_id": job_id, "events": events}


def get_research_job_sources(job_id: str) -> dict:
    _ = get_research_job(job_id)
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT source_id, job_id, project, source_type, url, final_url, title, publisher,
                   domain, language, content_type, local_original_path, local_text_path,
                   local_markdown_path, local_screenshot_path, linked_document_id, status,
                   source_score, source_score_breakdown,
                   error, retrieved_at, created_at, updated_at
            FROM nexus_sources
            WHERE job_id = ?
            ORDER BY created_at ASC, source_id ASC
            """,
            (job_id,),
        ).fetchall()

    sources = [_normalize_source_row(dict(row)) for row in rows]
    return {"job_id": job_id, "sources": sources}


def get_research_job_answer(job_id: str) -> dict:
    _ = get_research_job(job_id)
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT answer_id, question, answer_markdown, evidence_json, answer_json, source_ids_json, created_at
            FROM nexus_research_answers
            WHERE job_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (job_id,),
        ).fetchone()
        source_rows = conn.execute(
            """
            SELECT source_id, title, source_type, source_score, status, url, final_url, error
            FROM nexus_sources
            WHERE job_id = ?
            ORDER BY created_at ASC, source_id ASC
            """,
            (job_id,),
        ).fetchall()

    if row is None:
        return {"job_id": job_id, "answer": {}}

    answer_json_raw = str(row["answer_json"] or "").strip()
    if answer_json_raw:
        try:
            parsed_answer_json = json.loads(answer_json_raw)
        except (TypeError, ValueError):
            parsed_answer_json = {}
        if isinstance(parsed_answer_json, dict) and parsed_answer_json:
            answer = dict(parsed_answer_json)
            parsed_refs = answer.get("references")
            if isinstance(parsed_refs, list):
                source_index: dict[str, dict] = {}
                for source_row in source_rows:
                    source = _normalize_source_row(dict(source_row))
                    source_id = str(source.get("source_id") or "").strip()
                    if source_id:
                        source_index[source_id] = source
                enriched_refs: list[dict] = []
                for idx, item in enumerate(parsed_refs, start=1):
                    ref = dict(item) if isinstance(item, dict) else {}
                    source_id = str(ref.get("source_id") or "").strip()
                    source = source_index.get(source_id, {})
                    enriched_refs.append(
                        {
                            "citation_label": str(ref.get("citation_label") or f"[S{idx}]"),
                            "title": str(ref.get("title") or source.get("title") or ""),
                            "source_type": str(ref.get("source_type") or source.get("source_type") or ""),
                            "source_score": ref.get("source_score", source.get("source_score")),
                            "status": str(ref.get("status") or source.get("status") or ""),
                            "url": str(ref.get("url") or source.get("final_url") or source.get("url") or ""),
                            "error": str(ref.get("error") or source.get("error") or ""),
                            "source_id": source_id,
                        }
                    )
                answer["references"] = enriched_refs
            answer.setdefault("answer_id", row["answer_id"])
            answer.setdefault("question", row["question"])
            answer.setdefault("answer_markdown", row["answer_markdown"])
            answer.setdefault("created_at", row["created_at"])
            return {"job_id": job_id, "answer": answer}

    source_index: dict[str, dict] = {}
    for source_row in source_rows:
        source = _normalize_source_row(dict(source_row))
        source_id = str(source.get("source_id") or "").strip()
        if not source_id:
            continue
        source_index[source_id] = source

    evidence = json.loads(row["evidence_json"] or "[]")
    base_references = evidence if isinstance(evidence, list) else []
    references: list[dict] = []
    for idx, item in enumerate(base_references, start=1):
        ref = dict(item) if isinstance(item, dict) else {}
        source_id = str(ref.get("source_id") or "").strip()
        source = source_index.get(source_id, {})
        references.append(
            {
                "citation_label": str(ref.get("citation_label") or f"[S{idx}]"),
                "title": str(ref.get("title") or source.get("title") or ""),
                "source_type": str(ref.get("source_type") or source.get("source_type") or ""),
                "source_score": ref.get("source_score", source.get("source_score")),
                "status": str(ref.get("status") or source.get("status") or ""),
                "url": str(ref.get("url") or source.get("final_url") or source.get("url") or ""),
                "error": str(ref.get("error") or source.get("error") or ""),
                "source_id": source_id,
            }
        )

    answer = {
        "answer_id": row["answer_id"],
        "question": row["question"],
        "answer_markdown": row["answer_markdown"],
        "evidence": evidence if isinstance(evidence, list) else [],
        "references": references,
        "source_ids": json.loads(row["source_ids_json"] or "[]"),
        "created_at": row["created_at"],
    }
    return {"job_id": job_id, "answer": answer}


def get_research_job_evidence(job_id: str) -> dict:
    _ = get_research_job(job_id)
    return {"job_id": job_id, "evidence": list_evidence_items(job_id)}


def get_research_job_bundle(job_id: str, after: int = -1) -> dict:
    base = get_research_job(job_id)
    events = get_research_job_events(job_id, after=after).get("events", [])
    answer = get_research_job_answer(job_id).get("answer", {})
    sources = get_research_job_sources(job_id).get("sources", [])
    evidence = get_research_job_evidence(job_id).get("evidence", [])
    health = _build_research_job_health(base.get("job", {}), events)
    return {
        "job_id": job_id,
        "job": base.get("job", {}),
        "health": health,
        "events": events,
        "answer": answer,
        "sources": sources,
        "evidence": evidence,
    }


def _build_research_job_health(job: dict, events: list[dict]) -> dict:
    status = str(job.get("status") or "").lower()
    phase = str(job.get("message") or "").strip()
    last_event = events[-1] if events else {}
    last_event_type = str(last_event.get("type") or "")
    last_event_at = str(last_event.get("updated_at") or last_event.get("ts") or "")
    last_heartbeat = None
    for ev in reversed(events):
        if str(ev.get("type") or "") == "heartbeat":
            last_heartbeat = ev
            break
    last_heartbeat_at = str((last_heartbeat or {}).get("updated_at") or (last_heartbeat or {}).get("ts") or "")
    now = datetime.now(timezone.utc)
    sec_since_hb = None
    sec_since_event = None
    if last_heartbeat_at:
        try:
            iso = last_heartbeat_at.replace("Z", "+00:00")
            sec_since_hb = max(0.0, (now - datetime.fromisoformat(iso)).total_seconds())
        except ValueError:
            sec_since_hb = None
    if last_event_at:
        try:
            iso = last_event_at.replace("Z", "+00:00")
            sec_since_event = max(0.0, (now - datetime.fromisoformat(iso)).total_seconds())
        except ValueError:
            sec_since_event = None
    stalled_after = float(
        str(
            os.environ.get(
                "NEXUS_STALLED_AFTER_SEC",
                os.environ.get("NEXUS_DOWNLOAD_STALLED_AFTER_SEC", "120"),
            )
        ).strip()
        or "120"
    )
    inferred_phase = str((last_heartbeat or {}).get("data", {}).get("phase") or phase or "").strip()
    if inferred_phase == "download":
        inferred_phase = "downloading"
    current_message = str((last_heartbeat or {}).get("data", {}).get("message") or job.get("message") or "").strip()
    is_terminal = is_terminal_job(job)
    is_active = status == "running" and bool(last_heartbeat_at) and not is_terminal
    progress_events = [ev for ev in events if str(ev.get("type") or "") == "download_progress"]
    last_progress = progress_events[-1] if progress_events else {}
    progress_data = (last_progress.get("data") or {}) if isinstance(last_progress, dict) else {}
    active_downloads = int(progress_data.get("active") or 0)
    completed_downloads = int(progress_data.get("completed") or 0)
    total_downloads = int(progress_data.get("total") or 0)
    degraded_downloads = int(progress_data.get("degraded") or 0)
    failed_downloads = int(progress_data.get("failed") or 0)
    skipped_downloads = int(progress_data.get("skipped") or 0)
    latest_download_progress = progress_data if isinstance(progress_data, dict) else {}
    is_stalled = bool(
        status == "running"
        and not is_terminal
        and sec_since_hb is not None
        and sec_since_hb > stalled_after
    )
    stalled_reason = ""
    suggested_action = ""
    if is_stalled:
        if inferred_phase == "downloading" and active_downloads > 0:
            stalled_reason = "一部URLの応答待ち"
            suggested_action = "ネットワーク到達性・対象URL応答を確認し、数十秒待って heartbeat を再確認してください。"
        elif inferred_phase == "answer_llm_generating":
            stalled_reason = "LLM回答生成heartbeat停止"
            suggested_action = "LLM endpoint / timeout / llama-server logを確認"
        elif inferred_phase == "evidence_compression":
            stalled_reason = "Evidence圧縮処理のheartbeat停止"
            suggested_action = "圧縮対象サイズ・サーバー負荷を確認してください。"
        elif inferred_phase == "source_ingest":
            stalled_reason = "Source登録処理のheartbeat停止"
            suggested_action = "DB書き込みとストレージ状態を確認してください。"
        else:
            stalled_reason = "heartbeat更新停止"
            suggested_action = "サーバーログとジョブ状態を確認してください。"
    return {
        "phase": inferred_phase or phase,
        "current_phase": inferred_phase or phase,
        "current_message": current_message,
        "last_event_type": last_event_type,
        "last_event_at": last_event_at,
        "seconds_since_last_event": sec_since_event,
        "last_heartbeat_at": last_heartbeat_at,
        "seconds_since_last_heartbeat": sec_since_hb,
        "is_active": is_active,
        "is_stalled": is_stalled,
        "latest_download_progress": latest_download_progress,
        "download_completed": completed_downloads,
        "download_total": total_downloads,
        "download_active": active_downloads,
        "download_degraded": degraded_downloads,
        "download_failed": failed_downloads,
        "download_skipped": skipped_downloads,
        "stalled_reason": stalled_reason,
        "suggested_action": suggested_action,
    }


def get_research_job_debug(job_id: str) -> dict:
    base = get_research_job(job_id)
    events = get_research_job_events(job_id, after=-1).get("events", [])
    answer = get_research_job_answer(job_id).get("answer", {})
    sources = get_research_job_sources(job_id).get("sources", [])
    health = _build_research_job_health(base.get("job", {}), events)
    source_total = len(sources)
    source_ingested = sum(1 for row in sources if str(row.get("status") or "") in {"downloaded", "ingested"})
    source_degraded = sum(1 for row in sources if str(row.get("status") or "") in {"degraded", "failed"})
    return {
        "job_id": job_id,
        "job": base.get("job", {}),
        "health": health,
        "latest_events": events[-20:],
        "answer_exists": bool(answer),
        "answer_incomplete": bool(answer.get("output_incomplete") or answer.get("generation", {}).get("output_incomplete")),
        "source_counts": {"total": source_total, "ingested": source_ingested, "degraded": source_degraded},
    }


def collect_web_sources(payload: CollectRequest) -> dict:
    existing = get_job(payload.job_id)
    if existing is None:
        create_job(payload.job_id, title="web.collect", status="running", message="collecting sources")
    else:
        update_job(payload.job_id, status="running", message="collecting sources")

    candidates = collect_source_candidates(
        search_items=payload.search_items,
        manual_urls=payload.manual_urls,
    )
    ranked_candidates = rank_source_candidates(
        candidates,
        prefer_pdf=True,
        official_first=True,
    )
    runtime_cfg = load_runtime_config()
    max_download_mb = _resolve_max_download_mb(payload.max_download_mb)
    max_downloads = payload.max_downloads if payload.max_downloads is not None else runtime_cfg.max_downloads
    max_total_download_mb = (
        payload.max_total_download_mb
        if payload.max_total_download_mb is not None
        else runtime_cfg.max_total_download_mb
    )
    download_timeout_sec = (
        payload.download_timeout_sec
        if payload.download_timeout_sec is not None
        else runtime_cfg.download_timeout_sec
    )
    max_download_bytes = max_download_mb * 1024 * 1024
    max_total_download_bytes = max_total_download_mb * 1024 * 1024
    downloadable_sources, download_error_count = _download_sources_parallel(
        job_id=payload.job_id,
        candidates=ranked_candidates,
        max_downloads=max_downloads,
        max_download_bytes=max_download_bytes,
        max_total_download_bytes=max_total_download_bytes,
        download_timeout_sec=download_timeout_sec,
        continue_on_download_error=payload.continue_on_download_error,
        concurrency=runtime_cfg.download_concurrency,
        pdf_extract_concurrency=runtime_cfg.pdf_extract_concurrency,
        download_progress_interval_sec=runtime_cfg.download_progress_interval_sec,
        download_stalled_after_sec=runtime_cfg.download_stalled_after_sec,
    )

    sources = register_or_update_sources(job_id=payload.job_id, project=payload.project, sources=downloadable_sources)
    final_status = "degraded" if download_error_count > 0 else "completed"
    update_job(payload.job_id, status=final_status, message="source collection completed", progress=1.0)

    return {
        "job_id": payload.job_id,
        "collected_count": len(sources),
        "sources": sources,
    }


def get_source(source_id: str) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT source_id, job_id, project, source_type, url, final_url, title, publisher,
                   domain, language, content_type, local_original_path, local_text_path,
                   local_markdown_path, local_screenshot_path, linked_document_id, status,
                   source_score, source_score_breakdown,
                   error, retrieved_at, created_at, updated_at
            FROM nexus_sources
            WHERE source_id = ?
            """,
            (source_id,),
        ).fetchone()
    if row is None:
        raise _source_not_found()
    return {"source_id": source_id, "source": _normalize_source_row(dict(row))}


def _source_file_response(source_id: str, key: str, filename_suffix: str) -> FileResponse:
    source = get_source(source_id).get("source", {})
    raw_path = str(source.get(key) or "").strip()
    if not raw_path:
        raise HTTPException(status_code=404, detail=f"{key} not ready")
    path = Path(raw_path)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"{key} missing")
    return FileResponse(path, filename=f"{source_id}.{filename_suffix}")


def get_source_text(source_id: str) -> FileResponse:
    return _source_file_response(source_id, "local_text_path", "txt")


def get_source_markdown(source_id: str) -> FileResponse:
    return _source_file_response(source_id, "local_markdown_path", "md")


def get_source_original(source_id: str) -> FileResponse:
    source = get_source(source_id).get("source", {})
    raw_path = str(source.get("local_original_path") or "").strip()
    if not raw_path:
        raise HTTPException(status_code=404, detail="original not ready")
    path = Path(raw_path)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="original missing")
    return FileResponse(path, filename=path.name)


def get_source_chunks(source_id: str) -> dict:
    _ = get_source(source_id)
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT sc.id, sc.source_id, sc.document_id, sc.chunk_id, sc.page_start, sc.page_end,
                   sc.section_path, sc.citation_label, sc.created_at,
                   c.title AS chunk_title, c.text AS chunk_text
            FROM nexus_source_chunks sc
            LEFT JOIN nexus_chunks c ON c.chunk_id = sc.chunk_id
            WHERE sc.source_id = ?
            ORDER BY sc.created_at ASC, sc.id ASC
            """,
            (source_id,),
        ).fetchall()
    return {"source_id": source_id, "chunks": [dict(row) for row in rows]}
