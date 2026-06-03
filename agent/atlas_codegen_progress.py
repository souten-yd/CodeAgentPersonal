from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_dir(data_root: str | Path, pool_id: str) -> Path:
    return Path(data_root) / "atlas" / "autonomous_codegen" / str(pool_id)


def _progress_path(data_root: str | Path, pool_id: str, run_id: str) -> Path:
    return _run_dir(data_root, pool_id) / f"{run_id}.progress.json"


def write_progress(data_root: str | Path, pool_id: str, run_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    root = _run_dir(data_root, pool_id)
    root.mkdir(parents=True, exist_ok=True)
    path = _progress_path(data_root, pool_id, run_id)
    current = read_progress(data_root, pool_id, run_id)
    now = _now_iso()
    data = {
        "phase": "",
        "current_item_index": 0,
        "total_items": 0,
        "sub_phase": "",
        "attempt": 0,
        "started_at": current.get("started_at") or now,
        "heartbeat_at": now,
        "last_event": "",
        "waiting_on_model_seconds": 0,
        "stop_requested": False,
        **current,
        **dict(patch or {}),
        "heartbeat_at": now,
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return data


def read_progress(data_root: str | Path, pool_id: str, run_id: str) -> dict[str, Any]:
    path = _progress_path(data_root, pool_id, run_id)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def request_stop(data_root: str | Path, pool_id: str, run_id: str, *, reason: str = "user_stop_requested") -> dict[str, Any]:
    progress = read_progress(data_root, pool_id, run_id)
    target_run_id = run_id
    if not progress:
        for path in _run_dir(data_root, pool_id).glob("*.progress.json"):
            candidate = read_progress(data_root, pool_id, path.name.removesuffix(".progress.json"))
            if str(candidate.get("run_id") or "") == run_id or str(candidate.get("orchestrator_run_id") or "") == run_id:
                progress = candidate
                target_run_id = path.name.removesuffix(".progress.json")
                break
    return write_progress(
        data_root,
        pool_id,
        target_run_id,
        {
            **progress,
            "run_id": progress.get("run_id") or run_id,
            "orchestrator_run_id": progress.get("orchestrator_run_id") or target_run_id,
            "stop_requested": True,
            "stop_reason": reason,
            "last_event": "stop_requested",
        },
    )


def is_stop_requested(data_root: str | Path, pool_id: str, run_id: str) -> bool:
    return bool(read_progress(data_root, pool_id, run_id).get("stop_requested"))
