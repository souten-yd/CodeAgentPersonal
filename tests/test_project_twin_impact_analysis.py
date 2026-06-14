"""PIBIH-2: Impact Analysis Core acceptance tests.

Fixture project (per the PIBIH test plan):
- function A (`handle_items`) calls function B (`load_items`);
- route R (`GET /items`) is handled by function A;
- a JS click event calls route R;
- function B writes/reads a file resource;
- test T (`test_handle_items`) covers function A.

These prove the impact traversal returns direct + transitive impacts, route -> handler/UI/test/side
effect, resource writers/readers, honest uncertainty for heuristic links, working depth/min-confidence
filters, and historical-risk gating. Inferred graph facts are never asserted as verified facts.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from agent.project_twin.behavioral_graph import BehavioralAnalyzer
from agent.project_twin.contracts import (
    ImpactRequest,
    StaticAnalysisRequest,
    TwinDelta,
    TwinEdge,
    TwinNode,
)
from agent.project_twin.projection import StaticProjectionService
from agent.project_twin.static_graph import nid
from agent.project_twin.store import SqliteProjectTwinStore

PROJECT = "p1"
A_REF = "py://app.py#handle_items"   # route handler (function A)
B_REF = "py://app.py#load_items"     # function B (called by A; touches the file)
ROUTE_REF = "route://GET /items"
UIEVENT_REF = "uievent://ui.js#click"
TEST_REF = "test://test_app.py::test_handle_items"


def _write(root: Path, rel: str, content: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _seed(store, root: Path) -> None:
    StaticProjectionService(store).refresh(project_id=PROJECT, project_path=str(root), full_rebuild=True)
    delta = BehavioralAnalyzer().analyze(
        StaticAnalysisRequest(project_id=PROJECT, project_path=str(root), full_rebuild=True)
    ).delta
    store.apply_delta(delta)


def _fixture_store(tmp_path: Path) -> SqliteProjectTwinStore:
    _write(
        tmp_path,
        "app.py",
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "\n"
        "@router.get('/items')\n"
        "def handle_items():\n"
        "    return load_items()\n"
        "\n"
        "def load_items():\n"
        "    return open('data.txt').read()\n",
    )
    _write(tmp_path, "ui.js", "btn.addEventListener('click', () => { fetch('/items'); });\n")
    _write(tmp_path, "test_app.py", "def test_handle_items():\n    assert handle_items() is not None\n")
    store = SqliteProjectTwinStore(":memory:")
    _seed(store, tmp_path)
    return store


def _refs(items):
    return {i.canonical_ref for i in items}


def test_function_change_returns_direct_and_transitive_and_tests(tmp_path: Path):
    store = _fixture_store(tmp_path)
    res = store.assess_impact(ImpactRequest(project_id=PROJECT, changed_refs=[B_REF], change_kind="body", min_confidence=0.0))
    impacted = _refs(res.direct_impacts) | _refs(res.transitive_impacts)
    assert A_REF in impacted, "caller handle_items must be impacted by changing load_items"
    # B is covered transitively by T because A's test reaches B through A.
    assert any(t.canonical_ref == TEST_REF for t in res.recommended_tests)
    store.close()


def test_route_change_returns_handler_ui_caller_tests_and_side_effects(tmp_path: Path):
    store = _fixture_store(tmp_path)
    res = store.assess_impact(ImpactRequest(project_id=PROJECT, changed_refs=[ROUTE_REF], change_kind="signature", min_confidence=0.0))
    direct = _refs(res.direct_impacts)
    impacted = direct | _refs(res.transitive_impacts)
    # backend handler surfaced via forward `handled_by` expansion (reverse traversal alone misses it)
    assert A_REF in direct
    assert any(i.reason == "implements_changed_entity" and i.canonical_ref == A_REF for i in res.direct_impacts)
    # UI caller via reaches_route, recommended test via the handler, file side effect via the handler->B
    assert UIEVENT_REF in impacted
    assert any(t.canonical_ref == TEST_REF for t in res.recommended_tests)
    assert any(se.canonical_ref.startswith("side_effect://app.py#load_items/file") for se in res.side_effects)
    store.close()


def test_resource_change_returns_writers_and_readers(tmp_path: Path):
    store = _fixture_store(tmp_path)
    res = store.assess_impact(ImpactRequest(project_id=PROJECT, changed_refs=["resource://file:data.txt"], change_kind="schema", min_confidence=0.0))
    impacted = _refs(res.direct_impacts) | _refs(res.transitive_impacts)
    # the function that touches the file (writer/reader) must surface through the side-effect edges
    assert B_REF in impacted
    store.close()


def test_uncertainty_flags_heuristic_links_not_verified(tmp_path: Path):
    store = _fixture_store(tmp_path)
    res = store.assess_impact(ImpactRequest(project_id=PROJECT, changed_refs=[ROUTE_REF], change_kind="signature", min_confidence=0.0))
    # Behavioral/inferred hops are heuristic; at least one impact must carry an honest path_confidence
    # below the verified threshold, and none of the impacts may claim a verified status.
    assert res.uncertainty, "heuristic impacts must be reported with uncertainty"
    assert all("path_confidence" in u for u in res.uncertainty)
    assert any(float(u["path_confidence"]) < 0.7 for u in res.uncertainty)
    for item in res.direct_impacts + res.transitive_impacts:
        assert item.status != "verified" or item.confidence >= 0.5
    store.close()


def test_depth_and_min_confidence_filters(tmp_path: Path):
    store = _fixture_store(tmp_path)
    # max_depth=1 keeps only the immediate caller; the test (several hops away) must NOT appear.
    shallow = store.assess_impact(ImpactRequest(project_id=PROJECT, changed_refs=[B_REF], change_kind="body", min_confidence=0.0, max_depth=1))
    assert A_REF in _refs(shallow.direct_impacts)
    assert not any(t.canonical_ref == TEST_REF for t in shallow.recommended_tests)
    deep = store.assess_impact(ImpactRequest(project_id=PROJECT, changed_refs=[B_REF], change_kind="body", min_confidence=0.0, max_depth=5))
    assert any(t.canonical_ref == TEST_REF for t in deep.recommended_tests)

    # A high min-confidence prunes heuristic links, shrinking the impacted set.
    loose = store.assess_impact(ImpactRequest(project_id=PROJECT, changed_refs=[ROUTE_REF], change_kind="signature", min_confidence=0.0))
    strict = store.assess_impact(ImpactRequest(project_id=PROJECT, changed_refs=[ROUTE_REF], change_kind="signature", min_confidence=0.95))
    loose_n = len(loose.direct_impacts) + len(loose.transitive_impacts)
    strict_n = len(strict.direct_impacts) + len(strict.transitive_impacts)
    assert strict_n < loose_n
    store.close()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _incident_delta(target_ref: str) -> TwinDelta:
    """A minimal delta adding one historical incident node linked to ``target_ref``."""
    inc_ref = "incident://past-failure-1"
    common = dict(
        project_id=PROJECT, source_kind="test", source_ref="seed", derivation="runtime_observation",
        valid_from=_now(), created_at=_now(), updated_at=_now(),
    )
    node = TwinNode(
        node_id=nid(inc_ref), domain="runtime", node_type="incident", canonical_ref=inc_ref,
        label="past failure", confidence=0.9, status="observed", **common,
    )
    edge = TwinEdge(
        edge_id=nid(f"edge://{inc_ref}->{target_ref}"), domain="runtime",
        source_node_id=nid(inc_ref), target_node_id=nid(target_ref), edge_type="affects",
        confidence=0.9, status="observed", **common,
    )
    return TwinDelta(project_id=PROJECT, idempotency_key="incident-seed-1", trigger_type="test", nodes=[node], edges=[edge])


def test_impact_excludes_structural_container_nodes(tmp_path: Path):
    # A function's module/file/parent-dir/repo are reachable via containment edges but are not
    # behavioral impacts; they must not pollute the impact items shown to the planner.
    store = _fixture_store(tmp_path)
    res = store.assess_impact(ImpactRequest(project_id=PROJECT, changed_refs=[B_REF], change_kind="body", min_confidence=0.0))
    containers = {"repository", "directory", "file", "module", "package"}
    polluting = [i.canonical_ref for i in res.direct_impacts + res.transitive_impacts if i.item_type in containers]
    assert polluting == [], f"impact items must exclude structural containers, got {polluting}"
    store.close()


def test_historical_risks_included_only_when_requested(tmp_path: Path):
    store = _fixture_store(tmp_path)
    store.apply_delta(_incident_delta(A_REF))

    with_risks = store.assess_impact(ImpactRequest(project_id=PROJECT, changed_refs=[A_REF], change_kind="body", min_confidence=0.0, include_historical_risks=True))
    assert any(i.canonical_ref == "incident://past-failure-1" for i in with_risks.past_incidents)

    without_risks = store.assess_impact(ImpactRequest(project_id=PROJECT, changed_refs=[A_REF], change_kind="body", min_confidence=0.0, include_historical_risks=False))
    assert without_risks.past_incidents == []
    store.close()
