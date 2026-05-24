from __future__ import annotations

from pydantic import BaseModel, Field

_RUNTIME_LEVEL = "level_0_manual_only"
_SHELL_METACHARS = (";", "&&", "||", "|", "`", "$", ">", "<")
_BLOCKED_TOKENS = (
    "pip install",
    "npm install",
    "pnpm add",
    "yarn add",
    "git clone",
    "git fetch",
    "git pull",
    "rm -rf",
    "del /f",
    "format ",
)


class AtlasVerificationCommand(BaseModel):
    command_id: str
    label: str
    command: list[str]
    description: str
    timeout_seconds: int = 60
    allowed: bool = True
    risk_class: str = "low"


class AtlasVerificationResolution(BaseModel):
    target_id: str
    allowed: bool
    reason: str
    risk_class: str
    runtime_level: str = _RUNTIME_LEVEL
    resolver_only: bool = True
    execution_enabled: bool = False
    advisory_only: bool = True
    authoritative_source: str = "backend"
    vue_authoritative: bool = False
    command_metadata: dict[str, object] = Field(default_factory=dict)


def atlas_verification_allowlist() -> dict[str, AtlasVerificationCommand]:
    commands = [
        AtlasVerificationCommand(command_id="pytest_selected", label="Pytest selected", command=["python", "-m", "pytest", "-q", "{test_path}"], description="Run selected pytest target."),
        AtlasVerificationCommand(command_id="pytest_file", label="Pytest file", command=["python", "-m", "pytest", "-q", "{test_file}"], description="Run pytest file target."),
        AtlasVerificationCommand(command_id="node_check_dashboard", label="Node check dashboard", command=["node", "--check", "web/js/atlas_dashboard.js"], description="Syntax check atlas dashboard."),
        AtlasVerificationCommand(command_id="node_check_pipeline_api", label="Node check pipeline api", command=["node", "--check", "web/js/atlas_pipeline_api.js"], description="Syntax check atlas pipeline api."),
    ]
    return {c.command_id: c for c in commands}


def resolve_verification_allowlist_target(target_id: str) -> AtlasVerificationResolution:
    raw = str(target_id or "").strip()
    if not raw:
        return AtlasVerificationResolution(target_id="", allowed=False, reason="empty_target_id", risk_class="blocked")

    lowered = raw.lower()
    if any(ch in raw for ch in _SHELL_METACHARS):
        return AtlasVerificationResolution(target_id=raw, allowed=False, reason="shell_metacharacter_rejected", risk_class="blocked")
    if any(token in lowered for token in _BLOCKED_TOKENS):
        return AtlasVerificationResolution(target_id=raw, allowed=False, reason="disallowed_command_pattern", risk_class="blocked")

    command = atlas_verification_allowlist().get(raw)
    if command is None:
        return AtlasVerificationResolution(target_id=raw, allowed=False, reason="unknown_target_id", risk_class="blocked")

    command_metadata = {
        "command_id": command.command_id,
        "label": command.label,
        "command": list(command.command),
        "description": command.description,
        "timeout_seconds": command.timeout_seconds,
    }
    return AtlasVerificationResolution(
        target_id=raw,
        allowed=bool(command.allowed),
        reason="allowlisted" if command.allowed else "allowlisted_but_disabled",
        risk_class=command.risk_class,
        command_metadata=command_metadata,
    )
