from __future__ import annotations

from agent.atlas_code_intel_schema import (
    AtlasDependencyGraphRequest,
    AtlasRelatedTestsRequest,
    AtlasSymbolIndexRequest,
)
from agent.atlas_code_intel_service import AtlasCodeIntelService


class ProjectIntelligenceCodeIntelAdapter:
    """Compatibility adapter for read-only Atlas code-intelligence consumers."""

    def __init__(self, service: AtlasCodeIntelService | None = None) -> None:
        self._service = service or AtlasCodeIntelService()

    def build_symbol_index(self, request: AtlasSymbolIndexRequest):
        return self._service.build_symbol_index(request)

    def build_dependency_graph(self, request: AtlasDependencyGraphRequest):
        return self._service.build_dependency_graph(request)

    def find_related_tests(self, request: AtlasRelatedTestsRequest):
        return self._service.find_related_tests(request)
