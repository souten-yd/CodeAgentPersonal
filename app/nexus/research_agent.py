from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import uuid

from app.nexus.answer_builder import build_answer_payload
from app.nexus.citation_mapper import build_citation_map, normalize_reference_labels
from app.nexus.downloader import safe_download, save_download_artifacts
from app.nexus.evidence import EvidenceItem, save_evidence_items
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


def _build_evidence_from_sources(job_id: str, sources: list[dict]) -> list[EvidenceItem]:
    source_ids = [str(item.get("source_id") or "").strip() for item in sources]
    source_ids = [source_id for source_id in source_ids if source_id]
    if not source_ids:
        return []

    placeholders = ",".join("?" for _ in source_ids)
    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT s.source_id, s.source_type, s.url, s.final_url, s.title, s.publisher, s.retrieved_at,
                   s.linked_document_id, sc.chunk_id, sc.citation_label, c.text AS quote
            FROM nexus_sources s
            LEFT JOIN nexus_source_chunks sc ON sc.source_id = s.source_id
            LEFT JOIN nexus_chunks c ON c.chunk_id = sc.chunk_id
            WHERE s.source_id IN ({placeholders})
            ORDER BY s.created_at ASC, sc.id ASC
            """,
            tuple(source_ids),
        ).fetchall()

    evidence: list[EvidenceItem] = []
    seen_chunk_keys: set[tuple[str, str]] = set()

    for row in rows:
        source_id = str(row["source_id"] or "")
        chunk_id = str(row["chunk_id"] or "").strip()
        linked_document_id = str(row["linked_document_id"] or "")
        if chunk_id:
            dedupe_key = (source_id, chunk_id)
            if dedupe_key in seen_chunk_keys:
                continue
            seen_chunk_keys.add(dedupe_key)
            evidence.append(
                EvidenceItem(
                    source_id=source_id,
                    source_type=str(row["source_type"] or "web"),
                    document_id=linked_document_id,
                    chunk_id=chunk_id,
                    url=str(row["final_url"] or row["url"] or ""),
                    retrieved_at=str(row["retrieved_at"] or _now_iso()),
                    title=str(row["title"] or ""),
                    publisher=str(row["publisher"] or ""),
                    citation_label=str(row["citation_label"] or ""),
                    note=f"source:{source_id}",
                    quote=str(row["quote"] or ""),
                    metadata_json={"source_id": source_id, "linked_document_id": linked_document_id},
                )
            )

    if not evidence:
        for source in sources:
            source_id = str(source.get("source_id") or "").strip()
            if not source_id:
                continue
            evidence.append(
                EvidenceItem(
                    source_id=source_id,
                    source_type=str(source.get("source_type") or "web"),
                    document_id=str(source.get("linked_document_id") or ""),
                    chunk_id=f"{source_id}:fallback",
                    url=str(source.get("final_url") or source.get("url") or ""),
                    retrieved_at=str(source.get("retrieved_at") or _now_iso()),
                    title=str(source.get("title") or ""),
                    publisher=str(source.get("publisher") or ""),
                    citation_label=f"[S{len(evidence) + 1}]",
                    note="fallback_without_chunks",
                    quote=str(source.get("snippet") or ""),
                    metadata_json={"source_id": source_id, "fallback": True},
                )
            )
    return evidence


def run_research_job(payload: ResearchAgentInput, *, job_id: str | None = None) -> dict:
    query = payload.query.strip()
    if not query:
        raise ValueError("query must not be empty")

    effective_job_id = job_id or f"research_{uuid.uuid4().hex}"
    if not job_id:
        create_job(effective_job_id, title=query, message="research queued", status="queued")

    try:
        _record_state(effective_job_id, "planning", message="query planning", progress=0.1)
        queries = plan_web_queries(
            query,
            mode=payload.mode,
            depth=payload.depth,
            max_queries=payload.max_queries,
            scope=payload.scope,
            language=payload.language,
        )
        update_job(effective_job_id, status="running", progress=0.2, message="searching web")

        _record_state(effective_job_id, "searching", message="running web search", progress=0.25)
        search = run_web_search(
            queries,
            mode=payload.mode,
            depth=payload.depth,
            max_results_per_query=payload.max_results_per_query,
            scope=payload.scope,
            language=payload.language,
        )
        items = list(search.get("items") or [])

        _record_state(effective_job_id, "collecting_sources", message="normalizing source candidates", progress=0.4)
        candidates = collect_source_candidates(search_items=items, manual_urls=payload.manual_urls)
        _record_state(effective_job_id, "downloading", message="downloading source content", progress=0.55)
        downloadable_sources: list[dict] = []
        for candidate in candidates:
            source_id = str(candidate.get("source_id") or uuid.uuid4())
            source = {
                **candidate,
                "source_id": source_id,
                "final_url": str(candidate.get("url") or ""),
                "content_type": "",
                "local_original_path": "",
                "local_text_path": "",
                "local_markdown_path": "",
                "status": "download_failed",
                "error": "",
            }
            url = str(candidate.get("url") or "").strip()
            if not url:
                source["error"] = "url is missing"
                downloadable_sources.append(source)
                continue
            try:
                download_result = safe_download(url)
                saved = save_download_artifacts(
                    job_id=effective_job_id,
                    source_id=source_id,
                    download_result=download_result,
                )
                source["final_url"] = str(download_result.get("final_url") or url)
                source["content_type"] = str(download_result.get("content_type") or "")
                source["local_original_path"] = str(saved.get("original") or "")
                source["local_text_path"] = str(saved.get("extracted_txt") or "")
                source["local_markdown_path"] = str(saved.get("extracted_md") or "")
                source["status"] = str(saved.get("status") or "downloaded")
                source["error"] = str(saved.get("error") or "")
            except Exception as exc:  # noqa: BLE001
                source["error"] = str(exc)
                source["status"] = "degraded"
            downloadable_sources.append(source)

        registered_sources = register_or_update_sources(
            job_id=effective_job_id,
            project=payload.project,
            sources=downloadable_sources,
        )

        evidence_items = _build_evidence_from_sources(effective_job_id, registered_sources)
        save_evidence_items(effective_job_id, evidence_items)

        _record_state(effective_job_id, "retrieving_evidence", message="mapping citations", progress=0.7)
        source_chunks = _load_source_chunks([str(item.get("source_id") or "") for item in registered_sources])
        references = build_citation_map(registered_sources, source_chunks)
        normalized = normalize_reference_labels(
            references=references,
            evidence_json=registered_sources,
            evidence_chunks=source_chunks,
        )
        references = normalized["references"]
        registered_sources = normalized["evidence_json"]
        source_chunks = normalized["evidence_chunks"]

        _record_state(effective_job_id, "answering", message="building answer", progress=0.85)
        if references:
            labels = [f"[S{i + 1}]" for i in range(len(references))]
            summary = f"{query} に関する調査結果です。確認済みソース: {' '.join(labels)}"
        else:
            summary = f"{query} に関する根拠は未確認です。現時点では断定できません。"
        answer_payload = build_answer_payload(
            question=query,
            summary=summary,
            references=references,
            evidence=registered_sources,
            evidence_chunks=source_chunks,
            job_id=effective_job_id,
            project=payload.project,
        )

        _record_state(effective_job_id, "reporting", message="finalizing report", progress=0.95)
        update_job(effective_job_id, status="completed", progress=1.0, message="research completed")
        _record_state(effective_job_id, "completed", message="job completed", progress=1.0)

        return {
            "job_id": effective_job_id,
            "queries": queries,
            "search": search,
            "sources": registered_sources,
            "answer": answer_payload,
        }
    except Exception as exc:  # noqa: BLE001
        update_job(effective_job_id, status="failed", progress=1.0, message="research failed", error=str(exc))
        _record_state(effective_job_id, "failed", message=str(exc), progress=1.0)
        raise
