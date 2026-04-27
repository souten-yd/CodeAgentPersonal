from __future__ import annotations

import csv
import io
import json
from pathlib import Path
import tempfile
from typing import Any
import zipfile

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.nexus.db import NEXUS_DIR, get_conn
from app.nexus.evidence import list_evidence_items
from app.nexus.jobs import get_job, get_job_events
from app.nexus.report import get_latest_report
from app.nexus.web_scout import plan_web_queries


_BUNDLE_DIR = Path(tempfile.gettempdir()) / "codeagent_nexus_bundles"
_BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
nexus_export_router = APIRouter()


def _normalize_source_row(row: dict) -> dict:
    normalized = dict(row)
    try:
        normalized["source_score"] = float(normalized.get("source_score") or 0.0)
    except (TypeError, ValueError):
        normalized["source_score"] = 0.0
    raw_breakdown = normalized.get("source_score_breakdown")
    if isinstance(raw_breakdown, str):
        try:
            parsed = json.loads(raw_breakdown)
        except (TypeError, ValueError):
            parsed = {}
        normalized["source_score_breakdown"] = parsed if isinstance(parsed, dict) else {}
    elif not isinstance(raw_breakdown, dict):
        normalized["source_score_breakdown"] = {}
    return normalized


def _collect_document_ids(job_id: str, evidence: list[dict]) -> list[str]:
    ids: set[str] = set()
    for item in evidence:
        chunk_id = str(item.get("chunk_id") or "")
        if ":" in chunk_id:
            ids.add(chunk_id.split(":", 1)[0])

    for event in get_job_events(job_id):
        document_id = str(event.data.get("document_id") or "").strip()
        if document_id:
            ids.add(document_id)

    return sorted(ids)


def _iter_existing_children(root: Path):
    if not root.exists() or not root.is_dir():
        return
    for path in sorted(root.rglob("*")):
        if path.is_file():
            yield path


def _write_document_dirs_to_zip(zf: zipfile.ZipFile, document_ids: list[str]) -> None:
    for document_id in document_ids:
        extracted_root = NEXUS_DIR / "extracted" / document_id
        uploads_root = NEXUS_DIR / "uploads" / document_id

        for src in _iter_existing_children(extracted_root) or []:
            rel = src.relative_to(extracted_root).as_posix()
            zf.write(src, f"extracted/{document_id}/{rel}")
        for src in _iter_existing_children(uploads_root) or []:
            rel = src.relative_to(uploads_root).as_posix()
            zf.write(src, f"files/{document_id}/{rel}")


def create_nexus_bundle(job_id: str, report: dict) -> Path:
    """Create nexus_bundle_{job_id}.zip with evidence/report/job artifacts."""
    if not job_id:
        raise ValueError("job_id is required")

    job = get_job(job_id)
    if not job:
        raise ValueError("job not found")

    evidence = list_evidence_items(job_id)
    related_document_ids = _collect_document_ids(job_id, evidence)
    report_md = Path(str(report.get("markdown_path") or report.get("report_md_path") or ""))
    report_html = Path(str(report.get("html_path") or report.get("report_html_path") or ""))

    zip_path = _BUNDLE_DIR / f"nexus_bundle_{job_id}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("evidence.json", json.dumps(evidence, ensure_ascii=False, indent=2))

        csv_buf = io.StringIO()
        writer = csv.DictWriter(csv_buf, fieldnames=["citation_label", "source_url", "retrieved_at", "chunk_id"])
        writer.writeheader()
        for item in evidence:
            writer.writerow(
                {
                    "citation_label": item.get("citation_label", ""),
                    "source_url": item.get("url", "") or item.get("source_url", ""),
                    "retrieved_at": item.get("retrieved_at", ""),
                    "chunk_id": item.get("chunk_id", ""),
                }
            )
        zf.writestr("sources.csv", csv_buf.getvalue())

        if report_md.exists():
            zf.write(report_md, "report.md")
        if report_html.exists():
            zf.write(report_html, "report.html")

        job_payload = job.model_dump(mode="json") if hasattr(job, "model_dump") else job
        zf.writestr("job.json", json.dumps(job_payload, ensure_ascii=False, indent=2))
        _write_document_dirs_to_zip(zf, related_document_ids)

    return zip_path


