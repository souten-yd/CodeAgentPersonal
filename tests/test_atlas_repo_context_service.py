from pathlib import Path
from agent.atlas_repo_context_schema import AtlasRepoContextRequest
from agent.atlas_repo_context_service import AtlasRepoContextService


def test_repo_context_snapshot_missing_without_project_path(tmp_path: Path):
    svc = AtlasRepoContextService(data_root=tmp_path)
    snap = svc.build_snapshot(AtlasRepoContextRequest())
    assert snap.status == 'missing'


def test_repo_context_missing_index_is_non_blocking(tmp_path: Path):
    project = tmp_path / 'repo'
    project.mkdir()
    svc = AtlasRepoContextService(data_root=tmp_path)
    snap = svc.build_snapshot(AtlasRepoContextRequest(project_path=str(project)))
    assert snap.status == 'missing'
