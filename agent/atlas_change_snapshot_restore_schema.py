from __future__ import annotations

from pydantic import BaseModel, Field


class AtlasChangeSnapshotRestoreRequest(BaseModel):
    pool_id: str
    item_id: str = ""
    run_id: str = ""
    workspace_id: str = "default"
    manifest_path: str
    confirm_delete_missing_before: bool = False
    metadata: dict = Field(default_factory=dict)


class AtlasChangeSnapshotRestoreFileResult(BaseModel):
    path: str
    existed_before: bool = True
    restored: bool = False
    deleted: bool = False
    skipped: bool = False
    skip_reason: str = ""
    sha256_before: str = ""
    sha256_after: str = ""


class AtlasChangeSnapshotRestoreResult(BaseModel):
    pool_id: str
    item_id: str = ""
    run_id: str = ""
    status: str
    restored_count: int = 0
    deleted_count: int = 0
    skipped_count: int = 0
    report_json_path: str = ""
    report_md_path: str = ""
    file_results: list[AtlasChangeSnapshotRestoreFileResult] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
