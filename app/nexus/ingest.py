from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path, PurePath
import re
import threading
import uuid

from fastapi import UploadFile

from app.nexus.config import load_runtime_config
from app.nexus.db import NEXUS_DIR, insert_chunk, insert_document, update_document_artifact_paths
from app.nexus.extractors import DependencyMissingError, build_artifacts, extract_pages
from app.nexus.jobs import append_job_event, create_job, update_job

UPLOAD_ROOT = NEXUS_DIR / "uploads"
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)

MIN_CHUNK_SIZE = 800
MAX_CHUNK_SIZE = 1200
MIN_OVERLAP = 100
MAX_OVERLAP = 200
DEFAULT_CHUNK_SIZE = 1000
DEFAULT_OVERLAP = 150

ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md", ".csv", ".html"}
_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _max_upload_mb() -> int:
    return load_runtime_config().max_upload_mb


def _max_upload_size_bytes() -> int:
    return _max_upload_mb() * 1024 * 1024


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize_filename(filename: str) -> str:
    base = PurePath(filename).name.strip()
    if not base:
        raise ValueError("File name is required")

    # path traversal 対策: basename化後に危険パターンを拒否
    if base in {".", ".."}:
        raise ValueError("Invalid filename")

    safe = _FILENAME_RE.sub("_", base).strip("._")
    if not safe:
        safe = "upload"

    ext = Path(base).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError("Unsupported file extension")

    if not safe.lower().endswith(ext):
        safe = f"{safe}{ext}"

    return safe


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
    update_job(job_id, status="running", progress=0.05, message="extracting")
    append_job_event(
        job_id,
        "progress",
        {
            "status": "running",
            "progress": 0.05,
            "message": "extracting",
            "label": "extracting",
            "document_id": document_id,
        },
    )

    try:
        pages = extract_pages(path)
    except DependencyMissingError as exc:
        message = str(exc)
        update_job(
            job_id,
            status="completed",
            progress=1.0,
            message="dependency_missing",
            error=message,
            document_count=1,
        )
        append_job_event(
            job_id,
            "dependency_missing",
            {
                "status": "completed",
                "progress": 1.0,
                "message": "dependency_missing",
                "document_id": document_id,
                "error": message,
            },
        )
        return
    except Exception as exc:
        update_job(job_id, status="failed", progress=1.0, error=str(exc), message="extract_failed")
        append_job_event(
            job_id,
            "job_failed",
            {
                "status": "failed",
                "progress": 1.0,
                "message": "extract_failed",
                "document_id": document_id,
                "error": str(exc),
            },
        )
        return

    artifacts_dir = NEXUS_DIR / "extracted" / document_id
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    (artifacts_dir / "tables").mkdir(parents=True, exist_ok=True)
    (artifacts_dir / "images").mkdir(parents=True, exist_ok=True)

    artifacts = build_artifacts(pages)
    extracted_text_path = artifacts_dir / "text.txt"
    markdown_path = artifacts_dir / "document.md"
    extracted_text_path.write_text(artifacts.text, encoding="utf-8")
    markdown_path.write_text(artifacts.markdown, encoding="utf-8")

    created_at = _now_iso()
    update_document_artifact_paths(
        document_id=document_id,
        extracted_text_path=str(extracted_text_path),
        markdown_path=str(markdown_path),
        updated_at=created_at,
    )

    inserted = 0
    chunk_index = 0
    total_pages = max(1, len(pages))
    for page_idx, page in enumerate(pages, start=1):
        page_progress = 0.3 + (0.65 * page_idx / total_pages)
        update_job(job_id, progress=page_progress, message=f"indexing_page_{page_idx}")
        append_job_event(
            job_id,
            "progress",
            {
                "status": "running",
                "progress": page_progress,
                "message": f"indexing_page_{page_idx}",
                "document_id": document_id,
                "page": page_idx,
                "total_pages": total_pages,
            },
        )
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

    update_job(job_id, status="completed", progress=1.0, message="extracted", document_count=1)
    append_job_event(
        job_id,
        "job_completed",
        {
            "status": "completed",
            "progress": 1.0,
            "message": "extracted",
            "document_id": document_id,
            "chunks": inserted,
            "extracted_text_path": str(extracted_text_path),
            "markdown_path": str(markdown_path),
        },
    )


async def _read_upload_bytes(file: UploadFile) -> bytes:
    max_upload_mb = _max_upload_mb()
    max_upload_size_bytes = _max_upload_size_bytes()
    total = 0
    chunks: list[bytes] = []
    while True:
        part = await file.read(1024 * 1024)
        if not part:
            break
        total += len(part)
        if total > max_upload_size_bytes:
            raise ValueError(f"File too large (max {max_upload_mb} MB)")
        chunks.append(part)
    return b"".join(chunks)


async def accept_upload(*, file: UploadFile, project: str = "default") -> dict:
    if not file.filename:
        raise ValueError("File name is required")

    safe_filename = _sanitize_filename(file.filename)
    ext = Path(safe_filename).suffix.lower()

    content = await _read_upload_bytes(file)
    if not content:
        raise ValueError("Empty file is not allowed")

    document_id = str(uuid.uuid4())
    doc_dir = (UPLOAD_ROOT / document_id).resolve()
    doc_dir.mkdir(parents=True, exist_ok=True)

    root_resolved = UPLOAD_ROOT.resolve()
    if root_resolved not in doc_dir.parents and doc_dir != root_resolved:
        raise ValueError("Invalid upload path")

    stored_path = (doc_dir / f"original{ext}").resolve()
    if doc_dir not in stored_path.parents:
        raise ValueError("Invalid upload destination")

    stored_path.write_bytes(content)
    digest = sha256(content).hexdigest()
    created_at = _now_iso()

    insert_document(
        document_id=document_id,
        project=project,
        filename=safe_filename,
        size=len(content),
        content_type=file.content_type or "application/octet-stream",
        path=str(stored_path),
        sha256=digest,
        created_at=created_at,
    )

    job_id = str(uuid.uuid4())
    create_job(job_id, title="nexus_extract", message="queued", document_count=1)
    append_job_event(
        job_id,
        "queued",
        {
            "status": "queued",
            "progress": 0.0,
            "message": "queued",
            "document_id": document_id,
            "path": str(stored_path),
        },
    )

    worker = threading.Thread(
        target=_extract_and_index,
        args=(document_id, stored_path, safe_filename, job_id),
        daemon=True,
    )
    worker.start()

    return {
        "job_id": job_id,
        "status": "queued",
        "document": {
            "id": document_id,
            "project": project,
            "filename": safe_filename,
            "size": len(content),
            "content_type": file.content_type or "application/octet-stream",
            "sha256": digest,
            "created_at": created_at,
        },
    }
