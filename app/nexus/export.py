from __future__ import annotations

import csv
import io
import json
from pathlib import Path
import tempfile
import zipfile

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.nexus.db import NEXUS_DIR, get_conn
from app.nexus.evidence import list_evidence_items
from app.nexus.jobs import get_job, get_job_events
from app.nexus.report import get_latest_report


_BUNDLE_DIR = Path(tempfile.gettempdir()) / "codeagent_nexus_bundles"
_BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
nexus_export_router = APIRouter()


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
    report_md = Path(report["report_md_path"])
    report_html = Path(report["report_html_path"])

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
                    "source_url": item.get("source_url", ""),
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


@nexus_export_router.get("/download/report/{report_id}")
def download_report_file(report_id: str) -> FileResponse:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT report_md_path FROM nexus_reports WHERE report_id = ?",
            (report_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="report not found")

    report_md = Path(str(row["report_md_path"]))
    if not report_md.exists():
        raise HTTPException(status_code=404, detail="report markdown missing")

    return FileResponse(report_md, filename=f"{report_id}.md")


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
