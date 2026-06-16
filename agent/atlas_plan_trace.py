from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


from agent.atlas_time_utils import utc_now_iso as _utc_now_iso


def _detail_enabled() -> bool:
    return os.environ.get("ATLAS_PLAN_TRACE") == "1" or os.environ.get("KASANE_DEBUG_TEST_HARNESS") == "1"


class PlanTrace:
    def __init__(
        self,
        *,
        data_root: str | Path,
        pool_id: str,
        run_id: str,
        detail_enabled: bool | None = None,
    ) -> None:
        self.data_root = Path(data_root)
        self.pool_id = _safe_id(pool_id)
        self.run_id = _safe_id(run_id)
        self.detail_enabled = _detail_enabled() if detail_enabled is None else bool(detail_enabled)
        self.records: list[dict[str, Any]] = []

    @property
    def path(self) -> Path:
        return self.data_root / "atlas" / "plan_traces" / self.pool_id / f"{self.run_id}.jsonl"

    def record(self, *, stage: str, decision: str, reason: str, detail: dict[str, Any] | None = None) -> dict[str, Any]:
        rec: dict[str, Any] = {
            "timestamp": _utc_now_iso(),
            "pool_id": self.pool_id,
            "run_id": self.run_id,
            "stage": str(stage or ""),
            "decision": str(decision or ""),
            "reason": str(reason or ""),
        }
        if self.detail_enabled and detail:
            rec["detail"] = _mask_detail(detail)
        self.records.append(rec)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec

    def to_journal(self, journal) -> None:
        if not self.records:
            return
        for rec in self.records:
            journal.append_event(
                self.pool_id,
                self.run_id,
                {
                    "event_type": "plan_trace",
                    "pool_id": self.pool_id,
                    "run_id": self.run_id,
                    "stage": rec.get("stage", ""),
                    "decision": rec.get("decision", ""),
                    "reason": rec.get("reason", ""),
                    "detail": rec.get("detail", {}),
                    "created_at": rec.get("timestamp", _utc_now_iso()),
                },
            )


def read_plan_trace(data_root: str | Path, *, pool_id: str, run_id: str) -> list[dict[str, Any]]:
    path = Path(data_root) / "atlas" / "plan_traces" / _safe_id(pool_id) / f"{_safe_id(run_id)}.jsonl"
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def summarize_root_cause(records: list[dict[str, Any]]) -> dict[str, str]:
    for rec in records:
        decision = str(rec.get("decision") or "").lower()
        reason = str(rec.get("reason") or "")
        if decision in {"fallback", "empty", "block", "blocked", "failed"}:
            return {
                "root_cause_stage": str(rec.get("stage") or ""),
                "root_cause_reason": reason,
            }
    return {"root_cause_stage": "", "root_cause_reason": ""}


def _safe_id(value: str) -> str:
    candidate = str(value or "").strip()
    if not candidate or "/" in candidate or "\\" in candidate or ".." in candidate:
        raise ValueError("unsafe plan trace id")
    return candidate


def _mask_detail(detail: dict[str, Any]) -> dict[str, Any]:
    masked: dict[str, Any] = {}
    for key, value in dict(detail or {}).items():
        key_s = str(key)
        if any(token in key_s.lower() for token in ("secret", "password", "credential", "token")):
            masked[key_s] = "[masked]"
        elif isinstance(value, str):
            masked[key_s] = value[:1000]
        else:
            masked[key_s] = value
    return masked
