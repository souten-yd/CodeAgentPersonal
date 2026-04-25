from __future__ import annotations

import uuid
from typing import Any

from app.nexus.evidence import EvidenceItem, save_evidence_items
from app.nexus.jobs import create_job
from app.nexus.report import build_report
from app.nexus.search import search_evidence
from app.nexus.web_scout import build_web_evidence, plan_web_queries, run_web_search


def nexus_search_library(query: str, top_k: int = 10) -> dict[str, Any]:
    hits = search_evidence(query=query, top_k=top_k)
    return {
        "ok": True,
        "query": query,
        "top_k": top_k,
        "count": len(hits),
        "hits": hits,
    }


def nexus_web_search(topic: str, max_queries: int = 4, max_results_per_query: int = 5) -> dict[str, Any]:
    queries = plan_web_queries(topic, max_queries=max_queries)
    search_output = run_web_search(queries, max_results_per_query=max_results_per_query)

    job_id = str(uuid.uuid4())
    create_job(job_id, title=f"nexus_web_search:{topic}", message="tool_invocation")

    evidence_items = build_web_evidence(search_output, note="nexus_web_search")
    saved = save_evidence_items(job_id, evidence_items)

    return {
        "ok": True,
        "job_id": job_id,
        "topic": topic,
        "queries": queries,
        "saved_evidence": saved,
        "search": search_output,
    }


def nexus_build_report(
    title: str,
    sections: list[dict[str, Any]],
    report_type: str = "standard",
    job_id: str | None = None,
) -> dict[str, Any]:
    resolved_job_id = (job_id or "").strip() or str(uuid.uuid4())
    if not job_id:
        create_job(resolved_job_id, title=title, message="nexus_build_report")

    evidence_items: list[EvidenceItem] = []
    for section in sections:
        for ev in section.get("evidence") or []:
            evidence_items.append(
                EvidenceItem(
                    chunk_id=str(ev.get("chunk_id") or ""),
                    citation_label=str(ev.get("citation_label") or ""),
                    source_url=str(ev.get("source_url") or "about:blank"),
                    retrieved_at=str(ev.get("retrieved_at") or ""),
                    note=ev.get("note"),
                    quote=ev.get("quote"),
                    metadata=ev.get("metadata") or {},
                )
            )

    saved = save_evidence_items(resolved_job_id, evidence_items)
    report = build_report(job_id=resolved_job_id, report_type=report_type, title=title, sections=sections)
    return {
        "ok": True,
        "job_id": resolved_job_id,
        "saved_evidence": saved,
        "report": report,
    }
