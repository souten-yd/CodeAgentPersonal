from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.nexus.evidence import build_library_evidence
from app.nexus.export import nexus_export_router
from app.nexus.ingest import accept_upload
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
