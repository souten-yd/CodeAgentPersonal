from __future__ import annotations

from typing import Any

from agent.atlas_run_schema import AtlasRunState


_RUNNABLE_ITEM_STATUSES = {"", "queued", "pending", "ready", "approval_required", "approved"}
_RERUN_ITEM_STATUSES = {*_RUNNABLE_ITEM_STATUSES, "completed"}


def select_run_items(pool: Any, state: AtlasRunState, mode: str, requested_item_id: str = "") -> list[str]:
    requested = str(requested_item_id or "").strip()
    normalized_mode = str(mode or "fresh").strip() or "fresh"
    if requested:
        item = _get_item(pool, requested)
        if item is None:
            raise ValueError(f"item_not_found:{requested}")
        if not _is_runnable_item(item, allow_completed=normalized_mode == "rerun"):
            raise ValueError(f"item_not_runnable:{requested}:{_item_status(item)}")
        return [requested]

    completed = _completed_item_ids(pool, state)
    selected: list[str] = []
    for item in getattr(pool, "items", []) or []:
        item_id = str(getattr(item, "item_id", "") or getattr(item, "id", "") or "").strip()
        if not item_id:
            continue
        if normalized_mode == "resume" and item_id in completed:
            continue
        if normalized_mode != "rerun" and not _is_runnable_item(item, allow_completed=False):
            continue
        if normalized_mode == "rerun" and not _is_runnable_item(item, allow_completed=True):
            continue
        selected.append(item_id)
    return selected


def _get_item(pool: Any, item_id: str) -> Any:
    if hasattr(pool, "get_item"):
        return pool.get_item(item_id)
    for item in getattr(pool, "items", []) or []:
        if str(getattr(item, "item_id", "") or getattr(item, "id", "") or "") == item_id:
            return item
    return None


def _is_runnable_item(item: Any, *, allow_completed: bool) -> bool:
    statuses = _RERUN_ITEM_STATUSES if allow_completed else _RUNNABLE_ITEM_STATUSES
    return _item_status(item) in statuses


def _item_status(item: Any) -> str:
    return str(getattr(item, "status", "") or "").strip().lower()


def _completed_item_ids(pool: Any, state: AtlasRunState) -> set[str]:
    completed = {str(item_id) for item_id in (state.completed_item_ids or []) if str(item_id)}
    for item_id in getattr(pool, "completed_item_ids", []) or []:
        if str(item_id):
            completed.add(str(item_id))
    for item in getattr(pool, "items", []) or []:
        item_id = str(getattr(item, "item_id", "") or getattr(item, "id", "") or "").strip()
        if not item_id:
            continue
        metadata = getattr(item, "metadata", {}) if isinstance(getattr(item, "metadata", {}), dict) else {}
        changed_files = ((metadata.get("safe_apply") or {}).get("changed_files") or [])
        if _item_status(item) == "completed" or changed_files:
            completed.add(item_id)
    return completed
