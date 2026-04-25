from __future__ import annotations

from datetime import datetime, timezone
import json

from app.nexus.db import transaction, get_conn

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "queued": {"running"},
    "running": {"completed", "failed"},
    "completed": set(),
    "failed": set(),
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_job(row) -> dict:
    return {
        "job_id": row["job_id"],
        "status": row["status"],
        "title": row["title"],
        "message": row["message"],
        "document_count": row["document_count"],
        "download_url": row["download_url"],
        "error": row["error"],
        "bundle_path": row["bundle_path"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "completed_at": row["completed_at"],
    }


def create_job(
    job_id: str,
    *,
    title: str | None = None,
    message: str | None = None,
    document_count: int = 0,
    download_url: str | None = None,
    bundle_path: str | None = None,
) -> dict:
    now = _now_iso()
    with transaction() as conn:
        conn.execute(
            """
            INSERT INTO nexus_jobs (
                job_id, status, title, message, document_count, download_url, bundle_path,
                created_at, updated_at
            ) VALUES (?, 'queued', ?, ?, ?, ?, ?, ?, ?)
            """,
            (job_id, title, message, document_count, download_url, bundle_path, now, now),
        )
        conn.execute(
            """
            INSERT INTO nexus_job_events (job_id, seq, event_type, data, created_at)
            VALUES (?, 0, 'job_created', ?, ?)
            """,
            (job_id, json.dumps({"status": "queued"}, ensure_ascii=False), now),
        )

    return get_job(job_id)


def update_job(
    job_id: str,
    *,
    status: str | None = None,
    title: str | None = None,
    message: str | None = None,
    document_count: int | None = None,
    download_url: str | None = None,
    bundle_path: str | None = None,
    error: str | None = None,
) -> dict | None:
    with transaction() as conn:
        row = conn.execute(
            "SELECT * FROM nexus_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        if not row:
            return None

        current_status = row["status"]
        new_status = status or current_status
        if status and new_status != current_status:
            allowed = ALLOWED_TRANSITIONS.get(current_status, set())
            if new_status not in allowed:
                raise ValueError(f"invalid status transition: {current_status} -> {new_status}")

        now = _now_iso()
        completed_at = row["completed_at"]
        if new_status in {"completed", "failed"}:
            completed_at = now

        conn.execute(
            """
            UPDATE nexus_jobs
            SET status = ?,
                title = COALESCE(?, title),
                message = COALESCE(?, message),
                document_count = COALESCE(?, document_count),
                download_url = COALESCE(?, download_url),
                bundle_path = COALESCE(?, bundle_path),
                error = COALESCE(?, error),
                updated_at = ?,
                completed_at = ?
            WHERE job_id = ?
            """,
            (
                new_status,
                title,
                message,
                document_count,
                download_url,
                bundle_path,
                error,
                now,
                completed_at,
                job_id,
            ),
        )

        if status and new_status != current_status:
            seq = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) + 1 FROM nexus_job_events WHERE job_id = ?",
                (job_id,),
            ).fetchone()[0]
            conn.execute(
                """
                INSERT INTO nexus_job_events (job_id, seq, event_type, data, created_at)
                VALUES (?, ?, 'job_status', ?, ?)
                """,
                (
                    job_id,
                    seq,
                    json.dumps(
                        {
                            "from": current_status,
                            "to": new_status,
                            "status": new_status,
                            "error": error,
                        },
                        ensure_ascii=False,
                    ),
                    now,
                ),
            )

    return get_job(job_id)


def get_job(job_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM nexus_jobs WHERE job_id = ?", (job_id,)).fetchone()
    if not row:
        return None
    return _normalize_job(row)


def list_active_jobs(limit: int = 100) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM nexus_jobs
            WHERE status IN ('queued', 'running')
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (max(1, limit),),
        ).fetchall()
    return [_normalize_job(row) for row in rows]


def append_job_event(job_id: str, event_type: str, data: dict) -> dict:
    now = _now_iso()
    with transaction() as conn:
        seq = conn.execute(
            "SELECT COALESCE(MAX(seq), -1) + 1 FROM nexus_job_events WHERE job_id = ?",
            (job_id,),
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO nexus_job_events (job_id, seq, event_type, data, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (job_id, seq, event_type, json.dumps(data, ensure_ascii=False), now),
        )
    return {"seq": seq, "type": event_type, "data": data, "ts": now}


def get_job_events(job_id: str, after: int = -1) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT seq, event_type, data, created_at
            FROM nexus_job_events
            WHERE job_id = ? AND seq > ?
            ORDER BY seq ASC
            """,
            (job_id, after),
        ).fetchall()

    return [
        {
            "seq": row["seq"],
            "type": row["event_type"],
            "data": json.loads(row["data"]),
            "ts": row["created_at"],
        }
        for row in rows
    ]
