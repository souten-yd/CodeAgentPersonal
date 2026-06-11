"""Compatibility adapter for Atlas context-refresh API services.

The retained context-refresh services stay behind this Project Intelligence adapter while
API consumers stop importing legacy owners directly.
"""

from __future__ import annotations

from pathlib import Path

from agent.atlas_context_refresh_schema import AtlasContextRefreshRequest
from agent.atlas_context_refresh_service import AtlasContextRefreshService
from agent.atlas_context_refresh_v2_schema import AtlasContextRefreshV2Request
from agent.atlas_context_refresh_v2_service import AtlasContextRefreshV2Service
from agent.atlas_journal import AtlasJournal


class AtlasContextRefreshAdapter:
    """Adapter used by API routes and service factories for context-refresh support."""

    def __init__(self, data_root: str | Path) -> None:
        self.data_root = Path(data_root)

    def build_service(self, *, journal: AtlasJournal | None = None) -> AtlasContextRefreshService:
        return AtlasContextRefreshService(journal=journal, data_root=self.data_root)

    def refresh(self, request: AtlasContextRefreshRequest):
        return self.build_service().refresh(request)

    def refresh_v2(self, request: AtlasContextRefreshV2Request):
        return AtlasContextRefreshV2Service(data_root=self.data_root).refresh(request)
