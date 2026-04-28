from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import Any, cast

from app.nexus.db import get_conn
from app.nexus.schemas import JobStatus, NexusJob, NexusJobEvent

logger = logging.getLogger(__name__)
_EVENT_APPEND_LOCK = threading.RLock()


ACTIVE_STATUSES: tuple[JobStatus, ...] = ("queued", "running")
_VALID_JOB_STATUSES = {"queued", "running", "completed", "failed", "degraded"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_event_status(value: Any) -> JobStatus | None:
    if value is None:
        return None
    raw = str(value).strip().lower()
    if not raw:
        return None
    if raw in _VALID_JOB_STATUSES:
        return cast(JobStatus, raw)
    return "running"


def _row_to_job(row: Any) -> NexusJob:
    return NexusJob(
        job_id=row["job_id"],
        status=row["status"],
        progress=float(row["progress"] or 0.0),
        message=row["message"],
        error=row["error"],
        created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
        updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
    )


def create_job(
    job_id: str,
    *,
    title: str | None = None,
    message: str | None = None,
    document_count: int = 0,
    status: JobStatus = "queued",
    error: str | None = None,
) -> NexusJob:
    now = _now_iso()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO nexus_jobs(job_id, status, title, message, error, document_count, created_at, updated_at)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (job_id, status, title, message, error, max(0, document_count), now, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM nexus_jobs WHERE job_id = ?", (job_id,)).fetchone()
    if row is None:
        raise ValueError(f"job not found after create: {job_id}")
    return _row_to_job(row)


def ensure_job_exists(
    job_id: str,
    *,
    title: str | None = None,
    message: str | None = None,
    status: JobStatus = "queued",
) -> NexusJob:
    existing = get_job(job_id)
    if existing is not None:
        return existing
    try:
        return create_job(job_id, title=title, message=message, status=status)
    except Exception:  # noqa: BLE001
        fallback = get_job(job_id)
        if fallback is None:
            raise
        return fallback


def update_job(
    job_id: str,
    *,
    status: JobStatus | None = None,
    progress: float | None = None,
    message: str | None = None,
    error: str | None = None,
    document_count: int | None = None,
) -> NexusJob:
    assignments: list[str] = ["updated_at = ?"]
    params: list[Any] = [_now_iso()]

    if status is not None:
        assignments.append("status = ?")
        params.append(status)
    if progress is not None:
        assignments.append("progress = ?")
        params.append(max(0.0, min(1.0, float(progress))))
    if message is not None:
        assignments.append("message = ?")
        params.append(message)
    if error is not None:
        assignments.append("error = ?")
        params.append(error)
    if document_count is not None:
        assignments.append("document_count = ?")
        params.append(max(0, document_count))

    params.append(job_id)

    with get_conn() as conn:
        cur = conn.execute(
            f"UPDATE nexus_jobs SET {', '.join(assignments)} WHERE job_id = ?",
            params,
        )
        if cur.rowcount == 0:
            raise ValueError(f"job not found: {job_id}")
        conn.commit()
        row = conn.execute("SELECT * FROM nexus_jobs WHERE job_id = ?", (job_id,)).fetchone()

    if row is None:
        raise ValueError(f"job not found after update: {job_id}")
    return _row_to_job(row)


def get_job(job_id: str) -> NexusJob | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM nexus_jobs WHERE job_id = ?", (job_id,)).fetchone()
    if row is None:
        return None
    return _row_to_job(row)


def list_active_jobs(limit: int = 100) -> list[NexusJob]:
    safe_limit = max(1, min(500, limit))
    placeholders = ", ".join("?" for _ in ACTIVE_STATUSES)
    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT *
            FROM nexus_jobs
            WHERE status IN ({placeholders})
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            [*ACTIVE_STATUSES, safe_limit],
        ).fetchall()
    return [_row_to_job(row) for row in rows]


def append_job_event(job_id: str, event_type: str, data: dict[str, Any]) -> NexusJobEvent:
    now = _now_iso()
    raw_status = data.get("status")
    normalized_status = _normalize_event_status(raw_status)
    should_preserve_original = (
        raw_status is not None and str(raw_status).strip().lower() not in _VALID_JOB_STATUSES
    )
    normalized_data = {
        "status": normalized_status,
        "progress": data.get("progress"),
        "message": data.get("message"),
        "error": data.get("error"),
        "updated_at": data.get("updated_at") or now,
        **data,
    }
    normalized_data["status"] = normalized_status
    if should_preserve_original:
        normalized_data["original_status"] = raw_status
    auto_recovery_info: dict[str, Any] | None = None
    with _EVENT_APPEND_LOCK:
        for attempt in range(3):
            try:
                with get_conn() as conn:
                    conn.execute("BEGIN IMMEDIATE")
                    job_row = conn.execute("SELECT 1 FROM nexus_jobs WHERE job_id = ?", (job_id,)).fetchone()
                    if job_row is None:
                        created_at = _now_iso()
                        auto_recovery_info = {
                            "reason": "missing_parent_job_auto_recovered",
                            "job_id": job_id,
                            "event_type": event_type,
                            "created_at": created_at,
                        }
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO nexus_jobs(
                                job_id, status, title, message, error, document_count, created_at, updated_at
                            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                job_id,
                                "running",
                                "auto_recovered_job",
                                "auto-created for event",
                                "",
                                0,
                                created_at,
                                created_at,
                            ),
                        )
                        logger.warning("append_job_event auto-recovered missing parent job: %s", auto_recovery_info)

                    if auto_recovery_info is not None:
                        normalized_data["auto_recovery_warning"] = auto_recovery_info
                    encoded = json.dumps(normalized_data, ensure_ascii=False)

                    next_seq_row = conn.execute(
                        "SELECT COALESCE(MAX(seq), -1) + 1 AS next_seq FROM nexus_job_events WHERE job_id = ?",
                        (job_id,),
                    ).fetchone()
                    seq = int(next_seq_row["next_seq"]) if next_seq_row is not None else 0

                    conn.execute(
                        """
                        INSERT INTO nexus_job_events(job_id, seq, type, data, ts)
                        VALUES(?, ?, ?, ?, ?)
                        """,
                        (job_id, seq, event_type, encoded, now),
                    )
                    conn.commit()
                    break
            except sqlite3.IntegrityError as exc:
                if "nexus_job_events.job_id" not in str(exc) or "seq" not in str(exc) or attempt >= 2:
                    raise
                time.sleep(0.01 * (attempt + 1))

    updated_raw = normalized_data.get("updated_at")
    updated_at = datetime.fromisoformat(now)
    if isinstance(updated_raw, str):
        try:
            updated_at = datetime.fromisoformat(updated_raw)
        except ValueError:
            updated_at = datetime.fromisoformat(now)

    return NexusJobEvent(
        seq=seq,
        type=event_type,
        data=normalized_data,
        ts=datetime.fromisoformat(now),
        status=normalized_status,
        progress=normalized_data.get("progress"),
        message=normalized_data.get("message"),
        updated_at=updated_at,
    )


