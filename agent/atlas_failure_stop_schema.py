from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class AtlasFailureStopSuggestion(BaseModel):
    pool_id: str
    item_id: str
    run_id: str = ""
    failure_phase: Literal["auto_verification", "safe_apply"]
    status: Literal["stopped", "no_action", "blocked"]
    reason: str = ""
    suggested_manual_actions: list[str] = Field(default_factory=list)
    restore_candidate: dict[str, Any] = Field(default_factory=dict)
    snapshot_manifest_path: str = ""
    changed_files: list[str] = Field(default_factory=list)
    verification_result: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
