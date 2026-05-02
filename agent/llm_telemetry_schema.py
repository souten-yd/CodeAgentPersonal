from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


TelemetryPurpose = Literal["patch_generation", "reproposal_generation", "manual_check"]


class LLMCallTelemetry(BaseModel):
    telemetry_id: str
    run_id: str
    plan_id: str = ""
    patch_id: str = ""
    step_id: str = ""
    created_at: str = Field(default_factory=_utc_now_iso)
    purpose: TelemetryPurpose = "patch_generation"
    provider: str = ""
    model: str = ""
    base_url: str = ""
    request_started_at: str = ""
    request_finished_at: str = ""
    duration_ms: int = 0
    success: bool = False
    error: str = ""
    prompt_chars: int = 0
    response_chars: int = 0
    raw_output_preview: str = ""
    sanitized: bool = False
    parsed_json: bool = False
    validation_reason: str = ""
    apply_allowed_after_validation: bool = False
    metadata: dict = Field(default_factory=dict)
