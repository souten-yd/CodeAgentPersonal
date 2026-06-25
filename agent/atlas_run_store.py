from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from agent.atlas_run_events import AtlasRunEventLog, run_dir, validate_run_storage_id
from agent.atlas_run_schema import AtlasRunEvent, AtlasRunState, TERMINAL_RUN_STATUSES
from agent.atlas_time_utils import utc_now_iso


class AtlasRunStore:
    def __init__(self, root_dir: str | Path):
        self.root_dir = Path(root_dir)
        self.events = AtlasRunEventLog(root_dir)

    def create_run(
        self,
        *,
        pool_id: str,
        workspace_id: str = "default",
        mode: str = "fresh",
        run_id: str = "",
        total_items: int = 0,
        metadata: dict | None = None,
    ) -> AtlasRunState:
        safe_pool_id = validate_run_storage_id(pool_id, "pool_id")
        safe_workspace_id = validate_run_storage_id(workspace_id or "default", "workspace_id")
        safe_run_id = validate_run_storage_id(run_id, "run_id") if run_id else f"atlas_run_{uuid4().hex[:12]}"
        state = AtlasRunState(
            run_id=safe_run_id,
            pool_id=safe_pool_id,
            workspace_id=safe_workspace_id,
            mode=str(mode or "fresh"),
            total_items=max(0, int(total_items or 0)),
            metadata=dict(metadata or {}),
        )
        self.save_state(state)
        self.append_event(
            state.run_id,
            event_type="run_created",
            phase=state.phase,
            status=state.status,
            message="Atlas backend run created.",
        )
        return state

    def state_path(self, run_id: str) -> Path:
        return run_dir(self.root_dir, run_id) / "state.json"

    def save_state(self, state: AtlasRunState) -> AtlasRunState:
        state.updated_at = utc_now_iso()
        if state.status in TERMINAL_RUN_STATUSES and not state.finished_at:
            state.finished_at = state.updated_at
        path = self.state_path(state.run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        return state

    def load_state(self, run_id: str) -> AtlasRunState:
        path = self.state_path(run_id)
        return AtlasRunState(**json.loads(path.read_text(encoding="utf-8")))

    def patch_state(self, run_id: str, patch: dict, *, heartbeat_only: bool = False) -> AtlasRunState:
        state = self.load_state(run_id)
        if heartbeat_only and state.status in TERMINAL_RUN_STATUSES:
            return state
        next_payload = state.model_dump()
        for key, value in dict(patch or {}).items():
            if key in {"run_id", "pool_id", "created_at", "finished_at"}:
                continue
            if key in next_payload:
                next_payload[key] = value
        next_state = AtlasRunState(**next_payload)
        return self.save_state(next_state)

    def append_event(
        self,
        run_id: str,
        *,
        event_type: str,
        phase: str = "",
        status: str = "",
        item_id: str = "",
        message: str = "",
        source: str = "backend",
        metadata: dict | None = None,
    ) -> AtlasRunEvent:
        state = self.load_state(run_id)
        return self.events.append_event(
            {
                "run_id": state.run_id,
                "pool_id": state.pool_id,
                "event_type": event_type,
                "phase": phase or state.phase,
                "status": status or state.status,
                "item_id": item_id,
                "message": message,
                "source": source,
                "metadata": dict(metadata or {}),
            }
        )

    def read_events(self, run_id: str, *, after_sequence: int = 0, limit: int | None = None) -> list[AtlasRunEvent]:
        return self.events.read_events(run_id, after_sequence=after_sequence, limit=limit)

