"""PDT-8 tests for behavioral graph inference."""

from __future__ import annotations

from pathlib import Path

from agent.project_twin.behavioral_graph import BehavioralAnalyzer
from agent.project_twin.contracts import StaticAnalysisRequest, TwinQuery
from agent.project_twin.static_graph import nid
from agent.project_twin.store import SqliteProjectTwinStore


def _write(root: Path, rel: str, content: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _analyze(root: Path):
    return BehavioralAnalyzer().analyze(
        StaticAnalysisRequest(project_id="p1", project_path=str(root), full_rebuild=True)
    )


def test_side_effects_are_inferred_per_kind(tmp_path: Path):
    _write(
        tmp_path,
        "svc.py",
        "import requests, subprocess\n"
        "def save(path, data):\n"
        "    with open(path, 'w') as f:\n"
        "        f.write(data)\n"
        "def fetch_remote(url):\n"
        "    return requests.get(url)\n"
        "def run_job():\n"
        "    subprocess.run(['ls'])\n"
        "def query_db(cur):\n"
        "    return cur.execute('select 1').fetchall()\n",
    )
    delta = _analyze(tmp_path).delta
    kinds = {n.properties.get("kind") for n in delta.nodes if n.node_type == "side_effect"}
    assert {"file", "network", "process", "database"} <= kinds
    # every behavioral fact is inferred + heuristic, never verified
    assert all(n.status == "inferred" for n in delta.nodes)
    assert all(n.derivation == "heuristic_static" for n in delta.nodes)
    assert all(n.confidence < 1.0 for n in delta.nodes)


def test_side_effects_are_queryable(tmp_path: Path):
    _write(tmp_path, "io.py", "def w(p):\n    open(p, 'w').write('x')\n")
    store = SqliteProjectTwinStore(":memory:")
    store.apply_delta(_analyze(tmp_path).delta)
    rows = store.query(TwinQuery(project_id="p1", node_types=["side_effect"]))
    assert any(n.properties.get("kind") == "file" for n in rows.nodes)
    et = {(e.edge_type, e.source_node_id) for e in store.get_snapshot("p1").edges}
    assert ("performs_side_effect", nid("py://io.py#w")) in et
    store.close()


def test_ui_path_is_modeled(tmp_path: Path):
    _write(
        tmp_path,
        "app.js",
        "btn.addEventListener('click', () => {\n"
        "  fetch('/items').then(r => r.json());\n"
        "});\n",
    )
    delta = _analyze(tmp_path).delta
    refs = {n.canonical_ref: n for n in delta.nodes}
    assert "uievent://app.js#click" in refs and refs["uievent://app.js#click"].node_type == "event"
    assert "uiaction://app.js#click" in refs
    assert "apicall://app.js#/items" in refs
    et = {(e.edge_type, e.source_node_id, e.target_node_id) for e in delta.edges}
    # event -> action -> api_call  (a modeled UI path)
    assert ("triggers", nid("uievent://app.js#click"), nid("uiaction://app.js#click")) in et
    assert ("invokes", nid("uiaction://app.js#click"), nid("apicall://app.js#/items")) in et
    # inferred linkage to a structural route
    assert ("reaches_route", nid("apicall://app.js#/items"), nid("route://GET /items")) in et


def test_unresolved_ui_action_emits_uncertainty(tmp_path: Path):
    _write(tmp_path, "app.js", "btn.addEventListener('click', () => { doNothing(); });\n")
    result = _analyze(tmp_path)
    assert any(d["code"] == "ui_action_target_unresolved" for d in result.diagnostics)
