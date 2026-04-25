from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.nexus.ingest import accept_upload


nexus_router = APIRouter()


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


# 既存インポート互換
router = nexus_router
