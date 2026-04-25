from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import tempfile
import time
import uuid
import zipfile

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.nexus.db import get_conn
from app.nexus.ingest import accept_upload
from app.nexus.jobs import (
    append_job_event,
    create_job,
    get_job as get_job_record,
    get_job_events,
    list_active_jobs,
    update_job,
)
from app.nexus.search import search_evidence

router = APIRouter()


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=10, ge=1, le=100)


class ReportBuildRequest(BaseModel):
    title: str = Field(default="Nexus Report")
    document_ids: list[str] = Field(default_factory=list)


_BUNDLE_DIR = Path(tempfile.gettempdir()) / "codeagent_nexus_bundles"
_BUNDLE_DIR.mkdir(parents=True, exist_ok=True)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_error(status_code: int, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail=message)


@router.get("/summary")
def get_summary() -> dict:
    active_jobs = list_active_jobs(limit=1000)
    with get_conn() as conn:
        documents = conn.execute("SELECT COUNT(*) FROM nexus_documents").fetchone()[0]

    return {
        "documents": documents,
        "jobs": {
            "active": len(active_jobs),
            "queued": sum(1 for j in active_jobs if j["status"] == "queued"),
            "running": sum(1 for j in active_jobs if j["status"] == "running"),
        },
    }


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    project: str = Form(default="default"),
) -> dict:
    try:
        return await accept_upload(file=file, project=project)
    except ValueError as exc:
        raise _json_error(400, str(exc)) from exc


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = get_job_record(job_id)
    if not job:
        raise _json_error(404, "Job not found")
    return job


@router.get("/jobs/active")
def get_active_jobs(limit: int = Query(default=100, ge=1, le=1000)) -> dict:
    jobs = list_active_jobs(limit=limit)
    return {"jobs": jobs, "count": len(jobs)}


@router.get("/jobs/{job_id}/events")
def get_job_events_endpoint(
    job_id: str,
    request: Request,
    after: int = Query(default=-1),
    mode: str = Query(default="auto", pattern="^(auto|poll|sse)$"),
):
    job = get_job_record(job_id)
    if not job:
        raise _json_error(404, "Job not found")

    wants_sse = mode == "sse" or (mode == "auto" and "text/event-stream" in request.headers.get("accept", ""))

    if not wants_sse:
        events = get_job_events(job_id, after=after)
        return {
            "job_id": job_id,
            "status": job["status"],
            "events": events,
            "next_after": (events[-1]["seq"] if events else after),
        }

    def generate():
        last_seq = after
        while True:
            events = get_job_events(job_id, after=last_seq)
            for event in events:
                payload = json.dumps({**event["data"], "type": event["type"], "seq": event["seq"]}, ensure_ascii=False)
                yield f"data: {payload}\n\n"
                last_seq = event["seq"]

            current = get_job_record(job_id)
            if current and current["status"] in {"completed", "failed"}:
                end_payload = json.dumps({"type": "job_end", "status": current["status"]}, ensure_ascii=False)
                yield f"data: {end_payload}\n\n"
                break
            time.sleep(0.5)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/documents")
def list_documents(project: str | None = None) -> dict:
    with get_conn() as conn:
        if project:
            rows = conn.execute(
                """
                SELECT id, project, filename, size, content_type, sha256, created_at
                FROM nexus_documents
                WHERE project = ?
                ORDER BY created_at DESC
                """,
                (project,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, project, filename, size, content_type, sha256, created_at
                FROM nexus_documents
                ORDER BY created_at DESC
                """
            ).fetchall()

    documents = [dict(row) for row in rows]
    return {"documents": documents, "count": len(documents)}


@router.post("/search")
def search_documents(req: SearchRequest) -> dict:
    hits = search_evidence(req.query, top_k=req.top_k)
    return {"query": req.query, "hits": hits, "count": len(hits)}


@router.post("/report/build")
def build_report(req: ReportBuildRequest) -> dict:
    job_id = str(uuid.uuid4())

    create_job(job_id, title=req.title, message="build_report")
    append_job_event(job_id, "progress", {"label": "queued"})
    update_job(job_id, status="running")

    with get_conn() as conn:
        if req.document_ids:
            placeholders = ",".join("?" for _ in req.document_ids)
            query = f"""
                SELECT id, filename, project, created_at
                FROM nexus_documents
                WHERE id IN ({placeholders})
            """
            rows = conn.execute(query, tuple(req.document_ids)).fetchall()
        else:
            rows = []
        selected_docs = [dict(row) for row in rows]

    bundle_path = _BUNDLE_DIR / f"{job_id}.zip"
    try:
        with zipfile.ZipFile(bundle_path, "w", zipfile.ZIP_DEFLATED) as zf:
            manifest = [
                {
                    "id": d["id"],
                    "filename": d["filename"],
                    "project": d["project"],
                    "created_at": d["created_at"],
                }
                for d in selected_docs
            ]
            zf.writestr("report.txt", f"{req.title}\nGenerated at: {_now_iso()}\n")
            zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

        download_url = f"/nexus/download/bundle/{job_id}"
        update_job(
            job_id,
            status="completed",
            document_count=len(selected_docs),
            download_url=download_url,
            bundle_path=str(bundle_path),
        )
        append_job_event(job_id, "job_completed", {"status": "completed", "download_url": download_url})
    except Exception as exc:
        update_job(job_id, status="failed", error=str(exc))
        append_job_event(job_id, "job_failed", {"status": "failed", "error": str(exc)})
        raise

    job = get_job_record(job_id)
    if not job:
        raise _json_error(500, "Failed to save job")
    return job


@router.get("/download/bundle/{job_id}")
def download_bundle(job_id: str):
    job = get_job_record(job_id)
    if not job:
        raise _json_error(404, "Job not found")

    bundle_path = Path((job.get("bundle_path") or "").strip())
    if not bundle_path.exists():
        raise _json_error(404, "Bundle not found")

    return FileResponse(
        path=bundle_path,
        media_type="application/zip",
        filename=f"nexus_bundle_{job_id}.zip",
    )
