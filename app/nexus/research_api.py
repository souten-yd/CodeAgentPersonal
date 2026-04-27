from __future__ import annotations

import json
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.nexus.db import get_conn
from app.nexus.evidence import list_evidence_items
from app.nexus.jobs import create_job, get_job, get_job_events, update_job
from app.nexus.research_agent import ResearchAgentInput, run_research_job
from app.nexus.source_collector import collect_source_candidates
from app.nexus.source_registry import register_or_update_sources


class ResearchRunRequest(BaseModel):
    query: str = Field(min_length=1)
    project: str = Field(default="default")
    mode: str = Field(default="standard")
    depth: str | None = None
    max_queries: int | None = Field(default=None, ge=1, le=20)
    max_results_per_query: int | None = Field(default=None, ge=1, le=20)
    scope: str | list[str] | None = None
    language: str | None = None
    manual_urls: list[str] | None = None


class CollectRequest(BaseModel):
    job_id: str = Field(min_length=1)
    project: str = Field(default="default")
    search_items: list[dict] = Field(default_factory=list)
    manual_urls: list[str] = Field(default_factory=list)


def _source_not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="source not found")


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
                scope=payload.scope,
                language=payload.language,
                manual_urls=payload.manual_urls,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job_id = str(result.get("job_id") or "")
    return {
        "job_id": job_id,
        "job": get_research_job(job_id).get("job"),
        "queries": result.get("queries", []),
        "answer": result.get("answer", {}),
        "sources": result.get("sources", []),
    }


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
                   error, retrieved_at, created_at, updated_at
            FROM nexus_sources
            WHERE job_id = ?
            ORDER BY created_at ASC, source_id ASC
            """,
            (job_id,),
        ).fetchall()

    sources = [dict(row) for row in rows]
    return {"job_id": job_id, "sources": sources}


def get_research_job_answer(job_id: str) -> dict:
    _ = get_research_job(job_id)
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT answer_id, question, answer_markdown, evidence_json, source_ids_json, created_at
            FROM nexus_research_answers
            WHERE job_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (job_id,),
        ).fetchone()

    if row is None:
        return {"job_id": job_id, "answer": {}}

    answer = {
        "answer_id": row["answer_id"],
        "question": row["question"],
        "answer_markdown": row["answer_markdown"],
        "evidence": json.loads(row["evidence_json"] or "[]"),
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
    return {
        "job_id": job_id,
        "job": base.get("job", {}),
        "events": events,
        "answer": answer,
        "sources": sources,
        "evidence": evidence,
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
    sources = register_or_update_sources(job_id=payload.job_id, project=payload.project, sources=candidates)
    update_job(payload.job_id, status="completed", message="source collection completed", progress=1.0)

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
                   error, retrieved_at, created_at, updated_at
            FROM nexus_sources
            WHERE source_id = ?
            """,
            (source_id,),
        ).fetchone()
    if row is None:
        raise _source_not_found()
    return {"source_id": source_id, "source": dict(row)}


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
