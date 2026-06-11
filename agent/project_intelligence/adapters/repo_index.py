from __future__ import annotations

from pathlib import Path

from agent.atlas_repo_index_policies import POLICIES
from agent.atlas_repo_index_schema import AtlasRepoIndexRequest
from agent.atlas_repo_index_service import AtlasRepoIndexService
from agent.atlas_repo_index_storage import AtlasRepoIndexStorage


class ProjectIntelligenceRepoIndexAdapter:
    """Compatibility adapter for Atlas repository-index API routes."""

    def __init__(self, data_root: str | Path) -> None:
        self.data_root = Path(data_root)
        self._service = AtlasRepoIndexService(self.data_root)
        self._storage = AtlasRepoIndexStorage(self.data_root)

    def policies(self) -> dict:
        return {"policies": POLICIES}

    def build_or_update(self, request: AtlasRepoIndexRequest):
        return self._service.build_or_update(request)

    def query_impacts(self, request: AtlasRepoIndexRequest) -> dict:
        return self._service.query_impacts(request.project_path, request.changed_files)

    def query_related_tests(self, request: AtlasRepoIndexRequest) -> dict:
        return self._service.query_related_tests(request.project_path, request.changed_files)

    def load_latest(self, request: AtlasRepoIndexRequest) -> dict:
        return self._service.load_latest(request.workspace_id, request.project_path)

    def load_result_by_hash(self, project_hash: str, index_run_id: str) -> dict:
        return self._storage.load_result_by_hash(project_hash, index_run_id)
