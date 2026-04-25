from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import tempfile
import threading
import uuid
import zipfile

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

router = APIRouter()


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=10, ge=1, le=100)


class ReportBuildRequest(BaseModel):
    title: str = Field(default="Nexus Report")
    document_ids: list[str] = Field(default_factory=list)


_DATA_LOCK = threading.Lock()
_UPLOAD_DIR = Path(tempfile.gettempdir()) / "codeagent_nexus_uploads"
_BUNDLE_DIR = Path(tempfile.gettempdir()) / "codeagent_nexus_bundles"
_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
_BUNDLE_DIR.mkdir(parents=True, exist_ok=True)

_DOCUMENTS: dict[str, dict] = {}
_JOBS: dict[str, dict] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_error(status_code: int, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail=message)


@router.get("/summary")
def get_summary() -> dict:
    with _DATA_LOCK:
        queued = sum(1 for j in _JOBS.values() if j["status"] == "queued")
        done = sum(1 for j in _JOBS.values() if j["status"] == "done")
        error = sum(1 for j in _JOBS.values() if j["status"] == "error")
        return {
            "documents": len(_DOCUMENTS),
            "jobs": {
                "total": len(_JOBS),
                "queued": queued,
                "done": done,
                "error": error,
            },
        }


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    project: str = Form(default="default"),
) -> dict:
    if not file.filename:
        raise _json_error(400, "File name is required")

    doc_id = str(uuid.uuid4())
    safe_name = Path(file.filename).name
    dest = _UPLOAD_DIR / f"{doc_id}_{safe_name}"

    content = await file.read()
    dest.write_bytes(content)

    record = {
        "id": doc_id,
        "project": project,
        "filename": safe_name,
        "size": len(content),
        "content_type": file.content_type or "application/octet-stream",
        "path": str(dest),
        "created_at": _now_iso(),
    }
    with _DATA_LOCK:
        _DOCUMENTS[doc_id] = record

    return {"document": {k: v for k, v in record.items() if k != "path"}}


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    with _DATA_LOCK:
        job = _JOBS.get(job_id)
    if not job:
        raise _json_error(404, "Job not found")
    return job


@router.get("/documents")
def list_documents(project: str | None = None) -> dict:
    with _DATA_LOCK:
        documents = list(_DOCUMENTS.values())

    if project:
        documents = [d for d in documents if d["project"] == project]

    public_docs = [{k: v for k, v in d.items() if k != "path"} for d in documents]
    return {"documents": public_docs, "count": len(public_docs)}


@router.post("/search")
def search_documents(req: SearchRequest) -> dict:
    query = req.query.lower()
    with _DATA_LOCK:
        docs = list(_DOCUMENTS.values())

    hits = [
        {
            "document_id": d["id"],
            "filename": d["filename"],
            "project": d["project"],
            "score": 1.0,
        }
        for d in docs
        if query in d["filename"].lower() or query in d["project"].lower()
    ]
    return {"query": req.query, "hits": hits[: req.top_k], "count": len(hits)}


@router.post("/report/build")
def build_report(req: ReportBuildRequest) -> dict:
    job_id = str(uuid.uuid4())
    with _DATA_LOCK:
        selected_docs = [
            _DOCUMENTS[d_id]
            for d_id in req.document_ids
            if d_id in _DOCUMENTS
        ]

    bundle_path = _BUNDLE_DIR / f"{job_id}.zip"
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

    job = {
        "job_id": job_id,
        "status": "done",
        "title": req.title,
        "document_count": len(selected_docs),
        "created_at": _now_iso(),
        "download_url": f"/nexus/download/bundle/{job_id}",
        "bundle_path": str(bundle_path),
    }
    with _DATA_LOCK:
        _JOBS[job_id] = job

    return {k: v for k, v in job.items() if k != "bundle_path"}


@router.get("/download/bundle/{job_id}")
def download_bundle(job_id: str):
    with _DATA_LOCK:
        job = _JOBS.get(job_id)
    if not job:
        raise _json_error(404, "Job not found")

    bundle_path = Path(job.get("bundle_path", ""))
    if not bundle_path.exists():
        raise _json_error(404, "Bundle not found")

    return FileResponse(
        path=bundle_path,
        media_type="application/zip",
        filename=f"nexus_bundle_{job_id}.zip",
    )
