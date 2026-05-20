from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


AtlasContextRefreshTrigger = Literal[
    "implementation_planning",
    "pre_safe_apply",
    "verification_failure",
    "debug_review",
    "evaluator_precheck",
    "manual",
]

AtlasContextBundleStatus = Literal["ready", "partial", "blocked", "failed", "skipped"]

AtlasContextSourceType = Literal[
    "git_status",
    "git_diff",
    "project_tree",
    "file_outline",
    "symbol_index",
    "dependency_graph",
    "related_tests",
    "nexus_local",
    "nexus_web",
    "nexus_deep_research",
    "manual",
]


class AtlasContextRefreshRequest(BaseModel):
    pool_id: str
    item_id: str = ""
    run_id: str = ""
    trigger: AtlasContextRefreshTrigger
    workspace_id: str = "default"
    project_path: str = ""
    changed_files: list[str] = Field(default_factory=list)
    target_files: list[str] = Field(default_factory=list)
    query: str = ""
    policy_id: str = "local_first_bounded"
    include_local_tools: bool = True
    include_nexus_search: bool = False
    include_deep_research: bool = False
    max_sources: int = 8
    max_context_chars: int = 24000
    timeout_seconds: int = 60
    metadata: dict = Field(default_factory=dict)


class AtlasContextRefreshPolicy(BaseModel):
    policy_id: str
    name: str
    description: str
    allow_local_dev_tools: bool = True
    allow_code_intel: bool = True
    allow_nexus_local_knowledge: bool = True
    allow_nexus_web_search: bool = False
    allow_deep_research: bool = False
    require_manual_for_web: bool = True
    require_manual_for_deep_research: bool = True
    max_sources: int = 8
    max_context_chars: int = 24000
    max_changed_files: int = 20
    timeout_seconds: int = 60
    notes: list[str] = Field(default_factory=list)


class AtlasContextSource(BaseModel):
    source_id: str
    source_type: AtlasContextSourceType
    title: str
    summary: str
    path: str = ""
    url: str = ""
    score: float = 0
    metadata: dict = Field(default_factory=dict)


class AtlasContextBundle(BaseModel):
    bundle_id: str
    pool_id: str
    item_id: str = ""
    run_id: str = ""
    trigger: str
    policy_id: str
    status: AtlasContextBundleStatus
    query: str = ""
    context_text: str = ""
    sources: list[AtlasContextSource] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)
    related_tests: list[dict] = Field(default_factory=list)
    dependency_edges: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    created_at: str
