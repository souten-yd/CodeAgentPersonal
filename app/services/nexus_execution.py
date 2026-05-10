from __future__ import annotations

from dataclasses import asdict
from typing import Any, Callable, Mapping

from app.nexus.evidence import EvidenceItem, build_library_evidence, save_evidence_items
from app.nexus.research_api import CollectRequest, ResearchRunRequest


class NexusExecutionError(Exception):
    """Route-neutral Nexus execution error with an HTTP-compatible status."""

    def __init__(self, detail: str, *, status_code: int = 400) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def _payload_to_dict(payload: Any) -> dict[str, Any]:
    if hasattr(payload, "model_dump"):
        return dict(payload.model_dump())
    if hasattr(payload, "dict"):
        return dict(payload.dict())
    try:
        return dict(payload)
    except (TypeError, ValueError):
        return dict(getattr(payload, "__dict__", {}) or {})


def _payload_dict(payload: Any) -> dict[str, Any]:
    return _payload_to_dict(payload)


def _value_or_default(payload: Any, name: str, default: Any) -> Any:
    value = getattr(payload, name, None)
    return default if value is None else value


def _clone_research_request(payload: Any, **overrides: Any) -> ResearchRunRequest:
    data = _payload_to_dict(payload)
    data.update({k: v for k, v in overrides.items() if v is not None})
    return ResearchRunRequest(**data)


def _build_deep_research_payload(payload: Any, **overrides: Any) -> ResearchRunRequest:
    deep_defaults = {
        "mode": "deep",
        "depth": "deep",
        "max_queries": _value_or_default(payload, "max_queries", 6),
        "max_results_per_query": _value_or_default(payload, "max_results_per_query", 8),
        "max_sources": _value_or_default(payload, "max_sources", 40),
        "max_downloads": _value_or_default(payload, "max_downloads", 16),
        "prefer_pdf": True,
        "official_first": True,
        "continue_on_download_error": True,
        "source_profile": _value_or_default(payload, "source_profile", "web"),
        "confidence_threshold": _value_or_default(payload, "confidence_threshold", 0.78),
        "stop_when_sufficient": _value_or_default(payload, "stop_when_sufficient", True),
    }
    deep_defaults.update(overrides)
    return _clone_research_request(payload, **deep_defaults)


def _as_canonical_payload(operation: str, request: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "operation": operation,
        "request": dict(request),
        "result": dict(result),
    }


def _with_item_provider_engine(search: Mapping[str, Any]) -> list[dict[str, Any]]:
    selected_provider = str(search.get("selected_provider") or search.get("provider") or "unknown")
    normalized_items: list[dict[str, Any]] = []
    for item in (search.get("items") or []):
        row = dict(item)
        row["provider"] = str(row.get("provider") or selected_provider)
        row["engine"] = str(row.get("engine") or row.get("provider") or "unknown")
        normalized_items.append(row)
    return normalized_items


def run_nexus_search_service(
    payload: Any,
    *,
    search_evidence: Callable[..., tuple[list[dict[str, Any]], dict[str, Any]]],
    build_library_evidence_items: Callable[[list[dict[str, Any]]], list[Any]] = build_library_evidence,
) -> dict[str, Any]:
    query = str(getattr(payload, "query", "") or "").strip()
    if not query:
        raise NexusExecutionError("query must not be empty")

    limit = getattr(payload, "limit", None)
    if limit is None:
        top_k = getattr(payload, "top_k", None)
        limit = top_k if top_k is not None else 10
    results, applied_filters = search_evidence(
        query=query,
        limit=limit,
        scope=getattr(payload, "scope", None),
        doc_types=getattr(payload, "doc_types", []),
        filters=getattr(payload, "filters", {}),
    )
    response: dict[str, Any] = {
        "query": query,
        "scope": getattr(payload, "scope", None),
        "doc_types": getattr(payload, "doc_types", []),
        "limit": limit,
        "top_k": getattr(payload, "top_k", None),
        "filters": getattr(payload, "filters", {}),
        "applied_filters": applied_filters,
        "results": results,
    }
    if getattr(payload, "as_evidence", False):
        response["evidence"] = [asdict(item) for item in build_library_evidence_items(results)]
    return response


