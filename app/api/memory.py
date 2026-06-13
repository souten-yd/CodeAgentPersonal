"""Memory API router (extracted from main.py).

Thin HTTP wrappers over the memory helpers that still live in ``main`` (``memory_search``,
``memory_get_all``, ``memory_save``, ``memory_delete``, ``_analyze_job_for_memory``). They are
imported lazily inside each handler because they are defined late in ``main.py``; see
docs/MAINTAINABILITY_PLAN.md.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["memory"])


@router.get("/memory")
def list_memory(q: str = ""):
    """メモリ一覧 or キーワード検索"""
    from main import memory_get_all, memory_search
    if q.strip():
        entries = memory_search(q.strip(), limit=50)
    else:
        entries = memory_get_all()
    return {"entries": entries, "count": len(entries)}


@router.post("/memory")
def create_memory(req: dict):
    from main import memory_save
    if not req.get("title") or not req.get("content"):
        raise HTTPException(400, "title and content required")
    mid = memory_save(req)
    return {"ok": True, "id": mid}


@router.put("/memory/{mid}")
def update_memory(mid: str, req: dict):
    from main import memory_save
    req["id"] = mid
    memory_save(req)
    return {"ok": True}


@router.delete("/memory/{mid}")
def delete_memory_api(mid: str):
    from main import memory_delete
    memory_delete(mid)
    return {"ok": True}


@router.post("/memory/analyze/{job_id}")
def trigger_memory_analysis(job_id: str, project: str = "default"):
    """指定ジョブのログからメモリを抽出（手動トリガー）"""
    import threading as _t

    from main import LLM_URL, _analyze_job_for_memory
    _t.Thread(target=_analyze_job_for_memory, args=(job_id, project, LLM_URL), daemon=True).start()
    return {"ok": True, "message": f"memory analysis triggered for job {job_id}"}
