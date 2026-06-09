from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.atlas.play.contracts import LaunchProfile, TrustState


CAPSULE_SCHEMA_VERSION = "atlas.capsule.v1"


class StrictContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CapsuleDataPolicy(StrictContractModel):
    schema_version: Literal[CAPSULE_SCHEMA_VERSION] = CAPSULE_SCHEMA_VERSION
    persistent_data_supported: bool = False
    export_includes_runtime_data: bool = False
    backup_format_version: str = "portal-data-backup.v1"


class CapsuleManifest(StrictContractModel):
    schema_version: Literal[CAPSULE_SCHEMA_VERSION] = CAPSULE_SCHEMA_VERSION
    package_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    launch_profiles: list[LaunchProfile] = Field(min_length=1)
    default_profile_id: str
    requested_permissions: list[str] = Field(default_factory=list)
    data_policy: CapsuleDataPolicy = Field(default_factory=CapsuleDataPolicy)
    application_root: str = "application"
    metadata_root: str = "metadata"

    @model_validator(mode="after")
    def _default_profile_must_exist(self) -> "CapsuleManifest":
        if self.default_profile_id not in {profile.profile_id for profile in self.launch_profiles}:
            raise ValueError("default_profile_not_found")
        return self


class CapsuleBuildRequest(StrictContractModel):
    schema_version: Literal[CAPSULE_SCHEMA_VERSION] = CAPSULE_SCHEMA_VERSION
    project_id: str = Field(min_length=1)
    play_session_id: str = Field(min_length=1)
    selected_profile_ids: list[str] = Field(min_length=1)
    require_current_hashes: bool = True
    # Force build bypasses the successful-Play-session gate and current-hash check.
    # Path safety, exclusion policy and private-data findings still apply.
    force: bool = False
    package_id: str | None = None
    name: str | None = None
    version: str = "0.1.0"
    default_profile_id: str | None = None
    launch_profiles: list[LaunchProfile] = Field(default_factory=list)
    include_globs: list[str] = Field(default_factory=lambda: ["*", "**/*"])
    exclude_globs: list[str] = Field(default_factory=list)
    expected_file_hashes: dict[str, str] = Field(default_factory=dict)
    data_policy: CapsuleDataPolicy = Field(default_factory=CapsuleDataPolicy)


class CapsulePackageRecord(StrictContractModel):
    schema_version: Literal[CAPSULE_SCHEMA_VERSION] = CAPSULE_SCHEMA_VERSION
    package_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    storage_path: str = Field(min_length=1)
    content_hash: str = Field(min_length=1)
    trust_state: TrustState = TrustState.TRUSTED_LOCAL_CAPSULE
    immutable: bool = True
    manifest_path: str = ""
    findings_path: str = ""
