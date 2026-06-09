from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


PLAY_SCHEMA_VERSION = "atlas.play.v1"
PLAY_THREAT_MODEL_VERSION = "atlas.play.threat_model.v1"


class StrictContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LaunchKind(StrEnum):
    STATIC_WEB = "static_web"
    PYTHON_SCRIPT = "python_script"
    PYTHON_ASGI = "python_asgi"
    PYTHON_WSGI = "python_wsgi"
    STREAMLIT = "streamlit"
    DJANGO = "django"
    NODE_SCRIPT = "node_script"
    NPM_SCRIPT = "npm_script"
    VITE = "vite"
    NEXT = "next"
    COMPOSITE = "composite"


class PlayRequestSource(StrEnum):
    ATLAS_BUTTON = "atlas_button"
    ATLAS_COMMAND = "atlas_command"
    PORTAL_RUN = "portal_run"


class TrustState(StrEnum):
    TRUSTED_LOCAL_CAPSULE = "trusted_local_capsule"
    VERIFIED_PUBLISHER_PACKAGE = "verified_publisher_package"
    UNTRUSTED_IMPORTED_PACKAGE = "untrusted_imported_package"


class RuntimeIsolationPolicy(StrEnum):
    ADVISORY_TRUST_DEFAULT_BLOCK = "advisory_trust_default_block"


class PlayResourceLimits(StrictContractModel):
    schema_version: Literal[PLAY_SCHEMA_VERSION] = PLAY_SCHEMA_VERSION
    max_sessions_per_project: int = Field(default=2, ge=1, le=8)
    max_total_sessions: int = Field(default=8, ge=1, le=32)
    max_log_bytes_per_session: int = Field(default=2_000_000, ge=64_000, le=20_000_000)
    max_session_seconds: int = Field(default=3600, ge=10, le=86_400)
    max_recovery_seconds: int = Field(default=86_400, ge=60, le=604_800)
    max_related_files: int = Field(default=500, ge=1, le=10_000)
    max_file_bytes: int = Field(default=2_000_000, ge=1_024, le=50_000_000)
    loopback_only: bool = True
    expose_temporary_ports_directly: bool = False
    allow_unbounded_commands: bool = False
    allow_host_filesystem_serving: bool = False


class PlayThreatModel(StrictContractModel):
    schema_version: Literal[PLAY_THREAT_MODEL_VERSION] = PLAY_THREAT_MODEL_VERSION
    execution_boundary: str = (
        "Play and Portal launch user-selected project artifacts as a runtime; "
        "they are not agent autonomous command execution."
    )
    launch_adapter_authority: str = (
        "Launch adapters are separate from verification allowlists and do not "
        "lend authority to workflow_state, PlanPool approval, or self-apply."
    )
    isolation_policy: RuntimeIsolationPolicy = RuntimeIsolationPolicy.ADVISORY_TRUST_DEFAULT_BLOCK
    untrusted_default_run_allowed: bool = False
    untrusted_override_requires_warning: bool = True
    notes: list[str] = Field(
        default_factory=lambda: [
            "No general shell endpoint.",
            "No file:// preview.",
            "No direct temporary port exposure.",
            "Unknown launch kinds fail closed.",
        ]
    )


class PlayRequest(StrictContractModel):
    schema_version: Literal[PLAY_SCHEMA_VERSION] = PLAY_SCHEMA_VERSION
    source: PlayRequestSource
    project_id: str = Field(min_length=1)
    work_root: str = Field(min_length=1)
    selected_entrypoint: str | None = None
    launch_profile_id: str | None = None
    requested_by: str = "user"
    portal_installation_id: str | None = None
    allow_untrusted_override: bool = False

    @model_validator(mode="after")
    def _portal_source_requires_installation(self) -> "PlayRequest":
        if self.source == PlayRequestSource.PORTAL_RUN and not self.portal_installation_id:
            raise ValueError("portal_run_requires_installation_id")
        return self


class PlayTarget(StrictContractModel):
    schema_version: Literal[PLAY_SCHEMA_VERSION] = PLAY_SCHEMA_VERSION
    project_id: str = Field(min_length=1)
    work_root: str = Field(min_length=1)
    entrypoint: str = Field(min_length=1)
    related_files: list[str] = Field(default_factory=list)
    detected_launch_kinds: list[LaunchKind] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)


class LaunchProfile(StrictContractModel):
    schema_version: Literal[PLAY_SCHEMA_VERSION] = PLAY_SCHEMA_VERSION
    profile_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    kind: LaunchKind
    entrypoint: str | None = None
    working_directory: str = "."
    args: list[str] = Field(default_factory=list, max_length=32)
    environment_keys: list[str] = Field(default_factory=list, max_length=64)
    depends_on: list[str] = Field(default_factory=list, max_length=32)

    @field_validator("args", "environment_keys", "depends_on")
    @classmethod
    def _non_empty_string_items(cls, value: list[str]) -> list[str]:
        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise ValueError("empty_list_item")
        return value

    @model_validator(mode="after")
    def _entrypoint_required_for_non_composite(self) -> "LaunchProfile":
        if self.kind != LaunchKind.COMPOSITE and not self.entrypoint:
            raise ValueError("entrypoint_required")
        if self.kind == LaunchKind.COMPOSITE and self.entrypoint:
            raise ValueError("composite_profile_has_no_single_entrypoint")
        return self


class EnvironmentSpec(StrictContractModel):
    schema_version: Literal[PLAY_SCHEMA_VERSION] = PLAY_SCHEMA_VERSION
    python_executable: str | None = None
    node_executable: str | None = None
    package_manager: str | None = None
    allowed_environment: dict[str, str] = Field(default_factory=dict)
    missing_dependencies: list[str] = Field(default_factory=list)
    host_mutation_allowed: bool = False


class PlaySessionView(StrictContractModel):
    schema_version: Literal[PLAY_SCHEMA_VERSION] = PLAY_SCHEMA_VERSION
    session_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    state: str
    target: PlayTarget | None = None
    launch_profile: LaunchProfile | None = None
    preview_url: str | None = None
    log_tail: list[str] = Field(default_factory=list)
    can_restart: bool = False
    can_stop: bool = False
    can_edit_files: bool = False
    warnings: list[str] = Field(default_factory=list)


class PlayLifecycleEvent(StrictContractModel):
    schema_version: Literal[PLAY_SCHEMA_VERSION] = PLAY_SCHEMA_VERSION
    session_id: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    state_before: str
    state_after: str
    message: str = ""
    details: dict[str, Any] = Field(default_factory=dict)
