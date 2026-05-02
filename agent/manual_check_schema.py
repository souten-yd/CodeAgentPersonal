from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ManualLLMCheckResult(BaseModel):
    check_id: str
    run_id: str
    patch_id: str
    created_at: str = Field(default_factory=_utc_now_iso)
    reviewer: str = ""
    llm_endpoint: str = ""
    model: str = ""
    test_target_file: str = ""
    patch_generation_mode: str = ""
    patch_type: str = ""
    generator: str = ""
    apply_allowed: bool = False
    quality_score: float = 0.0
    can_apply_reason: str = ""
    safety_warnings: list[str] = Field(default_factory=list)
    quality_warnings: list[str] = Field(default_factory=list)
    verification_status: str = ""
    reproposal_generated: bool = False
    observed_issue: str = ""
    notes: str = ""
    metadata: dict = Field(default_factory=dict)
