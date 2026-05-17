from __future__ import annotations

from pydantic import BaseModel, Field


class AtlasChangeSnapshotFile(BaseModel):
    path: str
    existed_before: bool
    size_before: int = 0
    sha256_before: str = ""
    backup_path: str = ""
    skipped: bool = False
    skip_reason: str = ""


class AtlasChangeSnapshot(BaseModel):
    snapshot_id: str
    pool_id: str
    item_id: str
    run_id: str = ""
    workspace_id: str = "default"
    created_at: str
    target_files: list[AtlasChangeSnapshotFile] = Field(default_factory=list)
    manifest_path: str = ""
    snapshot_dir: str = ""
    restore_allowed: bool = True
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class AtlasChangeSnapshotResult(BaseModel):
    pool_id: str
    item_id: str
    run_id: str = ""
    status: str
    snapshot: AtlasChangeSnapshot | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
