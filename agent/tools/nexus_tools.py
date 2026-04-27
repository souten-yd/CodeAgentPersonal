from __future__ import annotations

import asyncio
import io
from pathlib import Path
import uuid
from typing import Any

from fastapi import UploadFile

from app.nexus.evidence import EvidenceItem, list_evidence_items, save_evidence_items
from app.nexus.export import create_nexus_bundle
from app.nexus.ingest import accept_upload
from app.nexus.jobs import create_job
from app.nexus.market import run_market_mvp
from app.nexus.news import run_news_mvp
from app.nexus.report import build_report, get_latest_report, save_report_record
from app.nexus.search import search_evidence
from app.nexus.web_scout import build_web_evidence, plan_web_queries, run_web_search


# --- Single Nexus API call layer -------------------------------------------------

def _call_nexus_api(operation: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Single indirection point for Nexus API/domain calls.

    This keeps tool functions thin and prevents tight coupling with router endpoints.
    """

    if operation == "library.search":
        query = str(payload.get("query") or "").strip()
        top_k = int(payload.get("top_k", 10))
        results, applied_filters = search_evidence(query=query, limit=top_k)
        return {
            "ok": True,
            "query": query,
            "top_k": top_k,
            "count": len(results),
            "hits": results,
            "applied_filters": applied_filters,
        }

    if operation == "web.search":
        topic = str(payload.get("topic") or "").strip()
        mode = str(payload.get("mode") or "standard").strip() or "standard"
        depth = payload.get("depth")
        language = payload.get("language")
        scope = payload.get("scope")
        max_queries = int(payload.get("max_queries", 4))
        max_results_per_query = int(payload.get("max_results_per_query", 5))
        queries = plan_web_queries(
            topic,
            mode=mode,
            depth=depth,
            max_queries=max_queries,
            scope=scope,
            language=language,
        )
        search_output = run_web_search(
            queries,
            mode=mode,
            depth=depth,
            max_results_per_query=max_results_per_query,
            scope=scope,
            language=language,
        )

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

    if operation == "report.build":
        job_id = str(payload.get("job_id") or "").strip()
        report_type = str(payload.get("report_type") or "general").strip()
        title = payload.get("title")
        if not job_id:
            raise ValueError("job_id is required")

        report_title = str(title).strip() if title is not None else f"Nexus Report ({job_id})"
        evidence = list_evidence_items(job_id)
        sections = [{"heading": "Evidence", "summary": f"Collected evidence count: {len(evidence)}", "evidence": evidence}]
        report = build_report(job_id=job_id, report_type=report_type, title=report_title, sections=sections)
        report["project"] = "default"
        save_report_record(report)
        return {
            "ok": True,
            "job_id": job_id,
            "report": report,
        }

    if operation == "document.upload":
        file_path = str(payload.get("file_path") or "").strip()
        project = str(payload.get("project") or "default").strip() or "default"
        content_type = str(payload.get("content_type") or "application/octet-stream")
        if not file_path:
            raise ValueError("file_path is required")
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            raise ValueError("file_path must be an existing file")

        upload = UploadFile(file=io.BytesIO(path.read_bytes()), filename=path.name)
        response = asyncio.run(accept_upload(file=upload, project=project))
        return {
            "ok": True,
            "operation": operation,
            "request": {"file_path": file_path, "project": project},
            "result": response,
        }

    if operation == "news.scan":
        topic = str(payload.get("topic") or "").strip()
        mode = str(payload.get("mode") or "standard").strip() or "standard"
        max_results_per_query = payload.get("max_results_per_query")
        if not topic:
            raise ValueError("topic is required")
        response = run_news_mvp(topic=topic, mode=mode, max_results_per_query=max_results_per_query)
        return {
            "ok": True,
            "operation": operation,
            "request": {
                "topic": topic,
                "mode": mode,
                "max_results_per_query": max_results_per_query,
            },
            "result": response,
        }

    if operation == "market.research":
        symbol_or_theme = str(payload.get("symbol_or_theme") or "").strip()
        mode = str(payload.get("mode") or "standard").strip() or "standard"
        max_results_per_query = payload.get("max_results_per_query")
        if not symbol_or_theme:
            raise ValueError("symbol_or_theme is required")
        response = run_market_mvp(
            symbol_or_theme=symbol_or_theme,
            mode=mode,
            max_results_per_query=max_results_per_query,
        )
        return {
            "ok": True,
            "operation": operation,
            "request": {
                "symbol_or_theme": symbol_or_theme,
                "mode": mode,
                "max_results_per_query": max_results_per_query,
            },
            "result": response,
        }

    if operation == "bundle.export":
        job_id = str(payload.get("job_id") or "").strip()
        if not job_id:
            raise ValueError("job_id is required")
        report = get_latest_report(job_id)
        if report is None:
            raise ValueError("report not found for job_id")
        zip_path = create_nexus_bundle(job_id=job_id, report=report)
        return {
            "ok": True,
            "operation": operation,
            "request": {"job_id": job_id},
            "result": {
                "bundle_path": str(zip_path),
                "filename": zip_path.name,
            },
        }

    raise ValueError(f"unsupported nexus operation: {operation}")


# --- Public tool functions --------------------------------------------------------

def nexus_search_library(query: str, top_k: int = 10) -> dict[str, Any]:
    """Search chunks in Nexus library."""
    return _call_nexus_api("library.search", {"query": query, "top_k": top_k})


def nexus_web_search(
    topic: str,
    max_queries: int = 4,
    max_results_per_query: int = 5,
    mode: str = "standard",
    depth: str | None = None,
    language: str | None = None,
    scope: str | list[str] | None = None,
) -> dict[str, Any]:
    """Web検索を実行し、検索結果をNexus Evidenceとして保存してjob_idを返却する。返却されたjob_idはnexus_build_report / nexus_export_bundleに接続可能。"""
    return _call_nexus_api(
        "web.search",
        {
            "topic": topic,
            "max_queries": max_queries,
            "max_results_per_query": max_results_per_query,
            "mode": mode,
            "depth": depth,
            "language": language,
            "scope": scope,
        },
    )


def nexus_build_report(job_id: str, report_type: str = "general", title: str | None = None) -> dict[str, Any]:
    """Build report by job_id (required-signature compatible)."""
    return _call_nexus_api("report.build", {"job_id": job_id, "report_type": report_type, "title": title})


def nexus_build_report_legacy(
    title: str,
    sections: list[dict[str, Any]],
    report_type: str = "standard",
    job_id: str | None = None,
) -> dict[str, Any]:
    """Backward-compatible wrapper of the previous nexus_build_report signature."""
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
        "legacy": True,
    }


def nexus_upload_document(file_path: str, project: str = "default", content_type: str = "application/octet-stream") -> dict[str, Any]:
    """Upload a local document file to Nexus."""
    return _call_nexus_api(
        "document.upload",
        {"file_path": file_path, "project": project, "content_type": content_type},
    )


def nexus_news_scan(topic: str, mode: str = "standard", max_results_per_query: int | None = None) -> dict[str, Any]:
    """Scan news for a topic via Nexus API layer."""
    return _call_nexus_api(
        "news.scan",
        {"topic": topic, "mode": mode, "max_results_per_query": max_results_per_query},
    )


def nexus_market_research(
    symbol_or_theme: str,
    mode: str = "standard",
    max_results_per_query: int | None = None,
) -> dict[str, Any]:
    """Run market research for a symbol/theme via Nexus API layer."""
    return _call_nexus_api(
        "market.research",
        {
            "symbol_or_theme": symbol_or_theme,
            "mode": mode,
            "max_results_per_query": max_results_per_query,
        },
    )


def nexus_export_bundle(job_id: str) -> dict[str, Any]:
    """Create Nexus evidence/report bundle zip and return its path."""
    return _call_nexus_api("bundle.export", {"job_id": job_id})
