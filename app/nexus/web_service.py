from __future__ import annotations

import uuid
from typing import Any

from app.nexus.evidence import save_evidence_items
from app.nexus.jobs import create_job
from app.nexus.web_scout import build_web_evidence, plan_web_queries, run_web_search


def execute_nexus_web_search(
    query: str,
    *,
    mode: str = "standard",
    depth: str | None = None,
    max_queries: int | None = None,
    max_results_per_query: int | None = None,
    scope: str | list[str] | None = None,
    language: str | None = None,
) -> dict[str, Any]:
    normalized_query = (query or "").strip()
    if not normalized_query:
        raise ValueError("query must not be empty")

    requested_depth = (depth or mode or "standard").strip() or "standard"

    queries = plan_web_queries(
        normalized_query,
        mode=mode,
        depth=requested_depth,
        max_queries=max_queries,
        scope=scope,
        language=language,
    )
    search_output = run_web_search(
        queries,
        mode=mode,
        depth=requested_depth,
        max_results_per_query=max_results_per_query,
        scope=scope,
        language=language,
    )

    job_id = str(uuid.uuid4())
    create_job(job_id, title=f"nexus_web_search:{normalized_query}", message="tool_invocation")

    evidence_items = build_web_evidence(search_output, note="nexus_web_search")
    saved_evidence = save_evidence_items(job_id, evidence_items)

    return {
        "ok": True,
        "job_id": job_id,
        "queries": queries,
        "saved_evidence": saved_evidence,
        "search": search_output,
    }