def _list_job_sources(job_id: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT source_id, job_id, project, source_type, url, final_url, title, publisher,
                   domain, language, content_type, local_original_path, local_text_path,
                   local_markdown_path, local_screenshot_path, linked_document_id, status,
                   source_score, source_score_breakdown,
                   error, retrieved_at, created_at, updated_at
            FROM nexus_sources
            WHERE job_id = ?
            ORDER BY created_at ASC, source_id ASC
            """,
            (job_id,),
        ).fetchall()
    return [_normalize_source_row(dict(row)) for row in rows]


def _latest_research_answer(job_id: str) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT answer_id, question, answer_markdown, evidence_json, source_ids_json, created_at
            FROM nexus_research_answers
            WHERE job_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (job_id,),
        ).fetchone()
    if row is None:
        return {}

    return {
        "answer_id": row["answer_id"],
        "question": row["question"],
        "answer_markdown": row["answer_markdown"],
        "evidence": json.loads(row["evidence_json"] or "[]"),
        "source_ids": json.loads(row["source_ids_json"] or "[]"),
        "created_at": row["created_at"],
    }


def _zip_write_if_exists(zf: zipfile.ZipFile, src_path: str, dst_path: str) -> None:
    path = Path(str(src_path or "").strip())
    if path.exists() and path.is_file():
        zf.write(path, dst_path)


def _list_source_chunks(job_id: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT sc.id, sc.source_id, sc.document_id, sc.chunk_id, sc.page_start, sc.page_end,
                   sc.section_path, sc.citation_label, sc.created_at,
                   c.title AS chunk_title, c.text AS chunk_text
            FROM nexus_source_chunks sc
            JOIN nexus_sources s ON s.source_id = sc.source_id
            LEFT JOIN nexus_chunks c ON c.chunk_id = sc.chunk_id
            WHERE s.job_id = ?
            ORDER BY sc.created_at ASC, sc.id ASC
            """,
            (job_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def _extract_saved_queries(events: list[Any]) -> list[str]:
    candidate_keys = (
        "queries",
        "generated_queries",
        "planned_queries",
        "executed_queries",
        "search_queries",
    )
    recovered: list[str] = []
    seen: set[str] = set()
    for event in events:
        data = event.data if hasattr(event, "data") else {}
        if not isinstance(data, dict):
            continue
        for key in candidate_keys:
            raw = data.get(key)
            if not isinstance(raw, list):
                continue
            for item in raw:
                query = str(item or "").strip()
                if query and query not in seen:
                    seen.add(query)
                    recovered.append(query)
        effective_plan = data.get("effective_query_plan")
        if isinstance(effective_plan, dict):
            raw_queries = effective_plan.get("queries")
            if isinstance(raw_queries, list):
                for item in raw_queries:
                    query = str(item or "").strip()
                    if query and query not in seen:
                        seen.add(query)
                        recovered.append(query)
    return recovered


def _build_queries_payload(job: Any, answer: dict, events: list[Any]) -> dict:
    saved = _extract_saved_queries(events)
    if saved:
        return {"planned_queries": saved, "executed_queries": saved, "reconstructed": False}

    question = str(answer.get("question") or "")
    if not question and hasattr(job, "title"):
        question = str(job.title or "")
    question = question.strip()
    if not question:
        return {"planned_queries": [], "executed_queries": [], "reconstructed": True}

    reconstructed = plan_web_queries(question, mode="standard")
    return {
        "planned_queries": reconstructed,
        "executed_queries": reconstructed,
        "reconstructed": True,
        "reconstruction_source": "answer.question_or_job.title",
    }


def create_research_bundle(job_id: str) -> Path:
    if not job_id:
        raise ValueError("job_id is required")

    job = get_job(job_id)
    if not job:
        raise ValueError("job not found")

    answer = _latest_research_answer(job_id)
    sources = _list_job_sources(job_id)
    evidence = list_evidence_items(job_id)
    source_chunks = _list_source_chunks(job_id)
    events = get_job_events(job_id)
    events_payload = [event.model_dump(mode="json") if hasattr(event, "model_dump") else event for event in events]
    queries = _build_queries_payload(job, answer, events)
    report = get_latest_report(job_id)
    report_md = Path(str((report or {}).get("markdown_path") or (report or {}).get("report_md_path") or ""))

    zip_path = _BUNDLE_DIR / f"nexus_research_bundle_{job_id}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        answer_markdown = str(answer.get("answer_markdown") or "").strip()
        if answer_markdown:
            zf.writestr("answer.md", answer_markdown + "\n")
        zf.writestr("answer.json", json.dumps(answer, ensure_ascii=False, indent=2))
        zf.writestr("evidence.json", json.dumps(evidence, ensure_ascii=False, indent=2))
        zf.writestr("sources.json", json.dumps(sources, ensure_ascii=False, indent=2))
        zf.writestr("source_chunks.json", json.dumps(source_chunks, ensure_ascii=False, indent=2))
        zf.writestr("events.json", json.dumps(events_payload, ensure_ascii=False, indent=2))
        zf.writestr("queries.json", json.dumps(queries, ensure_ascii=False, indent=2))

        csv_buf = io.StringIO()
        writer = csv.DictWriter(
            csv_buf,
            fieldnames=[
                "source_id",
                "source_type",
                "url",
                "final_url",
                "title",
                "publisher",
                "domain",
                "status",
                "retrieved_at",
            ],
        )
        writer.writeheader()
        for source in sources:
            writer.writerow(
                {
                    "source_id": source.get("source_id", ""),
                    "source_type": source.get("source_type", ""),
                    "url": source.get("url", ""),
                    "final_url": source.get("final_url", ""),
                    "title": source.get("title", ""),
                    "publisher": source.get("publisher", ""),
                    "domain": source.get("domain", ""),
                    "status": source.get("status", ""),
                    "retrieved_at": source.get("retrieved_at", ""),
                }
            )
        zf.writestr("sources.csv", csv_buf.getvalue())

        for source in sources:
            source_id = str(source.get("source_id") or "").strip()
            if not source_id:
                continue
            source_root = f"downloads/{source_id}"
            zf.writestr(f"{source_root}/metadata.json", json.dumps(source, ensure_ascii=False, indent=2))
            zf.writestr(f"{source_root}/metadata/source.json", json.dumps(source, ensure_ascii=False, indent=2))

            original_path = str(source.get("local_original_path") or "").strip()
            if original_path:
                original_suffix = Path(original_path).suffix or ".bin"
                original_name = Path(original_path).name or f"original{original_suffix}"
                _zip_write_if_exists(zf, original_path, f"{source_root}/original{original_suffix}")
                _zip_write_if_exists(zf, original_path, f"{source_root}/original/{original_name}")
            _zip_write_if_exists(zf, str(source.get("local_text_path") or ""), f"{source_root}/text.txt")
            _zip_write_if_exists(zf, str(source.get("local_markdown_path") or ""), f"{source_root}/document.md")
            _zip_write_if_exists(zf, str(source.get("local_text_path") or ""), f"{source_root}/extracted/content.txt")
            _zip_write_if_exists(zf, str(source.get("local_markdown_path") or ""), f"{source_root}/extracted/content.md")
            _zip_write_if_exists(
                zf,
                str(source.get("local_screenshot_path") or ""),
                f"{source_root}/metadata/screenshot{Path(str(source.get('local_screenshot_path') or '')).suffix or '.png'}",
            )

        job_payload = job.model_dump(mode="json") if hasattr(job, "model_dump") else job
        zf.writestr("job.json", json.dumps(job_payload, ensure_ascii=False, indent=2))

        if report_md.exists():
            zf.write(report_md, "report.md")

    return zip_path


@nexus_export_router.get("/download/bundle/{job_id}")
def download_nexus_bundle(job_id: str) -> FileResponse:
    if not job_id:
        raise HTTPException(status_code=400, detail="job_id is required")

    report = get_latest_report(job_id)
    if report is None:
        raise HTTPException(status_code=404, detail="report not found for job_id")

    try:
        zip_path = create_nexus_bundle(job_id, report=report)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return FileResponse(
        path=zip_path,
        media_type="application/zip",
        filename=zip_path.name,
    )


@nexus_export_router.get("/research/jobs/{job_id}/bundle.zip")
def download_research_bundle(job_id: str) -> FileResponse:
    try:
        zip_path = Path(create_research_bundle(job_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return FileResponse(
        path=zip_path,
        media_type="application/zip",
        filename=zip_path.name,
    )


@nexus_export_router.get("/download/report/{report_id}")
def download_report_file(report_id: str) -> FileResponse:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT markdown_path, report_md_path FROM nexus_reports WHERE report_id = ?",
            (report_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="report not found")

    report_md = Path(str(row["markdown_path"] or row["report_md_path"] or ""))
    if not report_md.exists():
        raise HTTPException(status_code=404, detail="report markdown missing")

    return FileResponse(report_md, filename=f"{report_id}.md")


@nexus_export_router.get("/download/report/{report_id}/html")
def download_report_html_file(report_id: str) -> FileResponse:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT html_path, report_html_path FROM nexus_reports WHERE report_id = ?",
            (report_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="report not found")

    report_html = Path(str(row["html_path"] or row["report_html_path"] or ""))
    if not report_html.exists():
        raise HTTPException(status_code=404, detail="report html missing")

    return FileResponse(report_html, filename=f"{report_id}.html", media_type="text/html")


@nexus_export_router.get("/download/report/{report_id}/json")
def download_report_json_file(report_id: str) -> FileResponse:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT json_path, report_json_path FROM nexus_reports WHERE report_id = ?",
            (report_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="report not found")

    report_json = Path(str(row["json_path"] or row["report_json_path"] or ""))
    if not report_json.exists():
        raise HTTPException(status_code=404, detail="report json missing")

    return FileResponse(report_json, filename=f"{report_id}.json", media_type="application/json")


@nexus_export_router.get("/download/evidence/{job_id}")
def download_evidence_file(job_id: str) -> FileResponse:
    if get_job(job_id) is None:
        raise HTTPException(status_code=404, detail="job not found")

    evidence = list_evidence_items(job_id)
    output_path = _BUNDLE_DIR / f"evidence_{job_id}.json"
    output_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    return FileResponse(output_path, filename=output_path.name, media_type="application/json")


@nexus_export_router.get("/download/document/{document_id}")
def download_document_file(document_id: str) -> FileResponse:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT filename, path FROM nexus_documents WHERE id = ?",
            (document_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="document not found")

    path = Path(str(row["path"]))
    if not path.exists():
        raise HTTPException(status_code=404, detail="document file missing")

    return FileResponse(path, filename=str(row["filename"]))
