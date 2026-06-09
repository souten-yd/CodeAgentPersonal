"""PDT-11 tests for impact and path analysis."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent.project_twin.behavioral_graph import BehavioralAnalyzer
from agent.project_twin.contracts import ImpactRequest, PathTraceRequest, StaticAnalysisRequest
from agent.project_twin.projection import StaticProjectionService
from agent.project_twin.store import SqliteProjectTwinStore


def _write(root: Path, rel: str, content: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _seed_static(store, root: Path):
    StaticProjectionService(store).refresh(project_id="p1", project_path=str(root), full_rebuild=True)


def _seed_behavioral(store, root: Path):
    delta = BehavioralAnalyzer().analyze(StaticAnalysisRequest(project_id="p1", project_path=str(root), full_rebuild=True)).delta
    store.apply_delta(delta)


def test_function_change_impact_and_recommended_tests(tmp_path: Path):
    _write(tmp_path, "m.py", "def helper():\n    return 1\ndef caller():\n    return helper()\n")
    _write(tmp_path, "test_m.py", "def test_helper():\n    assert helper() == 1\n")
    store = SqliteProjectTwinStore(":memory:")
    _seed_static(store, tmp_path)

    impact = store.assess_impact(ImpactRequest(project_id="p1", changed_refs=["py://m.py#helper"], change_kind="signature", min_confidence=0.0))
    impacted_refs = {i.canonical_ref for i in impact.direct_impacts + impact.transitive_impacts}
    assert "py://m.py#caller" in impacted_refs  # caller depends on helper (reverse call edge)
    assert any(t.canonical_ref == "test://test_m.py::test_helper" for t in impact.recommended_tests)
    store.close()


def test_api_side_effects(tmp_path: Path):
    _write(tmp_path, "api.py",
           "from fastapi import APIRouter\nrouter = APIRouter()\n@router.get('/items')\ndef list_items():\n    open('f').read()\n")
    store = SqliteProjectTwinStore(":memory:")
    _seed_static(store, tmp_path)
    _seed_behavioral(store, tmp_path)

    impact = store.assess_impact(ImpactRequest(project_id="p1", changed_refs=["py://api.py#list_items"], change_kind="body", min_confidence=0.0))
    kinds = {se.canonical_ref for se in impact.side_effects}
    assert any("side_effect://api.py#list_items/file" == ref for ref in kinds)
    store.close()


def test_ui_to_persistence_path(tmp_path: Path):
    _write(tmp_path, "ui.js", "btn.addEventListener('click', () => { fetch('/items'); });\n")
    _write(tmp_path, "api.py",
           "from fastapi import APIRouter\nrouter = APIRouter()\n@router.get('/items')\ndef list_items():\n    open('f').read()\n")
    store = SqliteProjectTwinStore(":memory:")
    _seed_static(store, tmp_path)
    _seed_behavioral(store, tmp_path)

    res = store.trace_path(PathTraceRequest(
        project_id="p1", source_ref="uievent://ui.js#click",
        target_ref="side_effect://api.py#list_items/file", min_confidence=0.0, max_depth=8))
    assert res.paths, "expected a UI-to-persistence path"
    path = res.paths[0]
    assert path.node_refs[0] == "uievent://ui.js#click"
    assert "performs_side_effect" in path.edge_types
    assert "reaches_route" in path.edge_types
    assert path.contains_inferred is True  # behavioral hops are heuristic
    store.close()


def test_no_path_found_is_truthful(tmp_path: Path):
    _write(tmp_path, "m.py", "def a():\n    return 1\n")
    store = SqliteProjectTwinStore(":memory:")
    _seed_static(store, tmp_path)
    res = store.trace_path(PathTraceRequest(project_id="p1", source_ref="py://m.py#a", target_ref="py://nope#z"))
    assert res.paths == []
    assert any(d["code"] == "no_path_found" for d in res.diagnostics)
    store.close()
