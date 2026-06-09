"""PDT-3 tests for the static structural analyzer and projection service."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent.project_twin.contracts import StaticAnalysisRequest, TwinQuery
from agent.project_twin.projection import StaticProjectionService
from agent.project_twin.static_graph import StaticStructuralAnalyzer, nid
from agent.project_twin.store import SqliteProjectTwinStore


def _write(root: Path, rel: str, content: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _analyze(root: Path, changed=None, full=False):
    return StaticStructuralAnalyzer().analyze(
        StaticAnalysisRequest(
            project_id="p1",
            project_path=str(root),
            changed_paths=changed or [],
            full_rebuild=full,
        )
    )


# --- python structure --------------------------------------------------------

def test_python_symbols_and_edges(tmp_path: Path):
    _write(
        tmp_path,
        "pkg/mod.py",
        "import os\n"
        "from pkg.other import Base\n"
        "class A(Base):\n"
        "    def m(self):\n"
        "        return helper()\n"
        "def helper():\n"
        "    return 1\n",
    )
    delta = _analyze(tmp_path, full=True).delta
    refs = {n.canonical_ref: n for n in delta.nodes}
    assert "file://pkg/mod.py" in refs
    assert "module://pkg.mod" in refs
    assert "py://pkg/mod.py#A" in refs and refs["py://pkg/mod.py#A"].node_type == "class"
    assert refs["py://pkg/mod.py#A.m"].node_type == "method"
    assert refs["py://pkg/mod.py#helper"].node_type == "function"

    edge_types = {(e.edge_type, e.source_node_id, e.target_node_id) for e in delta.edges}
    assert ("inherits", nid("py://pkg/mod.py#A"), nid("pyname://Base")) in edge_types
    assert ("imports", nid("module://pkg.mod"), nid("module://os")) in edge_types
    assert ("imports", nid("module://pkg.mod"), nid("module://pkg.other")) in edge_types
    assert ("calls", nid("py://pkg/mod.py#A.m"), nid("pyname://helper")) in edge_types


def test_canonical_refs_are_deterministic(tmp_path: Path):
    _write(tmp_path, "a.py", "def f():\n    return 1\n")
    d1 = _analyze(tmp_path, full=True).delta
    d2 = _analyze(tmp_path, full=True).delta
    assert sorted(n.canonical_ref for n in d1.nodes) == sorted(n.canonical_ref for n in d2.nodes)
    assert sorted(e.edge_id for e in d1.edges) == sorted(e.edge_id for e in d2.edges)


# --- FastAPI / tests / fixtures ---------------------------------------------

def test_fastapi_route_projection(tmp_path: Path):
    _write(
        tmp_path,
        "api.py",
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "@router.get('/items')\n"
        "def list_items():\n"
        "    return []\n",
    )
    delta = _analyze(tmp_path, full=True).delta
    refs = {n.canonical_ref: n for n in delta.nodes}
    assert "route://GET /items" in refs and refs["route://GET /items"].node_type == "api_route"
    et = {(e.edge_type, e.source_node_id, e.target_node_id) for e in delta.edges}
    assert ("handled_by", nid("route://GET /items"), nid("py://api.py#list_items")) in et


def test_test_and_fixture_nodes(tmp_path: Path):
    _write(
        tmp_path,
        "test_sample.py",
        "import pytest\n"
        "@pytest.fixture\n"
        "def thing():\n"
        "    return 1\n"
        "def test_it(thing):\n"
        "    assert thing == 1\n",
    )
    delta = _analyze(tmp_path, full=True).delta
    types = {n.node_type for n in delta.nodes}
    assert "test" in types and "fixture" in types
    refs = {n.canonical_ref for n in delta.nodes}
    assert "test://test_sample.py::test_it" in refs
    assert "fixture://test_sample.py::thing" in refs


# --- web assets --------------------------------------------------------------

def test_html_and_js_links(tmp_path: Path):
    _write(tmp_path, "ui.html", '<html><head><link href="app.css"><script src="app.js"></script></head></html>')
    _write(tmp_path, "app.js", "import {x} from './util.js';\nbtn.addEventListener('click', () => {});\n")
    delta = _analyze(tmp_path, full=True).delta
    et = {e.edge_type for e in delta.edges}
    assert "loads_script" in et and "links_asset" in et
    assert "imports" in et  # js import
    assert "handles_event" in et
    refs = {n.canonical_ref for n in delta.nodes}
    assert "event://app.js#click" in refs


# --- diagnostics -------------------------------------------------------------

def test_parse_failure_creates_diagnostic(tmp_path: Path):
    _write(tmp_path, "broken.py", "def f(:\n  pass\n")
    result = _analyze(tmp_path, full=True)
    assert any(d["code"] == "parse_error" and d["file"] == "broken.py" for d in result.diagnostics)
    # The file node is still created even though parsing failed.
    assert any(n.canonical_ref == "file://broken.py" for n in result.delta.nodes)


# --- projection service: incremental refresh ---------------------------------

@pytest.fixture()
def store():
    s = SqliteProjectTwinStore(":memory:")
    yield s
    s.close()


def _current_row(store, canonical_ref):
    return store._conn.execute(
        "SELECT revision_id, valid_to, status FROM twin_nodes WHERE canonical_ref = ? AND valid_to IS NULL",
        (canonical_ref,),
    ).fetchone()


def test_single_file_update_avoids_unrelated_rebuild(tmp_path: Path, store):
    _write(tmp_path, "a.py", "def fa():\n    return 1\n")
    _write(tmp_path, "b.py", "def fb():\n    return 2\n")
    svc = StaticProjectionService(store)
    rev_full = svc.refresh(project_id="p1", project_path=str(tmp_path), full_rebuild=True)

    b_before = _current_row(store, "py://b.py#fb")
    assert b_before is not None and b_before["revision_id"] == rev_full.revision_id

    # change only a.py
    _write(tmp_path, "a.py", "def fa():\n    return 99\n")
    rev_inc = svc.refresh(project_id="p1", project_path=str(tmp_path), changed_paths=["a.py"])
    assert rev_inc.revision_id != rev_full.revision_id

    # b.py symbol is untouched: still current and still owned by the full-rebuild revision.
    b_after = _current_row(store, "py://b.py#fb")
    assert b_after is not None
    assert b_after["revision_id"] == rev_full.revision_id
    assert b_after["valid_to"] is None


def test_deleted_symbol_is_invalidated(tmp_path: Path, store):
    _write(tmp_path, "a.py", "def f():\n    return 1\ndef g():\n    return 2\n")
    svc = StaticProjectionService(store)
    svc.refresh(project_id="p1", project_path=str(tmp_path), full_rebuild=True)
    assert _current_row(store, "py://a.py#g") is not None

    # remove g
    _write(tmp_path, "a.py", "def f():\n    return 1\n")
    svc.refresh(project_id="p1", project_path=str(tmp_path), changed_paths=["a.py"])

    # g is no longer current and is recorded as invalidated (not silently lost).
    assert _current_row(store, "py://a.py#g") is None
    invalidated = store.query(TwinQuery(project_id="p1", statuses=["invalidated"]))
    assert any(n.canonical_ref == "py://a.py#g" and n.status == "invalidated" for n in invalidated.nodes)
    # f survives.
    assert _current_row(store, "py://a.py#f") is not None
