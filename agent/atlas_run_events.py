from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent.atlas_run_schema import AtlasRunEvent


def validate_run_storage_id(value: str, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    if "/" in text or "\\" in text or ".." in text:
        raise ValueError(f"{field_name} contains unsafe path segments: {text}")
    return text


def run_dir(root_dir: str | Path, run_id: str) -> Path:
    safe_run_id = validate_run_storage_id(run_id, "run_id")
    return Path(root_dir) / "atlas" / "runs" / safe_run_id


class AtlasRunEventLog:
    def __init__(self, root_dir: str | Path):
        self.root_dir = Path(root_dir)

    def events_path(self, run_id: str) -> Path:
        return run_dir(self.root_dir, run_id) / "events.ndjson"

    def append_event(self, event: AtlasRunEvent | dict[str, Any]) -> AtlasRunEvent:
        payload = event.model_dump() if isinstance(event, AtlasRunEvent) else dict(event or {})
        run_id = validate_run_storage_id(str(payload.get("run_id") or ""), "run_id")
        pool_id = validate_run_storage_id(str(payload.get("pool_id") or ""), "pool_id")
        path = self.events_path(run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        sequence = self._next_sequence(path)
        payload = {
            **payload,
            "run_id": run_id,
            "pool_id": pool_id,
            "sequence": sequence,
        }
        record = AtlasRunEvent(**payload)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.model_dump(), ensure_ascii=False) + "\n")
        return record

    def read_events(self, run_id: str, *, after_sequence: int = 0, limit: int | None = None) -> list[AtlasRunEvent]:
        path = self.events_path(run_id)
        if not path.exists():
            return []
        rows = [
            AtlasRunEvent(**json.loads(line))
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if after_sequence:
            rows = [row for row in rows if int(row.sequence) > int(after_sequence)]
        if limit is not None:
            rows = rows[-max(1, int(limit)) :]
        return rows

    @staticmethod
    def _next_sequence(path: Path) -> int:
        if not path.exists():
            return 1
        try:
            return len([line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]) + 1
        except Exception:
            return 1

