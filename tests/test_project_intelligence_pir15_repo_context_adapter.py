"""PIR-15 repo-context API adapter cutover tests."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from agent.atlas_repo_context_schema import AtlasRepoContextRequest
from agent.project_intelligence.adapters.atlas_repo_context import AtlasRepoContextAdapter
from agent.project_intelligence.inspection.consumer_inventory import build_inventory
from app.server import create_app


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_repo_context_adapter_preserves_scope_summary(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("def app():\n    return 'ok'\n", encoding="utf-8")

    adapter = AtlasRepoContextAdapter(data_root=tmp_path / "data")
    result = adapter.build_plan_scope_summary(
        AtlasRepoContextRequest(project_path=str(tmp_path), target_files=["app.py"])
    )

    assert result.status in {"available", "missing", "partial"}
    assert result.target_files == ["app.py"]


def test_repo_context_api_uses_project_intelligence_adapter(tmp_path: Path, monkeypatch) -> None:
    captured: dict[str, str] = {}
    original = AtlasRepoContextAdapter.build_planner_packaging_v2

    def wrapped(self: AtlasRepoContextAdapter, req):
        captured["data_root"] = str(self.data_root)
        return original(self, req)

    monkeypatch.setattr(AtlasRepoContextAdapter, "build_planner_packaging_v2", wrapped)
    app = create_app()
    app.state.atlas_ca_data_root = str(tmp_path / "custom_root")
    client = TestClient(app)

    response = client.post("/api/atlas/repo-context/planner-packaging-v2", json={"project_path": str(tmp_path)})

    assert response.status_code == 200
    assert captured["data_root"].endswith("custom_root")


def test_repo_context_api_direct_legacy_imports_move_behind_adapter() -> None:
    inventory = build_inventory(REPO_ROOT)
    api_entry = next(
        entry for entry in inventory["production_entrypoints"]
        if entry["path"] == "app/api/atlas_repo_context.py"
    )

    assert api_entry["imports_project_intelligence"] is True
    assert api_entry["imports_legacy_capability"] == []

    adapters = {row["module"]: row for row in inventory["project_intelligence"]["adapters"]}
    assert adapters["agent.project_intelligence.adapters.atlas_repo_context"]["present"] is True
    assert inventory["summary"]["adapter_module_count"] == 5
