from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AtlasSymbolIndexRequest(BaseModel):
    project_path: str
    relative_path: str = ""
    max_files: int = 1000
    max_symbols: int = 5000
    max_bytes_per_file: int = 200000


class AtlasSymbol(BaseModel):
    name: str
    kind: Literal[
        "function",
        "class",
        "method",
        "variable",
        "import",
        "export",
        "html_id",
        "css_selector",
    ]
    file_path: str
    line: int | None = None
    column: int | None = None
    parent: str = ""
    signature: str = ""
    metadata: dict = Field(default_factory=dict)


class AtlasSymbolIndexResult(BaseModel):
    project_path: str
    symbols: list[AtlasSymbol] = Field(default_factory=list)
    file_count: int = 0
    skipped_files: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class AtlasDependencyGraphRequest(BaseModel):
    project_path: str
    relative_path: str = ""
    max_files: int = 1000
    max_edges: int = 10000
    max_bytes_per_file: int = 200000


class AtlasDependencyEdge(BaseModel):
    source: str
    target: str
    kind: Literal[
        "python_import",
        "js_import",
        "html_script",
        "html_stylesheet",
        "css_import",
        "unknown",
    ]
    line: int | None = None
    metadata: dict = Field(default_factory=dict)


class AtlasDependencyGraphResult(BaseModel):
    project_path: str
    nodes: list[str] = Field(default_factory=list)
    edges: list[AtlasDependencyEdge] = Field(default_factory=list)
    skipped_files: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class AtlasRelatedTestsRequest(BaseModel):
    project_path: str
    changed_files: list[str]
    max_tests: int = 100


class AtlasRelatedTestsResult(BaseModel):
    project_path: str
    changed_files: list[str] = Field(default_factory=list)
    related_tests: list[dict] = Field(default_factory=list)
    confidence: str = "low"
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
