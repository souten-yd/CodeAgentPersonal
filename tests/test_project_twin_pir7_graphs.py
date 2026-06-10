"""PIR-7 behavioral graph recovery tests."""

from __future__ import annotations

from pathlib import Path

from agent.project_intelligence.contracts import ProjectIdentity
from agent.project_twin.behavioral_graph import BehavioralAnalyzer
from agent.project_twin.contracts import StaticAnalysisRequest
from agent.project_twin.facade import OpenTwinRequest, TwinQueryKind, TwinQueryRequest
from agent.project_twin.module import DigitalTwinModuleImpl
from agent.project_twin.static_graph import nid


def _write(root: Path, rel: str, content: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _analyze(root: Path):
    return BehavioralAnalyzer().analyze(
        StaticAnalysisRequest(project_id="p1", project_path=str(root), full_rebuild=True)
    ).delta


def test_pir7_cfg_def_use_resource_state_and_recovery_are_materialized(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "service.py",
        """
def transform(data):
    cleaned = data.strip()
    return cleaned

def save(path, data, db):
    state = "new"
    if not data:
        state = "empty"
        return False
    for attempt in range(3):
        try:
            payload = transform(data)
            with open(path, "w") as fh:
                fh.write(payload)
            db.execute("INSERT INTO users VALUES (?)", (payload,))
            state = "done"
            return True
        except TimeoutError:
            backoff(attempt)
            db.rollback()
            state = "retry"
    state = "failed"
    return False
""".lstrip(),
    )

    delta = _analyze(tmp_path)
    node_refs = {node.canonical_ref: node for node in delta.nodes}
    edge_types = {edge.edge_type for edge in delta.edges}
    edges = {(edge.edge_type, edge.source_node_id, edge.target_node_id) for edge in delta.edges}

    assert {"cfg_condition_true", "cfg_condition_false", "cfg_loop_back", "cfg_exception", "cfg_return"} <= edge_types
    assert any(
        node.node_type == "cfg_block" and node.properties.get("kind") == "try"
        for node in delta.nodes
    )
    assert any(node.node_type == "definition" and node.label == "payload" for node in delta.nodes)
    assert any(edge.edge_type == "interprocedural_argument_flow" for edge in delta.edges)
    assert "resource://database:users" in node_refs
    assert "flows_to_resource" in edge_types
    assert any(node.node_type == "state" and node.label == "state=done" for node in delta.nodes)
    assert "state_transition" in edge_types
    assert any(node.node_type == "recovery" and node.properties.get("kind") == "retry" for node in delta.nodes)
    assert any(node.node_type == "recovery" and node.properties.get("kind") == "rollback" for node in delta.nodes)
    assert (
        "persists_to",
        nid("py://service.py#save"),
        nid("resource://database:users"),
    ) in edges


def test_pir7_ui_handlers_only_invoke_apis_in_reachable_scope(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "ui.js",
        """
save.addEventListener("click", () => {
  fetch("/save");
});
cancel.addEventListener("change", () => {
  fetch("/cancel");
});
fetch("/global");
""".lstrip(),
    )

    delta = _analyze(tmp_path)
    invokes = {(edge.source_node_id, edge.target_node_id) for edge in delta.edges if edge.edge_type == "invokes"}

    save_action = nid("uiaction://ui.js#click")
    assert (save_action, nid("apicall://ui.js#get:/save")) in invokes
    assert (save_action, nid("apicall://ui.js#get:/cancel")) not in invokes
    assert (save_action, nid("apicall://ui.js#get:/global")) not in invokes


def test_pir7_behavioral_graph_is_connected_to_concrete_twin_facade(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "api.py",
        """
def handler(db, value):
    payload = value.strip()
    db.execute("INSERT INTO items VALUES (?)", (payload,))
    return payload
""".lstrip(),
    )
    module = DigitalTwinModuleImpl(db_path=":memory:")
    project = ProjectIdentity(project_id="proj", workspace_id="ws", project_path=str(tmp_path))
    try:
        state = module.open_project(OpenTwinRequest(project=project, requested_capabilities=["source_snapshot"]))
        assert state.twin_revision_id
        query = module.query(
            TwinQueryRequest(
                project_id="proj",
                workspace_id="ws",
                kind=TwinQueryKind.SEARCH,
                text="resource://database:items",
                limit=10,
            )
        )
        assert any(item.ref == "resource://database:items" for item in query.items)
        snapshot = module._store.get_snapshot("proj\x1fws")
        assert any(edge.edge_type == "flows_to_resource" for edge in snapshot.edges)
    finally:
        module.close()
