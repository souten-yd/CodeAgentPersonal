"""PIBIH-3 (slice 1): resource-effect direction + identity and config/env facts.

Covers the PIBIH-3 acceptance criteria advanced by this slice:
- resource effects include a direction (read/write/mutate/delete) and a resource identity;
- config/environment reads are modeled as a `config` resource (deferred from PIBIH-2);
- def-use edges are present and deterministic across rebuilds;
- every new behavioral fact remains inferred / heuristic_static (never verified).

Import-alias call resolution and ambiguous-call diagnostics remain for a later PIBIH-3 slice.
"""

from __future__ import annotations

from pathlib import Path

from agent.project_twin.behavioral_graph import BehavioralAnalyzer
from agent.project_twin.contracts import ImpactRequest, StaticAnalysisRequest
from agent.project_twin.projection import StaticProjectionService
from agent.project_twin.store import SqliteProjectTwinStore

SOURCE = (
    "import os\n"
    "\n"
    "def reader():\n"
    "    return open('data.txt').read()\n"
    "\n"
    "def writer():\n"
    "    open('out.txt', 'w')\n"
    "\n"
    "def remover():\n"
    "    os.remove('tmp.txt')\n"
    "\n"
    "def configured():\n"
    "    mode = os.environ.get('APP_MODE')\n"
    "    return mode\n"
)


def _write(root: Path, rel: str, content: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _analyze(root: Path):
    return BehavioralAnalyzer().analyze(
        StaticAnalysisRequest(project_id="p1", project_path=str(root), full_rebuild=True)
    ).delta


def _side_effects(delta):
    return [n for n in delta.nodes if n.node_type == "side_effect"]


def _has_effect(delta, *, fn: str, kind: str, direction: str) -> bool:
    # sym_ref is itself `py://m.py#fn`, so the effect ref is `side_effect://py://m.py#fn/<kind>/...`.
    prefix = f"side_effect://py://m.py#{fn}/{kind}/"
    return any(
        n.canonical_ref.startswith(prefix) and n.properties.get("direction") == direction
        for n in _side_effects(delta)
    )


def test_file_effect_directions_and_identity(tmp_path: Path):
    _write(tmp_path, "m.py", SOURCE)
    delta = _analyze(tmp_path)

    assert _has_effect(delta, fn="reader", kind="file", direction="read")
    assert _has_effect(delta, fn="writer", kind="file", direction="write")
    assert _has_effect(delta, fn="remover", kind="file", direction="delete")

    refs = {n.canonical_ref for n in delta.nodes}
    # resource identity nodes are present for the named files
    assert "resource://file:out.txt" in refs
    assert "resource://file:tmp.txt" in refs
    # the effect edges carry the direction property
    write_edges = [
        e for e in delta.edges
        if e.edge_type == "performs_side_effect" and e.properties.get("direction") == "write"
    ]
    assert write_edges


def test_config_env_read_is_modeled(tmp_path: Path):
    _write(tmp_path, "m.py", SOURCE)
    delta = _analyze(tmp_path)

    refs = {n.canonical_ref for n in delta.nodes}
    assert "resource://config:APP_MODE" in refs
    assert _has_effect(delta, fn="configured", kind="config", direction="read")


def test_config_change_impact_returns_reader(tmp_path: Path):
    _write(tmp_path, "m.py", SOURCE)
    store = SqliteProjectTwinStore(":memory:")
    StaticProjectionService(store).refresh(project_id="p1", project_path=str(tmp_path), full_rebuild=True)
    store.apply_delta(_analyze(tmp_path))

    impact = store.assess_impact(ImpactRequest(
        project_id="p1", changed_refs=["resource://config:APP_MODE"], change_kind="value", min_confidence=0.0,
    ))
    impacted = {i.canonical_ref for i in impact.direct_impacts + impact.transitive_impacts}
    assert "py://m.py#configured" in impacted
    store.close()


def test_defuse_edges_are_deterministic(tmp_path: Path):
    _write(tmp_path, "m.py", SOURCE)
    first = _analyze(tmp_path)
    second = _analyze(tmp_path)

    assert any(e.edge_type == "defines" for e in first.edges)
    assert {n.canonical_ref for n in first.nodes} == {n.canonical_ref for n in second.nodes}
    assert {e.edge_id for e in first.edges} == {e.edge_id for e in second.edges}


def test_all_behavioral_facts_remain_inferred(tmp_path: Path):
    _write(tmp_path, "m.py", SOURCE)
    delta = _analyze(tmp_path)

    assert delta.nodes, "expected behavioral nodes"
    for n in delta.nodes:
        assert n.status == "inferred"
        assert n.derivation == "heuristic_static"
        assert n.confidence < 1.0
    for e in delta.edges:
        assert e.status == "inferred"
        assert e.derivation == "heuristic_static"
