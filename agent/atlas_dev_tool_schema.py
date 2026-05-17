from __future__ import annotations

from pydantic import BaseModel, Field


class AtlasDevToolRequest(BaseModel):
    project_path: str
    relative_path: str = ""
    max_files: int = 500
    max_bytes: int = 200000
    include_untracked: bool = True


class _AtlasBaseResult(BaseModel):
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class AtlasGitStatusResult(_AtlasBaseResult):
    branch: str = ""
    entries: list[str] = Field(default_factory=list)


class AtlasGitDiffResult(_AtlasBaseResult):
    relative_path: str = ""
    staged: bool = False
    diff: str = ""
    truncated: bool = False


class AtlasGitLsFilesResult(_AtlasBaseResult):
    tracked_files: list[str] = Field(default_factory=list)
    untracked_files: list[str] = Field(default_factory=list)


class AtlasProjectTreeResult(_AtlasBaseResult):
    tree: list[str] = Field(default_factory=list)


class AtlasListFilesResult(_AtlasBaseResult):
    files: list[str] = Field(default_factory=list)


class AtlasFileOutlineResult(_AtlasBaseResult):
    relative_path: str = ""
    language: str = ""
    outline: list[str] = Field(default_factory=list)
