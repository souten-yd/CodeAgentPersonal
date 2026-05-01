from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


VerificationStatus = Literal["passed", "failed", "skipped", "warning"]


class VerificationCheck(BaseModel):
    check_id: str
    name: str
    status: VerificationStatus
    message: str = ""
    details: str = ""


class VerificationResult(BaseModel):
    verification_id: str
    run_id: str
    plan_id: str
    patch_id: str
    created_at: str = Field(default_factory=_utc_now_iso)
    status: VerificationStatus = "skipped"
    checks: list[VerificationCheck] = Field(default_factory=list)
    summary: str = ""
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
