from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field

class AtlasRepoIndexRequest(BaseModel):
    workspace_id: str = 'default'
    project_path: str
    pool_id: str = ''
    run_id: str = ''
    policy_id: str = 'repo_index_v1'
    mode: Literal['build','update','build_or_update','status_only'] = 'build_or_update'
    changed_files: list[str] = Field(default_factory=list)
    include_globs: list[str] = Field(default_factory=list)
    exclude_globs: list[str] = Field(default_factory=list)
    max_files: int = 5000
    max_file_bytes: int = 1_000_000
    incremental: bool = True
    force_rebuild: bool = False
    include_tests: bool = True
    include_ui_events: bool = True
    include_routes: bool = True
    metadata: dict = Field(default_factory=dict)

class AtlasRepoSymbol(BaseModel):
    symbol_id: str
    name: str
    kind: str = 'unknown'
    file_path: str
    language: str
    line_start: int = 0
    line_end: int = 0
    parent: str = ''
    signature: str = ''
    docstring: str = ''
    exported: bool = False
    references: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)

class AtlasRepoFileNode(BaseModel):
    file_path: str
    language: str
    size_bytes: int
    mtime_ns: int
    sha256: str
    symbols: list[str] = Field(default_factory=list)
    imports: list[str] = Field(default_factory=list)
    imported_by: list[str] = Field(default_factory=list)
    routes: list[str] = Field(default_factory=list)
    tests: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)

class AtlasRepoDependencyEdge(BaseModel):
    source: str
    target: str
    edge_type: str = 'unknown'
    confidence: Literal['high','medium','low'] = 'low'
    evidence: dict = Field(default_factory=dict)

class AtlasRepoIndexResult(BaseModel):
    workspace_id: str
    project_path: str
    index_run_id: str
    policy_id: str
    status: str
    mode: str
    total_files: int = 0
    indexed_files: int = 0
    skipped_files: int = 0
    changed_files: list[str] = Field(default_factory=list)
    impacted_files: list[str] = Field(default_factory=list)
    impacted_symbols: list[str] = Field(default_factory=list)
    related_tests: list[str] = Field(default_factory=list)
    symbol_count: int = 0
    edge_count: int = 0
    artifact_paths: dict = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    created_at: str
