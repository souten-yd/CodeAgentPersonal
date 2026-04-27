from __future__ import annotations

from datetime import datetime, timezone
import uuid
from typing import Any

from app.nexus.config import load_runtime_config
from app.nexus.db import get_conn
from app.nexus.evidence import save_evidence_items
from app.nexus.jobs import create_job, update_job
from app.nexus.web_scout import build_web_evidence, plan_web_queries, run_web_search


ALLOWED_SEARCH_MODES = {"quick", "standard", "deep", "exhaustive"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def list_watchlists(*, project: str = "default", include_inactive: bool = True) -> list[dict[str, Any]]:
    where = "WHERE project = ?"
    params: list[Any] = [project]
    if not include_inactive:
        where += " AND is_active = 1"

    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT watchlist_id, project, name, query, source_type, is_active,
                   last_checked_at, created_at, updated_at
            FROM nexus_watchlists
            {where}
            ORDER BY updated_at DESC
            """,
            params,
        ).fetchall()

    return [
        {
            "watchlist_id": row["watchlist_id"],
            "project": row["project"],
            "name": row["name"],
            "query": row["query"],
            "source_type": row["source_type"],
            "is_active": bool(row["is_active"]),
            "last_checked_at": row["last_checked_at"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]


def create_watchlist(
    *,
    name: str,
    query: str,
    project: str = "default",
    source_type: str = "news",
    is_active: bool = True,
) -> dict[str, Any]:
    now = _now_iso()
    watchlist_id = str(uuid.uuid4())

    name = (name or "").strip()
    query = (query or "").strip()
    source_type = (source_type or "news").strip() or "news"

    if not name:
        raise ValueError("name is required")
    if not query:
        raise ValueError("query is required")

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO nexus_watchlists(
                watchlist_id, project, name, query, source_type,
                is_active, last_checked_at, created_at, updated_at
            )
            VALUES(?, ?, ?, ?, ?, ?, NULL, ?, ?)
            """,
            (watchlist_id, project, name, query, source_type, 1 if is_active else 0, now, now),
        )
        conn.commit()

    return {
        "watchlist_id": watchlist_id,
        "project": project,
        "name": name,
        "query": query,
        "source_type": source_type,
        "is_active": is_active,
        "last_checked_at": None,
        "created_at": now,
        "updated_at": now,
    }


def update_watchlist(
    watchlist_id: str,
    *,
    project: str = "default",
    name: str | None = None,
    query: str | None = None,
    source_type: str | None = None,
    is_active: bool | None = None,
    last_checked_at: str | None = None,
) -> dict[str, Any] | None:
    update_fields: dict[str, Any] = {}

    if name is not None:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("name must not be empty")
        update_fields["name"] = normalized_name
    if query is not None:
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("query must not be empty")
        update_fields["query"] = normalized_query
    if source_type is not None:
        normalized_source_type = source_type.strip() or "news"
        update_fields["source_type"] = normalized_source_type
    if is_active is not None:
        update_fields["is_active"] = 1 if is_active else 0
    if last_checked_at is not None:
        update_fields["last_checked_at"] = last_checked_at

    if not update_fields:
        return get_watchlist(watchlist_id, project=project)

    now = _now_iso()
    update_fields["updated_at"] = now

    set_clause = ", ".join(f"{key} = ?" for key in update_fields)
    params = list(update_fields.values()) + [watchlist_id, project]

    with get_conn() as conn:
        result = conn.execute(
            f"""
            UPDATE nexus_watchlists
            SET {set_clause}
            WHERE watchlist_id = ? AND project = ?
            """,
            params,
        )
        conn.commit()

        if result.rowcount == 0:
            return None

    return get_watchlist(watchlist_id, project=project)


def get_watchlist(watchlist_id: str, *, project: str = "default") -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT watchlist_id, project, name, query, source_type, is_active,
                   last_checked_at, created_at, updated_at
            FROM nexus_watchlists
            WHERE watchlist_id = ? AND project = ?
            """,
            (watchlist_id, project),
        ).fetchone()

    if row is None:
        return None

    return {
        "watchlist_id": row["watchlist_id"],
        "project": row["project"],
        "name": row["name"],
        "query": row["query"],
        "source_type": row["source_type"],
        "is_active": bool(row["is_active"]),
        "last_checked_at": row["last_checked_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def delete_watchlist(watchlist_id: str, *, project: str = "default") -> bool:
    with get_conn() as conn:
        result = conn.execute(
            "DELETE FROM nexus_watchlists WHERE watchlist_id = ? AND project = ?",
            (watchlist_id, project),
        )
        conn.commit()
    return result.rowcount > 0


def run_news_mvp(
    topic: str,
    *,
    mode: str = "standard",
    max_results_per_query: int | None = None,
) -> dict[str, Any]:
    """MVP: topic input -> web evidence save -> lightweight digest output.

    Future extension points:
    - GDELT connector for event-level global news timelines.
    - Crossref connector for paper/news linkage and source quality checks.
    """
    cfg = load_runtime_config()
    query_seed = (topic or "").strip()
    if not query_seed:
        raise ValueError("topic is required")

    normalized_mode = _normalize_mode(mode)

    if not cfg.enable_news:
        return {
            "topic": query_seed,
            "mode": normalized_mode,
            "saved_evidence": 0,
            "message": "NEXUS_ENABLE_NEWS=false のため、ニュース取得をスキップしました。",
            "disabled": True,
        }

    job_id = str(uuid.uuid4())
    create_job(job_id, title=f"news:{query_seed}", message="news_mvp")
    update_job(job_id, status="running")

    queries = plan_web_queries(f"{query_seed} latest news", mode=normalized_mode)
    search_output = run_web_search(
        queries,
        mode=normalized_mode,
        max_results_per_query=max_results_per_query,
    )
    evidence_items = build_web_evidence(search_output, note="news_mvp")
    saved_count = save_evidence_items(job_id, evidence_items)

    headlines = [_evidence_title(item) for item in evidence_items[:5]]

    template = {
        "topic": query_seed,
        "mode": normalized_mode,
        "key_points": headlines,
        "risks": "TBD",
        "watch_items": ["source freshness", "claim validation"],
    }

    update_job(job_id, status="completed", document_count=saved_count)
    return {
        "job_id": job_id,
        "mode": normalized_mode,
        "queries": queries,
        "saved_evidence": saved_count,
        "search": search_output,
        "digest": {
            "summary": f"{query_seed} の簡易ニュース要約（MVP）",
            "template": template,
        },
    }