def run_nexus_web_search_service(
    payload: Any,
    *,
    execute_web_search: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    query = str(getattr(payload, "query", "") or "").strip()
    if not query:
        raise NexusExecutionError("query must not be empty")
    service_result = execute_web_search(
        query=query,
        mode=getattr(payload, "mode", "standard"),
        depth=getattr(payload, "depth", None),
        max_queries=getattr(payload, "max_queries", None),
        max_results_per_query=getattr(payload, "max_results_per_query", None),
        scope=getattr(payload, "scope", None),
        language=getattr(payload, "language", None),
    )
    queries = service_result.get("queries", [])
    search = dict(service_result.get("search") or {})
    items = _with_item_provider_engine(search)
    search["items"] = items
    search["total_items"] = int(search.get("total_items") or len(items))
    return _as_canonical_payload(
        "web.search",
        _payload_dict(payload),
        {
            "job_id": service_result.get("job_id"),
            "queries": queries,
            "generated_queries": search.get("generated_queries", queries),
            "effective_query_plan": search.get("effective_query_plan", {}),
            "provider": search.get("provider"),
            "selected_provider": search.get("selected_provider"),
            "attempted_providers": search.get("attempted_providers", []),
            "fallback_used": bool(search.get("fallback_used", False)),
            "skipped_providers": search.get("skipped_providers", {}),
            "provider_errors": search.get("provider_errors", {}),
            "configured": bool(search.get("configured", False)),
            "non_fatal": bool(search.get("non_fatal", False)),
            "message": search.get("message", ""),
            "saved_evidence": service_result.get("saved_evidence", 0),
            "search": search,
            "items": items,
            "total_items": search.get("total_items", len(items)),
        },
    )


def run_nexus_web_research_service(
    payload: Any,
    *,
    run_research_async: Callable[[ResearchRunRequest], dict[str, Any]],
) -> dict[str, Any]:
    delegated = run_research_async(
        ResearchRunRequest(
            query=getattr(payload, "query"),
            mode=getattr(payload, "mode", "standard"),
            depth=getattr(payload, "depth", None),
            max_queries=getattr(payload, "max_queries", None),
            max_results_per_query=getattr(payload, "max_results_per_query", None),
            scope=getattr(payload, "scope", None),
            language=getattr(payload, "language", None),
        )
    )
    summary = f"{str(getattr(payload, 'query', '')).strip()} に関するWeb調査（MVP）"
    return _as_canonical_payload("web.research", _payload_dict(payload), {**delegated, "summary": summary})


def run_nexus_research_service(
    payload: ResearchRunRequest,
    *,
    run_research_async: Callable[[ResearchRunRequest], dict[str, Any]],
) -> dict[str, Any]:
    return run_research_async(payload)


def run_nexus_deep_research_service(
    payload: ResearchRunRequest,
    *,
    run_research_async: Callable[[ResearchRunRequest], dict[str, Any]],
) -> dict[str, Any]:
    deep_payload = _build_deep_research_payload(payload)
    return run_research_async(deep_payload)


def run_nexus_recursive_research_service(
    payload: ResearchRunRequest,
    *,
    run_research_async: Callable[[ResearchRunRequest], dict[str, Any]],
) -> dict[str, Any]:
    recursive_payload = _build_deep_research_payload(
        payload,
        recursive_search=True,
        max_iterations=_value_or_default(payload, "max_iterations", 2),
        max_followup_queries=_value_or_default(payload, "max_followup_queries", 4),
    )
    if recursive_payload.max_iterations < 2:
        recursive_payload = _clone_research_request(recursive_payload, max_iterations=2)
    return run_research_async(recursive_payload)


async def ingest_nexus_document_service(
    *,
    file: Any,
    project: str = "default",
    accept_upload: Callable[..., Any],
) -> dict[str, Any]:
    return await accept_upload(file=file, project=project)


def index_nexus_document_service(*args: Any, index_document: Callable[..., dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
    return index_document(*args, **kwargs)


def collect_nexus_web_sources_service(
    payload: CollectRequest,
    *,
    collect_web_sources: Callable[[CollectRequest], dict[str, Any]],
) -> dict[str, Any]:
    return collect_web_sources(payload)


def run_nexus_sources_search_service(
    payload: Any,
    *,
    search_chunks: Callable[[Any], list[dict[str, Any]]],
) -> dict[str, Any]:
    results = search_chunks(payload)
    if getattr(payload, "collapse_duplicates", False):
        deduped: dict[str, dict[str, Any]] = {}
        for row in results:
            key = str(row.get("source_id") or "")
            deduped.setdefault(key, row)
        results = list(deduped.values())
    return {
        "query": getattr(payload, "query", ""),
        "scope": getattr(payload, "scope", "current_research_job"),
        "collapse_duplicates": getattr(payload, "collapse_duplicates", False),
        "results": results,
    }


def add_nexus_evidence_from_chunks_service(
    payload: Any,
    *,
    fetch_chunk_rows: Callable[[list[str]], list[dict[str, Any]]],
    save_items: Callable[[str, list[EvidenceItem]], int] = save_evidence_items,
) -> dict[str, Any]:
    chunk_ids = list(getattr(payload, "chunk_ids", []) or [])
    job_id = str(getattr(payload, "job_id", ""))
    if not chunk_ids:
        return {"job_id": job_id, "added": 0}
    rows = fetch_chunk_rows(chunk_ids)
    items = [
        EvidenceItem(
            source_type=str(r.get("source_type") or "research"),
            document_id=str(r.get("document_id") or ""),
            chunk_id=str(r.get("chunk_id") or ""),
            url=str(r.get("url") or f"nexus://chunk/{r.get('chunk_id')}"),
            retrieved_at=str(r.get("retrieved_at") or ""),
            source_id=str(r.get("source_id") or ""),
            title=str(r.get("title") or r.get("chunk_title") or ""),
            citation_label=str(r.get("citation_label") or ""),
            quote=str(r.get("text") or ""),
            note="added_from_chunks",
            metadata_json={"page_start": r.get("page_start"), "page_end": r.get("page_end")},
        )
        for r in rows
    ]
    added = save_items(job_id, items)
    return {"job_id": job_id, "added": added}


def run_nexus_research_followup_service(
    job_id: str,
    payload: Any,
    *,
    search_chunks: Callable[[Any], list[dict[str, Any]]],
    source_search_request_factory: Callable[..., Any],
    run_research_async: Callable[[ResearchRunRequest], dict[str, Any]] | None = None,
    append_followup_parent_event: Callable[[str, dict[str, Any]], Any] | None = None,
) -> dict[str, Any]:
    question = getattr(payload, "question")
    if getattr(payload, "use_existing_sources_only", True):
        results = search_chunks(
            source_search_request_factory(
                query=question,
                scope="current_research_job",
                job_id=job_id,
                limit=getattr(payload, "limit", 20),
            )
        )
        top = results[: min(5, len(results))]
        answer = "該当箇所が見つかりませんでした。"
        if top:
            bullets = [f"- {r.get('citation_label','[S]')} {r.get('title','')} / {r.get('snippet','')}" for r in top]
            answer = "収集済みソースのみを検索した結果:\n" + "\n".join(bullets)
        return {
            "job_id": job_id,
            "parent_job_id": job_id,
            "question": question,
            "use_existing_sources_only": True,
            "mode": "existing_sources",
            "answer": answer,
            "results": results,
        }

    if run_research_async is None:
        raise NexusExecutionError("run_research_async is required for deep-search follow-up")

    max_iterations = int(getattr(payload, "max_iterations", 1) or 1)
    request = ResearchRunRequest(
        query=question,
        project=getattr(payload, "project", None) or "default",
        mode="deep",
        depth="deep",
        max_queries=getattr(payload, "max_queries", None),
        max_results_per_query=getattr(payload, "max_results_per_query", None),
        max_sources=getattr(payload, "max_sources", None),
        max_downloads=getattr(payload, "max_downloads", None),
        manual_urls=None,
        prefer_pdf=True,
        official_first=True,
        continue_on_download_error=True,
        recursive_search=max_iterations > 1,
        max_iterations=max_iterations,
        confidence_threshold=getattr(payload, "confidence_threshold", 0.78),
        source_profile=getattr(payload, "source_profile", None) or "web",
    )
    delegated = run_research_async(request)
    new_job_id = str(delegated.get("job_id") or (delegated.get("job") or {}).get("job_id") or "")
    if new_job_id and append_followup_parent_event is not None:
        append_followup_parent_event(
            new_job_id,
            {
                "parent_job_id": job_id,
                "question": question,
                "mode": "deep_search",
            },
        )
    return {
        **delegated,
        "job_id": new_job_id,
        "parent_job_id": job_id,
        "question": question,
        "use_existing_sources_only": False,
        "mode": "deep_search",
        "followup_job": delegated.get("job"),
    }


def build_nexus_report_service(*args: Any, build_report: Callable[..., dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
    return build_report(*args, **kwargs)


def run_nexus_ask_service(
    payload: Any,
    *,
    search_evidence: Callable[..., tuple[list[dict[str, Any]], dict[str, Any]]],
    build_library_evidence_items: Callable[[list[dict[str, Any]]], list[Any]] = build_library_evidence,
) -> dict[str, Any]:
    query = str(getattr(payload, "query", "") or "").strip()
    if not query:
        raise NexusExecutionError("query must not be empty")
    limit = getattr(payload, "limit", None)
    if limit is None:
        top_k = getattr(payload, "top_k", None)
        limit = top_k if top_k is not None else 10
    results, applied_filters = search_evidence(
        query=query,
        limit=limit,
        scope=getattr(payload, "scope", None),
        doc_types=getattr(payload, "doc_types", []),
        filters=getattr(payload, "filters", {}),
    )
    top = results[0] if results else None
    answer = f"上位候補: {top.get('chunk', {}).get('title')}" if top else "該当する候補が見つかりませんでした。"
    return _as_canonical_payload(
        "ask",
        _payload_dict(payload),
        {
            "answer": answer,
            "applied_filters": applied_filters,
            "results": results,
            "evidence": [asdict(item) for item in build_library_evidence_items(results)] if getattr(payload, "as_evidence", False) else [],
        },
    )
