from __future__ import annotations

from fastapi import APIRouter


nexus_router = APIRouter()


@nexus_router.get("/health")
def nexus_health() -> dict[str, str]:
    """Nexus ルーターの疎通確認用エンドポイント。"""
    return {"status": "ok"}


# 既存インポート互換
router = nexus_router