def append_job_heartbeat(
    job_id: str,
    phase: str,
    message: str,
    progress: float | None = None,
    details: dict[str, Any] | None = None,
) -> NexusJobEvent:
    now = _now_iso()
    payload: dict[str, Any] = {
        "status": "running",
        "phase": str(phase or "").strip() or "running",
        "message": str(message or "").strip() or "running",
        "progress": progress,
        "heartbeat_at": now,
        "updated_at": now,
        "details": details or {},
    }
    event = append_job_event(job_id, "heartbeat", payload)
    update_job(
        job_id,
        status="running",
        progress=progress,
        message=payload["message"],
    )
    return event


def get_job_events(job_id: str, after: int = -1) -> list[NexusJobEvent]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT seq, type, data, ts
            FROM nexus_job_events
            WHERE job_id = ? AND seq > ?
            ORDER BY seq ASC
            """,
            (job_id, after),
        ).fetchall()

    events: list[NexusJobEvent] = []
    for row in rows:
        payload = json.loads(row["data"]) if row["data"] else {}
        raw_status = payload.get("status")
        normalized_status = _normalize_event_status(raw_status)
        if raw_status is not None and str(raw_status).strip().lower() not in _VALID_JOB_STATUSES:
            payload["original_status"] = raw_status
            payload["status"] = normalized_status
        ts = datetime.fromisoformat(row["ts"]) if row["ts"] else None
        updated_raw = payload.get("updated_at")
        updated_at = None
        if isinstance(updated_raw, str) and updated_raw:
            try:
                updated_at = datetime.fromisoformat(updated_raw)
            except ValueError:
                updated_at = ts
        else:
            updated_at = ts
        events.append(
            NexusJobEvent(
                seq=int(row["seq"]),
                type=row["type"],
                data=payload,
                ts=ts,
                status=normalized_status,
                progress=payload.get("progress"),
                message=payload.get("message"),
                updated_at=updated_at,
            )
        )
    return events
