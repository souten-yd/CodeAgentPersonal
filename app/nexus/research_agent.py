from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import uuid

from app.nexus.answer_builder import build_answer_payload
from app.nexus.citation_mapper import build_citation_map
from app.nexus.jobs import append_job_event, create_job, update_job
from app.nexus.source_collector import collect_source_candidates
from app.nexus.source_registry import register_or_update_sources
from app.nexus.db import get_conn
from app.nexus.web_scout import plan_web_queries, run_web_search


RESEARCH_STATES = (
    "queued",
    "planning",
    "searching",
    "collecting_sources",
    "downloading",
    "extracting",
    "ingesting_to_library",
    "retrieving_evidence",
    "answering",
    "verifying",
    "reporting",
    "completed",
    "failed",
    "cancelled",
)


@dataclass
class ResearchAgentInput:
    query: str
    project: str = "default"
    mode: str = "standard"
    depth: str | None = None
    max_queries: int | None = None
    max_results_per_query: int | None = None
    scope: str | list[str] | None = None
    language: str | None = None
    manual_urls: list[str] | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()




def _load_source_chunks(source_ids: list[str]) -> list[dict]:
    normalized = [s for s in source_ids if s]
    if not normalized:
        return []
    placeholders = ",".join("?" for _ in normalized)
    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT sc.source_id, sc.chunk_id, sc.page_start, sc.page_end, sc.citation_label,
                   c.title AS title, c.text AS quote
            FROM nexus_source_chunks sc
            LEFT JOIN nexus_chunks c ON c.chunk_id = sc.chunk_id
            WHERE sc.source_id IN ({placeholders})
            ORDER BY sc.created_at ASC, sc.id ASC
            """,
            tuple(normalized),
        ).fetchall()
    return [dict(row) for row in rows]
def _record_state(job_id: str, state: str, *, message: str, progress: float) -> None:
    append_job_event(
        job_id,
        "state_transition",
        {
            "state": state,
            "status": state,
            "message": message,
            "progress": progress,
            "updated_at": _now_iso(),
        },
    )


def run_research_job(payload: ResearchAgentInput) -> dict:
    query = payload.query.strip()
    if not query:
        raise ValueError("query must not be empty")

    job_id = f"research_{uuid.uuid4().hex}"
    create_job(job_id, title=query, message="research queued", status="queued")

    try:
        _record_state(job_id, "planning", message="query planning", progress=0.1)
        queries = plan_web_queries(
            query,
            mode=payload.mode,
            depth=payload.depth,
            max_queries=payload.max_queries,
            scope=payload.scope,
            language=payload.language,
        )
        update_job(job_id, status="running", progress=0.2, message="searching web")

        _record_state(job_id, "searching", message="running web search", progress=0.25)
        search = run_web_search(
            queries,
            mode=payload.mode,
            depth=payload.depth,
            max_results_per_query=payload.max_results_per_query,
            scope=payload.scope,
            language=payload.language,
        )
        items = list(search.get("items") or [])

        _record_state(job_id, "collecting_sources", message="normalizing source candidates", progress=0.4)
        candidates = collect_source_candidates(search_items=items, manual_urls=payload.manual_urls)
        registered_sources = register_or_update_sources(job_id=job_id, project=payload.project, sources=candidates)

        _record_state(job_id, "retrieving_evidence", message="mapping citations", progress=0.7)
        source_chunks = _load_source_chunks([str(item.get("source_id") or "") for item in registered_sources])
        references = build_citation_map(registered_sources, source_chunks)

        _record_state(job_id, "answering", message="building answer", progress=0.85)
        summary = f"{query} に関する調査結果を {len(references)} 件のソースから整理しました。"
        answer_payload = build_answer_payload(
            question=query,
            summary=summary,
            references=references,
            evidence=registered_sources,
            job_id=job_id,
            project=payload.project,
        )

        _record_state(job_id, "reporting", message="finalizing report", progress=0.95)
        update_job(job_id, status="completed", progress=1.0, message="research completed")
        _record_state(job_id, "completed", message="job completed", progress=1.0)

        return {
            "job_id": job_id,
            "queries": queries,
            "search": search,
            "sources": registered_sources,
            "answer": answer_payload,
        }
    except Exception as exc:  # noqa: BLE001
        update_job(job_id, status="failed", progress=1.0, message="research failed", error=str(exc))
        _record_state(job_id, "failed", message=str(exc), progress=1.0)
        raise
