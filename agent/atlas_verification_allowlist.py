from __future__ import annotations

from pydantic import BaseModel


class AtlasVerificationCommand(BaseModel):
    command_id: str
    label: str
    command: list[str]
    description: str
    timeout_seconds: int = 60
    allowed: bool = True


def atlas_verification_allowlist() -> dict[str, AtlasVerificationCommand]:
    commands = [
        AtlasVerificationCommand(command_id="pytest_selected", label="Pytest selected", command=["python", "-m", "pytest", "-q", "{test_path}"], description="Run selected pytest target."),
        AtlasVerificationCommand(command_id="pytest_file", label="Pytest file", command=["python", "-m", "pytest", "-q", "{test_file}"], description="Run pytest file target."),
        AtlasVerificationCommand(command_id="node_check_dashboard", label="Node check dashboard", command=["node", "--check", "web/js/atlas_dashboard.js"], description="Syntax check atlas dashboard."),
        AtlasVerificationCommand(command_id="node_check_pipeline_api", label="Node check pipeline api", command=["node", "--check", "web/js/atlas_pipeline_api.js"], description="Syntax check atlas pipeline api."),
    ]
    return {c.command_id: c for c in commands}
