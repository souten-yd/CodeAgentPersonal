from __future__ import annotations

import uuid
from typing import Any

from app.nexus.evidence import save_evidence_items
from app.nexus.jobs import create_job, update_job
from app.nexus.web_scout import build_web_evidence, plan_web_queries, run_web_search


def run_news_mvp(topic: str, *, max_results_per_query: int = 5) -> dict[str, Any]:
    """MVP: topic input -> web evidence save -> lightweight digest output.

    Future extension points:
    - GDELT connector for event-level global news timelines.
    - Crossref connector for paper/news linkage and source quality checks.
    """
    query_seed = (topic or "").strip()
    if not query_seed:
        raise ValueError("topic is required")

    job_id = str(uuid.uuid4())
    create_job(job_id, title=f"news:{query_seed}", message="news_mvp")
    update_job(job_id, status="running")

    queries = plan_web_queries(f"{query_seed} latest news")
    search_output = run_web_search(queries, max_results_per_query=max_results_per_query)
    evidence_items = build_web_evidence(search_output, note="news_mvp")
    saved_count = save_evidence_items(job_id, evidence_items)

    headlines = [
        (item.metadata.get("title") or item.quote or "(no title)")
        for item in evidence_items[:5]
    ]

    template = {
        "topic": query_seed,
        "key_points": headlines,
        "risks": "TBD",
        "watch_items": ["source freshness", "claim validation"],
    }

    update_job(job_id, status="completed", document_count=saved_count)
    return {
        "job_id": job_id,
        "queries": queries,
        "saved_evidence": saved_count,
        "search": search_output,
        "digest": {
            "summary": f"{query_seed} の簡易ニュース要約（MVP）",
            "template": template,
        },
    }
