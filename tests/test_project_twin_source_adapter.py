"""PIR-3 source snapshot adapter tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent.project_twin.project_identity import compute_project_identity
from agent.project_twin.source_adapter import ProjectSourceAdapter, SourceSnapshotError


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_snapshot_lists_safe_text_files_and_parser_manifest(tmp_path: Path) -> None:
    _write(tmp_path, "app.py", "def hello():\n    return 1\n")
    (tmp_path / "blob.bin").write_bytes(b"\0\1\2")

    snapshot = ProjectSourceAdapter().snapshot(tmp_path)

    assert [item.path for item in snapshot.files] == ["app.py"]
    assert snapshot.parser_manifest["source_adapter"].startswith("source_adapter.")
    assert snapshot.parser_manifest["static_graph"].startswith("static_graph.")
    assert any("binary" in diagnostic.message for diagnostic in snapshot.diagnostics)


def test_changed_path_escape_is_rejected(tmp_path: Path) -> None:
    _write(tmp_path, "app.py", "x = 1\n")

    with pytest.raises(SourceSnapshotError):
        ProjectSourceAdapter().snapshot(tmp_path, requested_changed_paths=["../outside.py"])


def test_dirty_working_tree_hash_changes_for_same_size_edit(tmp_path: Path) -> None:
    _write(tmp_path, "app.py", "value = 1\n")
    before = compute_project_identity(tmp_path).working_tree_hash

    _write(tmp_path, "app.py", "value = 2\n")
    after = compute_project_identity(tmp_path).working_tree_hash

    assert before != after
