from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.nexus.db import get_conn
from app.nexus.schemas import JobStatus, NexusJob, NexusJobEvent


ACTIVE_STATUSES: tuple[JobStatus, ...] = ("queued", "running")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    normalized_data = {
        "status": data.get("status"),
        "progress": data.get("progress"),
        "message": data.get("message"),
        "error": data.get("error"),
        "updated_at": data.get("updated_at") or now,
        **data,
    }
    encoded = json.dumps(normalized_data, ensure_ascii=False)
    with get_conn() as conn:
        job_row = conn.execute("SELECT 1 FROM nexus_jobs WHERE job_id = ?", (job_id,)).fetchone()
        if job_row is None:
            raise ValueError(f"job not found: {job_id}")

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
        status=normalized_data.get("status"),
        progress=normalized_data.get("progress"),
        message=normalized_data.get("message"),
        updated_at=updated_at,
    )


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
                status=payload.get("status"),
                progress=payload.get("progress"),
                message=payload.get("message"),
                updated_at=updated_at,
            )
        )
    return events
