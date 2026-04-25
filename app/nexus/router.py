from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.nexus.db import get_conn
from app.nexus.evidence import build_library_evidence
from app.nexus.export import nexus_export_router
from app.nexus.ingest import accept_upload
from app.nexus.jobs import get_job, get_job_events, list_active_jobs
from app.nexus.report import nexus_report_router
from app.nexus.search import search_evidence


nexus_router = APIRouter()


class NexusSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=10, ge=1, le=100)
    as_evidence: bool = False


@nexus_router.get("/health")
def nexus_health() -> dict[str, str]:
    """Nexus ルーターの疎通確認用エンドポイント。"""
    return {"status": "ok"}


@nexus_router.get("/dashboard/summary")
def nexus_dashboard_summary(project: str = Query("default")) -> dict[str, int]:
    """Dashboardカード表示向けのサマリー。"""
    with get_conn() as conn:
        docs_row = conn.execute(
            "SELECT COUNT(*) AS c FROM nexus_documents WHERE project = ?",
            (project,),
        ).fetchone()
        chunks_row = conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM nexus_chunks c
            JOIN nexus_documents d ON d.id = c.document_id
            WHERE d.project = ?
            """,
            (project,),
        ).fetchone()
        reports_row = conn.execute(
            "SELECT COUNT(*) AS c FROM nexus_reports WHERE project = ?",
            (project,),
        ).fetchone()

    active_jobs = sum(1 for job in list_active_jobs(limit=500) if job.status in ("queued", "running"))
    return {
        "documents": int(docs_row["c"] if docs_row else 0),
        "chunks": int(chunks_row["c"] if chunks_row else 0),
        "reports": int(reports_row["c"] if reports_row else 0),
        "active_jobs": active_jobs,
    }


@nexus_router.get("/library/documents")
def nexus_list_documents(
    project: str = Query("default"),
    q: str = Query(""),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    """Library文書一覧（検索つき）。"""
    keyword = q.strip().lower()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT d.id, d.project, d.filename, d.size, d.content_type, d.path, d.sha256, d.created_at,
                   COALESCE(COUNT(c.chunk_id), 0) AS chunk_count
            FROM nexus_documents d
            LEFT JOIN nexus_chunks c ON c.document_id = d.id
            WHERE d.project = ?
            GROUP BY d.id
            ORDER BY d.created_at DESC
            LIMIT ?
            """,
            (project, limit),
        ).fetchall()

    documents: list[dict] = []
    for row in rows:
        filename = str(row["filename"] or "")
        if keyword and keyword not in filename.lower():
            continue
        documents.append(
            {
                "id": row["id"],
                "project": row["project"],
                "filename": filename,
                "size": int(row["size"] or 0),
                "content_type": row["content_type"],
                "created_at": row["created_at"],
                "chunk_count": int(row["chunk_count"] or 0),
            }
        )
    return {"documents": documents}


@nexus_router.delete("/library/documents/{document_id}")
def nexus_delete_document(document_id: str, project: str = Query("default")) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, path FROM nexus_documents WHERE id = ? AND project = ?",
            (document_id, project),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="document not found")

        conn.execute("DELETE FROM nexus_documents WHERE id = ?", (document_id,))
        conn.commit()

    path = Path(str(row["path"]))
    try:
        if path.exists():
            path.unlink()
        parent = path.parent
        if parent.exists() and parent.name == document_id:
            parent.rmdir()
    except OSError:
        # DB削除を優先し、ファイル削除失敗は非致命扱い
        pass

    return {"ok": True, "document_id": document_id}


@nexus_router.get("/library/documents/{document_id}/download")
def nexus_download_document(document_id: str, project: str = Query("default")) -> FileResponse:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT filename, path FROM nexus_documents WHERE id = ? AND project = ?",
            (document_id, project),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="document not found")

    path = Path(str(row["path"]))
    if not path.exists():
        raise HTTPException(status_code=404, detail="file missing")

    return FileResponse(path, filename=str(row["filename"]))


@nexus_router.get("/jobs/active")
def nexus_active_jobs(limit: int = Query(50, ge=1, le=500)) -> dict:
    jobs = [job.model_dump(mode="json") for job in list_active_jobs(limit=limit)]
    return {"jobs": jobs}


@nexus_router.get("/jobs/{job_id}")
def nexus_job_status(job_id: str) -> dict:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return {"job": job.model_dump(mode="json")}


@nexus_router.get("/jobs/{job_id}/events")
def nexus_job_events(job_id: str, after: int = Query(-1)) -> dict:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")

    events = [event.model_dump(mode="json") for event in get_job_events(job_id, after=after)]
    return {"job_id": job_id, "events": events}


@nexus_router.post("/upload")
async def nexus_upload(file: UploadFile = File(...), project: str = Form("default")) -> dict:
    """アップロードを受け付け、抽出ジョブをバックグラウンドで開始する。"""
    try:
        return await accept_upload(file=file, project=project)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@nexus_router.post("/search")
def nexus_search(payload: NexusSearchRequest) -> dict:
    """FTS5 + BM25 でライブラリ内チャンクを検索する。"""
    query = payload.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="query must not be empty")

    results = search_evidence(query=query, top_k=payload.top_k)
    response: dict = {"query": query, "top_k": payload.top_k, "results": results}
    if payload.as_evidence:
        response["evidence"] = [asdict(item) for item in build_library_evidence(results)]
    return response


# 既存インポート互換
router = nexus_router

nexus_router.include_router(nexus_report_router)
nexus_router.include_router(nexus_export_router)
