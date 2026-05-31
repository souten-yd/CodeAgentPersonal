"""9th: a plan pool created for a selected project binds to that project's working directory
(ca_data/atlas/projects/{name}/work) — the same folder the project drawer lists and downloads — so
generated files don't land in a divergent ca_data/atlas/workspaces/{name} location."""
from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

import main


def _client():
    main.app.state.atlas_ca_data_dir = tempfile.mkdtemp()
    main.app.state.atlas_llm_json_fn = None  # deterministic fallback planner
    return TestClient(main.app), Path(main.app.state.atlas_ca_data_dir)


def test_pool_binds_to_project_work_dir_when_only_workspace_id_given():
    c, root = _client()
    r = c.post("/api/atlas/plan-pools?sync=1", json={"input": "hello world html", "workspace_id": "myproj"})
    assert r.status_code == 200, r.text
    pool = r.json()["plan_pool"]
    expected = str((root / "atlas" / "projects" / "myproj" / "work").resolve())
    assert pool["project_path"] == expected
    assert (root / "atlas" / "projects" / "myproj" / "work").is_dir()


def test_explicit_project_path_is_respected():
    c, root = _client()
    explicit = str((root / "custom" / "dir").resolve())
    r = c.post("/api/atlas/plan-pools?sync=1", json={"input": "x", "workspace_id": "myproj", "project_path": explicit})
    assert r.status_code == 200, r.text
    assert r.json()["plan_pool"]["project_path"] == explicit


def test_default_workspace_is_not_bound():
    c, _root = _client()
    r = c.post("/api/atlas/plan-pools?sync=1", json={"input": "x", "workspace_id": "default"})
    assert r.status_code == 200, r.text
    # No concrete project -> left unbound (empty), preserving the prior default behavior.
    assert r.json()["plan_pool"]["project_path"] == ""


def test_unsafe_workspace_id_does_not_escape():
    c, root = _client()
    # An unsafe workspace_id is rejected upstream (journal path validation); the binding guard also
    # refuses "/", "\\" and ".." segments. Either way, no directory is created outside the projects root.
    try:
        c.post("/api/atlas/plan-pools?sync=1", json={"input": "x", "workspace_id": "../escape"})
    except Exception:
        pass
    assert not (root / "atlas" / "escape").exists()
    assert not (root.parent / "escape").exists()
