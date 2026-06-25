from __future__ import annotations

from pathlib import Path

from agent.atlas_run_events import validate_run_storage_id
from agent.atlas_run_locks import is_lease_stale
from agent.atlas_run_store import AtlasRunStore


def recover_stale_runs(root_dir: str | Path, *, stale_after_seconds: int = 900) -> dict:
    store = AtlasRunStore(root_dir)
    recovered: list[dict] = []
    runs_root = Path(root_dir) / "atlas" / "runs"
    if not runs_root.exists():
        return {"recovered": recovered, "count": 0}
    for state_path in sorted(runs_root.glob("*/state.json")):
        run_id = state_path.parent.name
        try:
            safe_run_id = validate_run_storage_id(run_id, "run_id")
            state = store.load_state(safe_run_id)
        except Exception:  # noqa: BLE001
            continue
        if not is_lease_stale(state, stale_after_seconds=stale_after_seconds):
            continue
        blocked = store.patch_state(
            state.run_id,
            {
                "status": "blocked",
                "phase": state.phase or "planning",
                "requires_user_action": True,
                "block_reason": "stale_run_recovered_after_restart",
                "next_actions": ["retry", "inspect_events"],
                "lease_owner": "",
                "lease_expires_at": "",
            },
        )
        event = store.append_event(
            state.run_id,
            event_type="run_recovered_stale",
            phase=blocked.phase,
            status=blocked.status,
            message="Stale queued/running run marked blocked for inspection and retry.",
            metadata={
                "previous_status": state.status,
                "previous_phase": state.phase,
                "previous_lease_owner": state.lease_owner,
                "worker_heartbeat_at": state.worker_heartbeat_at,
                "lease_expires_at": state.lease_expires_at,
                "next_actions": blocked.next_actions,
            },
        )
        recovered.append({"run_id": state.run_id, "state": blocked.model_dump(), "event": event.model_dump()})
    return {"recovered": recovered, "count": len(recovered)}
