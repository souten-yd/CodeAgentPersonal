from __future__ import annotations

import uuid
from typing import Any

from app.nexus.evidence import save_evidence_items
from app.nexus.jobs import create_job, update_job
from app.nexus.web_scout import build_web_evidence, plan_web_queries, run_web_search


def run_market_mvp(symbol_or_theme: str, *, max_results_per_query: int = 5) -> dict[str, Any]:
    """MVP: market input -> web evidence save -> quick market snapshot.

    Future extension points:
    - EDGAR connector for SEC filings ingestion.
    - GDELT connector for macro/geopolitical event overlays.
    - Crossref connector for supporting research references.
    """
    seed = (symbol_or_theme or "").strip()
    if not seed:
        raise ValueError("symbol_or_theme is required")

    job_id = str(uuid.uuid4())
    create_job(job_id, title=f"market:{seed}", message="market_mvp")
    update_job(job_id, status="running")

    queries = plan_web_queries(f"{seed} market outlook")
    search_output = run_web_search(queries, max_results_per_query=max_results_per_query)
    evidence_items = build_web_evidence(search_output, note="market_mvp")
    saved_count = save_evidence_items(job_id, evidence_items)

    catalysts = [
        (item.metadata.get("title") or item.quote or "(no title)")
        for item in evidence_items[:5]
    ]

    template = {
        "symbol_or_theme": seed,
        "bull_case": "TBD",
        "bear_case": "TBD",
        "catalysts": catalysts,
        "next_checks": ["filings", "earnings", "macro indicators"],
    }

    update_job(job_id, status="completed", document_count=saved_count)
    return {
        "job_id": job_id,
        "queries": queries,
        "saved_evidence": saved_count,
        "search": search_output,
        "snapshot": {
            "summary": f"{seed} の簡易マーケットスナップショット（MVP）",
            "template": template,
        },
    }
