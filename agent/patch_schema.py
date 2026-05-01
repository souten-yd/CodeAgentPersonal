from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


PatchStatus = Literal["proposed", "approved", "applied", "rejected", "failed"]
PatchType = Literal["append", "replace_block", "unified_diff"]


class PatchProposal(BaseModel):
    patch_id: str
    run_id: str
    plan_id: str
    step_id: str
    target_file: str
    created_at: str = Field(default_factory=_utc_now_iso)
    status: PatchStatus = "proposed"
    patch_type: PatchType = "append"
    original_preview: str = ""
    proposed_content: str = ""
    unified_diff: str = ""
    risk_level: str = "low"
    safety_warnings: list[str] = Field(default_factory=list)
    apply_allowed: bool = False
    applied: bool = False
    error: str = ""
    metadata: dict = Field(default_factory=dict)


class PatchApplyResult(BaseModel):
    patch_id: str
    applied: bool = False
    target_file: str = ""
    backup_path: str = ""
    changed_bytes: int = 0
    message: str = ""
    error: str = ""
    verification_result_id: str = ""
