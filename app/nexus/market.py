from __future__ import annotations

import uuid
from typing import Any

from app.nexus.config import load_runtime_config
from app.nexus.evidence import save_evidence_items
from app.nexus.jobs import create_job, update_job
from app.nexus.web_scout import build_web_evidence, plan_web_queries, run_web_search


ALLOWED_SEARCH_MODES = {"quick", "standard", "deep", "exhaustive"}


def _normalize_mode(mode: str | None) -> str:
    raw_mode = (mode or "standard").strip().lower()
    if raw_mode in ALLOWED_SEARCH_MODES:
        return raw_mode
    return "standard"


def _evidence_title(item: Any) -> str:
    metadata = getattr(item, "metadata_json", {}) or {}
    title = (
        getattr(item, "title", None)
        or metadata.get("title")
        or getattr(item, "quote", None)
        or "(no title)"
    )
    return str(title)


def run_market_mvp(
    symbol_or_theme: str,
    *,
    mode: str = "standard",
    max_results_per_query: int | None = None,
) -> dict[str, Any]:
    """MVP: market input -> web evidence save -> quick market snapshot.

    Future extension points:
    - EDGAR connector for SEC filings ingestion.
    - GDELT connector for macro/geopolitical event overlays.
    - Crossref connector for supporting research references.
    """
    cfg = load_runtime_config()
    seed = (symbol_or_theme or "").strip()
    if not seed:
        raise ValueError("symbol_or_theme is required")

    normalized_mode = _normalize_mode(mode)

    if not cfg.enable_market:
        return {
            "symbol_or_theme": seed,
            "mode": normalized_mode,
            "saved_evidence": 0,
            "message": "NEXUS_ENABLE_MARKET=false のため、マーケット取得をスキップしました。",
            "disabled": True,
        }

    job_id = str(uuid.uuid4())
    create_job(job_id, title=f"market:{seed}", message="market_mvp")
    update_job(job_id, status="running")

    queries = plan_web_queries(f"{seed} market outlook", mode=normalized_mode)
    search_output = run_web_search(
        queries,
        mode=normalized_mode,
        max_results_per_query=max_results_per_query,
    )
    evidence_items = build_web_evidence(search_output, note="market_mvp")
    saved_count = save_evidence_items(job_id, evidence_items)

    catalysts = [_evidence_title(item) for item in evidence_items[:5]]

    template = {
        "symbol_or_theme": seed,
        "mode": normalized_mode,
        "bull_case": "TBD",
        "bear_case": "TBD",
        "catalysts": catalysts,
        "next_checks": ["filings", "earnings", "macro indicators"],
    }

    update_job(job_id, status="completed", document_count=saved_count)
    return {
        "job_id": job_id,
        "mode": normalized_mode,
        "queries": queries,
        "saved_evidence": saved_count,
        "search": search_output,
        "snapshot": {
            "summary": f"{seed} の簡易マーケットスナップショット（MVP）",
            "template": template,
        },
    }
