from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


AtlasPolicyDecision = Literal["allow", "require_approval", "block"]

AtlasPolicyReasonCategory = Literal[
    "low_risk",
    "high_risk",
    "critical_risk",
    "destructive_change",
    "dependency_change",
    "data_loss",
    "api_breaking_change",
    "ui_breaking_change",
    "security",
    "docker_change",
    "database_migration",
    "protected_path",
    "delete_forbidden",
    "run_command_forbidden",
    "too_many_files",
    "patch_too_large",
    "unknown_risk",
    "manual_gate",
]

AtlasPolicyScope = Literal["pool", "item", "patch", "command"]


class AtlasAutopilotPolicy(BaseModel):
    policy_id: str = ""
    created_at: str = Field(default_factory=_utc_now_iso)
    updated_at: str = Field(default_factory=_utc_now_iso)

    auto_start_next_item: bool = True
    auto_execute_low_risk: bool = True
    auto_apply_low_risk_patches: bool = False
    auto_run_tests: bool = True
    auto_debug_retry: bool = True

    stop_on_failure: bool = True
    pause_after_each_item: bool = False

    max_items_per_run: int = 10
    max_retries_per_item: int = 2
    max_debug_iterations: int = 2
    max_changed_files_per_item: int = 5
    max_patch_bytes: int = 20000

    allow_create: bool = True
    allow_update: bool = True
    allow_delete: bool = False
    allow_run_command: bool = False
    allow_test_command: bool = True

    manual_gate_risks: list[str] = Field(default_factory=lambda: ["high", "critical"])
    manual_gate_categories: list[str] = Field(
        default_factory=lambda: [
            "dependency_change",
            "data_loss",
            "api_breaking_change",
            "ui_breaking_change",
            "security",
            "docker_change",
            "database_migration",
            "destructive_change",
        ]
    )

    protected_paths: list[str] = Field(
        default_factory=lambda: [
            ".git",
            "ca_data",
            "models",
            "node_modules",
            "venv",
            ".venv",
            "__pycache__",
        ]
    )

    allowed_test_commands: list[str] = Field(
        default_factory=lambda: [
            "python -m py_compile",
            "pytest -q",
            "node --check",
            "python -m json.tool",
            "python scripts/check_ui_inline_script_syntax.py",
        ]
    )

    metadata: dict = Field(default_factory=dict)


class AtlasPolicyEvaluation(BaseModel):
    evaluation_id: str
    scope: AtlasPolicyScope
    decision: AtlasPolicyDecision
    item_id: str = ""
    pool_id: str = ""
    risk_level: str = "medium"
    reasons: list[str] = Field(default_factory=list)
    categories: list[AtlasPolicyReasonCategory] = Field(default_factory=list)
    requires_user_confirmation: bool = False
    auto_execution_allowed: bool = False
    blocked: bool = False
    warnings: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    created_at: str = Field(default_factory=_utc_now_iso)
