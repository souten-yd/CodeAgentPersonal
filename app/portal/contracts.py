from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.atlas.play.contracts import TrustState


PORTAL_SCHEMA_VERSION = "portal.v1"


class StrictContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PortalRunMode(StrEnum):
    CONTINUE_CURRENT_DATA = "continue_current_data"
    START_EMPTY = "start_empty"
    START_FROM_SNAPSHOT = "start_from_snapshot"
    EPHEMERAL = "ephemeral"


class PortalDataDecision(StrEnum):
    SAVE_AND_EXIT = "save_and_exit"
    SAVE_AS_SNAPSHOT = "save_as_snapshot"
    DISCARD_AND_EXIT = "discard_and_exit"
    RETURN_TO_APP = "return_to_app"


class PortalInstallation(StrictContractModel):
    schema_version: Literal[PORTAL_SCHEMA_VERSION] = PORTAL_SCHEMA_VERSION
    installation_id: str = Field(min_length=1)
    package_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    package_path: str = Field(min_length=1)
    content_hash: str = Field(min_length=1)
    trust_state: TrustState
    package_immutable: bool = True
    current_data_bytes: int = Field(default=0, ge=0)


class PortalRunRequest(StrictContractModel):
    schema_version: Literal[PORTAL_SCHEMA_VERSION] = PORTAL_SCHEMA_VERSION
    installation_id: str = Field(min_length=1)
    launch_profile_id: str = Field(min_length=1)
    run_mode: PortalRunMode = PortalRunMode.CONTINUE_CURRENT_DATA
    snapshot_id: str | None = None
    trust_state: TrustState
    untrusted_override_acknowledged: bool = False

    @model_validator(mode="after")
    def _snapshot_mode_requires_snapshot(self) -> "PortalRunRequest":
        if self.run_mode == PortalRunMode.START_FROM_SNAPSHOT and not self.snapshot_id:
            raise ValueError("snapshot_id_required")
        return self


class PortalRunDecision(StrictContractModel):
    schema_version: Literal[PORTAL_SCHEMA_VERSION] = PORTAL_SCHEMA_VERSION
    allowed: bool
    reason: str
    warning: str = ""


def evaluate_portal_run_policy(request: PortalRunRequest) -> PortalRunDecision:
    if (
        request.trust_state == TrustState.UNTRUSTED_IMPORTED_PACKAGE
        and not request.untrusted_override_acknowledged
    ):
        return PortalRunDecision(
            allowed=False,
            reason="untrusted_package_run_blocked_by_default",
            warning="Imported package execution is not OS-isolated in v1.",
        )
    if request.trust_state == TrustState.UNTRUSTED_IMPORTED_PACKAGE:
        return PortalRunDecision(
            allowed=True,
            reason="untrusted_package_override_acknowledged",
            warning="Imported package execution is not OS-isolated in v1.",
        )
    return PortalRunDecision(allowed=True, reason="trusted_package")


class PortalDataCommit(StrictContractModel):
    schema_version: Literal[PORTAL_SCHEMA_VERSION] = PORTAL_SCHEMA_VERSION
    installation_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    decision: PortalDataDecision
    atomic_commit_required: bool = True
    package_export_includes_data: bool = False


class PortalSnapshot(StrictContractModel):
    schema_version: Literal[PORTAL_SCHEMA_VERSION] = PORTAL_SCHEMA_VERSION
    snapshot_id: str = Field(min_length=1)
    installation_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    immutable: bool = True
    data_hash: str = Field(min_length=1)
