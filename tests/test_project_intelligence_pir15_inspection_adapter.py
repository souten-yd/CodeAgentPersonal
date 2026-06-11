"""PIR-15 read-only inspection adapter cutover tests."""

from __future__ import annotations

from pathlib import Path

from agent.project_intelligence.adapters.atlas_inspection import AtlasInspectionAdapter
from agent.project_intelligence.inspection.consumer_inventory import build_inventory


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_inspection_adapter_preserves_project_tree_and_git_status(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("def hello():\n    return 'hi'\n", encoding="utf-8")

    adapter = AtlasInspectionAdapter()
    tree = adapter.project_tree(str(repo), max_files=10)
    outline = adapter.file_outline(str(repo), "app.py")
    status = adapter.git_status(str(repo))

    assert "app.py" in tree.tree
    assert any("def hello" in item for item in outline.outline)
    assert isinstance(status.entries, list)


def test_read_only_inspection_direct_consumers_move_behind_adapter() -> None:
    inventory = build_inventory(REPO_ROOT)
    legacy_rows = {row["legacy_module"]: row for row in inventory["legacy_consumers"]}

    project = legacy_rows["agent.atlas_project_inspection_service"]
    git = legacy_rows["agent.atlas_git_inspection_service"]
    for row in (project, git):
        assert row["production_consumer_count"] == 0
        assert row["production_consumers"] == []
        assert row["adapter_consumer_count"] == 1
        assert row["adapter_consumers"] == [
            {
                "module": "agent.project_intelligence.adapters.atlas_inspection",
                "path": "agent/project_intelligence/adapters/atlas_inspection.py",
            }
        ]

    adapters = {row["module"]: row for row in inventory["project_intelligence"]["adapters"]}
    assert adapters["agent.project_intelligence.adapters.atlas_inspection"]["present"] is True
    assert inventory["summary"]["adapter_module_count"] == 8
