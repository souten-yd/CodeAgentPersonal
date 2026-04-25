from __future__ import annotations

from typing import Any

from app.nexus.schemas import JobStatus, NexusJob, NexusJobEvent



def create_job(job_id: str) -> NexusJob:
    """空実装: 最小ジョブを返す。"""
    return NexusJob(job_id=job_id, status="queued")



def update_job(job_id: str, *, status: JobStatus) -> NexusJob:
    """空実装: 指定ステータスの最小ジョブを返す。"""
    return NexusJob(job_id=job_id, status=status)



def get_job(job_id: str) -> NexusJob | None:
    """空実装: 永続化未対応のため常にNoneを返す。"""
    _ = job_id
    return None



def list_active_jobs(limit: int = 100) -> list[NexusJob]:
    """空実装: 空リストを返す。"""
    _ = limit
    return []



def append_job_event(job_id: str, event_type: str, data: dict[str, Any]) -> NexusJobEvent:
    """空実装: シーケンス0のイベントを返す。"""
    _ = job_id
    return NexusJobEvent(seq=0, type=event_type, data=data)



def get_job_events(job_id: str, after: int = -1) -> list[NexusJobEvent]:
    """空実装: 空リストを返す。"""
    _ = (job_id, after)
    return []
