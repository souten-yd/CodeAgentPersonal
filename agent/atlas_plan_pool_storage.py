from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_target_contract import compatibility_fill_plan_pool_payload


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _model_dump(model: Any) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def _model_validate(model_type: type[AtlasPlanPool], payload: dict[str, Any]) -> AtlasPlanPool:
    if hasattr(model_type, "model_validate"):
        return model_type.model_validate(payload)
    return model_type(**payload)


class AtlasPlanPoolStorage:
    def __init__(self, root_dir: Path | str):
        self.root_dir = Path(root_dir)
        self.plan_pools_dir = self.root_dir / "atlas" / "plan_pools"

    def pool_path(self, pool_id: str) -> Path:
        self._validate_storage_id(pool_id, "pool_id")
        return self.plan_pools_dir / f"{pool_id}.json"

    def save_pool(self, pool: AtlasPlanPool) -> Path:
        path = self.pool_path(pool.pool_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(_model_dump(pool), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    def load_pool(self, pool_id: str) -> AtlasPlanPool:
        path = self.pool_path(pool_id)
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload = compatibility_fill_plan_pool_payload(payload)
        return _model_validate(AtlasPlanPool, payload)

    def exists(self, pool_id: str) -> bool:
        return self.pool_path(pool_id).exists()

    def list_pool_ids(self) -> list[str]:
        if not self.plan_pools_dir.exists():
            return []
        return sorted(path.stem for path in self.plan_pools_dir.glob("*.json") if path.is_file())

    def update_pool(self, pool: AtlasPlanPool, **updates: Any) -> AtlasPlanPool:
        for field_name, value in updates.items():
            self._ensure_model_field(pool, field_name)
            setattr(pool, field_name, value)
        pool.updated_at = _utc_now_iso()
        payload = _model_dump(pool)
        updated_pool = _model_validate(AtlasPlanPool, payload)
        self.save_pool(updated_pool)
        return updated_pool

    def update_item(self, pool_id: str, item_id: str, **updates: Any) -> AtlasPlanPool:
        self._validate_storage_id(item_id, "item_id")
        pool = self.load_pool(pool_id)
        item = pool.get_item(item_id)
        if item is None:
            raise KeyError(f"item_id not found: {item_id}")
        for field_name, value in updates.items():
            self._ensure_model_field(item, field_name)
            setattr(item, field_name, value)
        item.updated_at = _utc_now_iso()
        pool.updated_at = _utc_now_iso()
        updated_pool = _model_validate(AtlasPlanPool, _model_dump(pool))
        self.save_pool(updated_pool)
        return updated_pool

    def append_item(self, pool_id: str, item: AtlasPlanItem) -> AtlasPlanPool:
        self._validate_storage_id(item.item_id, "item_id")
        pool = self.load_pool(pool_id)
        if item.pool_id != pool.pool_id:
            raise ValueError(f"item.pool_id must match pool.pool_id: {item.pool_id} != {pool.pool_id}")
        if item.item_id in pool.item_ids():
            raise ValueError(f"duplicate item_id: {item.item_id}")
        pool.items.append(item)
        pool.updated_at = _utc_now_iso()
        updated_pool = _model_validate(AtlasPlanPool, _model_dump(pool))
        self.save_pool(updated_pool)
        return updated_pool

    def mark_item_completed(self, pool_id: str, item_id: str) -> AtlasPlanPool:
        pool, item = self._load_pool_and_item(pool_id, item_id)
        item.status = "completed"
        self._add_unique(pool.completed_item_ids, item_id)
        self._remove_from_lists(item_id, pool.failed_item_ids, pool.blocked_item_ids, pool.skipped_item_ids)
        if pool.current_item_id == item_id:
            pool.current_item_id = ""
        item.updated_at = _utc_now_iso()
        pool.updated_at = _utc_now_iso()
        updated_pool = _model_validate(AtlasPlanPool, _model_dump(pool))
        self.save_pool(updated_pool)
        return updated_pool

    def mark_item_failed(self, pool_id: str, item_id: str, error: str = "") -> AtlasPlanPool:
        pool, item = self._load_pool_and_item(pool_id, item_id)
        item.status = "failed"
        self._add_unique(pool.failed_item_ids, item_id)
        self._remove_from_lists(item_id, pool.completed_item_ids, pool.blocked_item_ids, pool.skipped_item_ids)
        if error:
            item.errors.append(error)
        item.updated_at = _utc_now_iso()
        pool.updated_at = _utc_now_iso()
        updated_pool = _model_validate(AtlasPlanPool, _model_dump(pool))
        self.save_pool(updated_pool)
        return updated_pool

    def mark_item_blocked(self, pool_id: str, item_id: str, reason: str = "") -> AtlasPlanPool:
        pool, item = self._load_pool_and_item(pool_id, item_id)
        item.status = "blocked"
        self._add_unique(pool.blocked_item_ids, item_id)
        self._remove_from_lists(item_id, pool.completed_item_ids, pool.failed_item_ids, pool.skipped_item_ids)
        if reason:
            item.warnings.append(reason)
        item.updated_at = _utc_now_iso()
        pool.updated_at = _utc_now_iso()
        updated_pool = _model_validate(AtlasPlanPool, _model_dump(pool))
        self.save_pool(updated_pool)
        return updated_pool

    def _load_pool_and_item(self, pool_id: str, item_id: str) -> tuple[AtlasPlanPool, AtlasPlanItem]:
        self._validate_storage_id(item_id, "item_id")
        pool = self.load_pool(pool_id)
        item = pool.get_item(item_id)
        if item is None:
            raise KeyError(f"item_id not found: {item_id}")
        return pool, item

    @staticmethod
    def _validate_storage_id(value: str, field_name: str) -> None:
        if "/" in value or "\\" in value or ".." in value:
            raise ValueError(f"invalid {field_name}: path traversal tokens are not allowed")

    @staticmethod
    def _model_fields(model: Any) -> set[str]:
        model_type = model.__class__
        if hasattr(model_type, "model_fields"):
            return set(model_type.model_fields)
        return set(model_type.__fields__)

    @classmethod
    def _ensure_model_field(cls, model: Any, field_name: str) -> None:
        if field_name not in cls._model_fields(model):
            raise ValueError(f"unknown field for {model.__class__.__name__}: {field_name}")

    @staticmethod
    def _add_unique(values: list[str], value: str) -> None:
        if value not in values:
            values.append(value)

    @staticmethod
    def _remove_from_lists(value: str, *lists: list[str]) -> None:
        for values in lists:
            while value in values:
                values.remove(value)
