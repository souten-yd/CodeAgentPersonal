from __future__ import annotations

import json
from pathlib import Path

from agent.atlas_context_refresh_schema import AtlasContextRefreshRequest
from agent.atlas_repo_index_storage import AtlasRepoIndexStorage
from agent.project_intelligence.adapters.context_refresh_v1 import ProjectIntelligenceContextRefreshAdapter


def _write_latest_repo_index(data_root: Path, project_path: Path, index_run_id: str = "repoindex_test1234") -> None:
    storage = AtlasRepoIndexStorage(data_root)
    payload = {
        "workspace_id": "default",
        "project_path": str(project_path.resolve()),
        "index_run_id": index_run_id,
        "status": "indexed",
        "impacted_files": ["src/main.py", "tests/test_main.py"],
        "related_tests": ["tests/test_main.py"],
        "metadata": {"impacted_symbols": ["main"]},
    }
    storage.save_json(str(project_path.resolve()), "latest.json", payload)


def test_context_refresh_saves_bundle_under_injected_data_root(tmp_path: Path):
    project = tmp_path / "repo"
    project.mkdir()
    svc = ProjectIntelligenceContextRefreshAdapter(data_root=tmp_path)
    bundle = svc.refresh(AtlasContextRefreshRequest(pool_id="pool1", trigger="manual", project_path=str(project), changed_files=["a.py"]))
    root = tmp_path / "atlas" / "context_bundles" / "pool1"
    assert (root / f"{bundle.bundle_id}.json").exists()
    assert (root / f"{bundle.bundle_id}.md").exists()


def test_context_refresh_bundle_metadata_contains_result_paths(tmp_path: Path):
    project = tmp_path / "repo"
    project.mkdir()
    svc = ProjectIntelligenceContextRefreshAdapter(data_root=tmp_path)
    bundle = svc.refresh(AtlasContextRefreshRequest(pool_id="pool2", trigger="manual", project_path=str(project), changed_files=["a.py"]))
    payload = json.loads((tmp_path / "atlas" / "context_bundles" / "pool2" / f"{bundle.bundle_id}.json").read_text(encoding="utf-8"))
    metadata = payload["metadata"]
    assert metadata.get("result_path")
    assert metadata.get("result_path_relative")
    assert metadata.get("md_path")
    assert metadata.get("md_path_relative")
    assert metadata.get("data_root") == str(tmp_path)


def test_context_refresh_repo_context_snapshot_uses_same_data_root(tmp_path: Path):
    project = tmp_path / "repo"
    project.mkdir()
    _write_latest_repo_index(tmp_path, project, index_run_id="repoindex_same_root")
    svc = ProjectIntelligenceContextRefreshAdapter(data_root=tmp_path)
    bundle = svc.refresh(AtlasContextRefreshRequest(pool_id="pool3", trigger="manual", project_path=str(project), changed_files=["src/main.py"]))
    snap = (bundle.metadata or {}).get("repo_context_snapshot", {})
    assert snap.get("status") == "available"
    assert snap.get("index_run_id") == "repoindex_same_root"


def test_context_refresh_missing_repo_index_is_non_blocking(tmp_path: Path):
    project = tmp_path / "repo"
    project.mkdir()
    svc = ProjectIntelligenceContextRefreshAdapter(data_root=tmp_path)
    bundle = svc.refresh(AtlasContextRefreshRequest(pool_id="pool4", trigger="manual", project_path=str(project), changed_files=["src/main.py"]))
    snap = (bundle.metadata or {}).get("repo_context_snapshot", {})
    assert bundle.status in {"ready", "partial"}
    assert snap.get("status") == "missing"


def test_no_path_ca_data_literals_in_context_refresh_repo_context_stack():
    targets = [
        "agent/project_intelligence/adapters/context_refresh_v1.py",
        "app/api/atlas_context_refresh.py",
        "agent/project_intelligence/adapters/repo_context_service.py",
        "app/api/atlas_repo_context.py",
    ]
    for target in targets:
        text = Path(target).read_text(encoding="utf-8")
        assert 'Path("ca_data")' not in text
