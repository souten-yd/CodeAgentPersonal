from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import threading
import uuid

from fastapi import UploadFile

from app.nexus.db import NEXUS_DIR, insert_chunk, insert_document
from app.nexus.extractors import DependencyMissingError, extract_pages
from app.nexus.jobs import append_job_event, create_job, update_job

UPLOAD_ROOT = NEXUS_DIR / "uploads"
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)

MIN_CHUNK_SIZE = 800
MAX_CHUNK_SIZE = 1200
MIN_OVERLAP = 100
MAX_OVERLAP = 200
DEFAULT_CHUNK_SIZE = 1000
DEFAULT_OVERLAP = 150


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _chunk_text(text: str) -> list[str]:
    cleaned = " ".join(text.split())
    if not cleaned:
        return []

    chunk_size = min(MAX_CHUNK_SIZE, max(MIN_CHUNK_SIZE, DEFAULT_CHUNK_SIZE))
    overlap = min(MAX_OVERLAP, max(MIN_OVERLAP, DEFAULT_OVERLAP))

    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(len(cleaned), start + chunk_size)
        chunk = cleaned[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(cleaned):
            break
        start = max(start + 1, end - overlap)
    return chunks


def _extract_and_index(document_id: str, path: Path, filename: str, job_id: str) -> None:
    update_job(job_id, status="running", message="extracting")
    append_job_event(job_id, "progress", {"label": "extracting", "document_id": document_id})

    try:
        pages = extract_pages(path)
    except DependencyMissingError as exc:
        message = str(exc)
        update_job(
            job_id,
            status="completed",
            message="dependency_missing",
            error=message,
            document_count=1,
        )
        append_job_event(job_id, "dependency_missing", {"document_id": document_id, "error": message})
        return
    except Exception as exc:
        update_job(job_id, status="failed", error=str(exc), message="extract_failed")
        append_job_event(job_id, "job_failed", {"document_id": document_id, "error": str(exc)})
        return

    created_at = _now_iso()
    inserted = 0
    chunk_index = 0
    for page in pages:
        for content in _chunk_text(page.text):
            chunk_id = f"{document_id}:{chunk_index}"
            citation_label = f"{filename} p.{page.page_no}"
            insert_chunk(
                chunk_id=chunk_id,
                document_id=document_id,
                chunk_index=chunk_index,
                title=filename,
                section_path="/",
                content=content,
                page_start=page.page_no,
                page_end=page.page_no,
                citation_label=citation_label,
                created_at=created_at,
            )
            chunk_index += 1
            inserted += 1

    update_job(job_id, status="completed", message="extracted", document_count=1)
    append_job_event(
        job_id,
        "job_completed",
        {"status": "completed", "document_id": document_id, "chunks": inserted},
    )


async def accept_upload(*, file: UploadFile, project: str = "default") -> dict:
    if not file.filename:
        raise ValueError("File name is required")

    document_id = str(uuid.uuid4())
    ext = Path(file.filename).suffix.lower()
    safe_ext = ext if ext else ".bin"
    doc_dir = UPLOAD_ROOT / document_id
    doc_dir.mkdir(parents=True, exist_ok=True)
    stored_path = doc_dir / f"original{safe_ext}"

    content = await file.read()
    stored_path.write_bytes(content)
    digest = sha256(content).hexdigest()
    created_at = _now_iso()

    insert_document(
        document_id=document_id,
        project=project,
        filename=Path(file.filename).name,
        size=len(content),
        content_type=file.content_type or "application/octet-stream",
        path=str(stored_path),
        sha256=digest,
        created_at=created_at,
    )

    job_id = str(uuid.uuid4())
    create_job(job_id, title="nexus_extract", message="queued", document_count=1)
    append_job_event(job_id, "queued", {"document_id": document_id, "path": str(stored_path)})

    worker = threading.Thread(
        target=_extract_and_index,
        args=(document_id, stored_path, Path(file.filename).name, job_id),
        daemon=True,
    )
    worker.start()

    return {
        "document": {
            "id": document_id,
            "project": project,
            "filename": Path(file.filename).name,
            "size": len(content),
            "content_type": file.content_type or "application/octet-stream",
            "sha256": digest,
            "created_at": created_at,
        },
        "job": {"job_id": job_id, "status": "queued"},
    }
