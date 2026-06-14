"""Digital Twin / Deep Behavioral Graph behavior evaluation harness.

Builds a self-contained *virtual project* (Python services + FastAPI routes + JS UI + config + tests),
projects it into an in-memory Project Twin (static graph + behavioral graph), and runs a battery of
behavior checks (impact analysis, call resolution, resource direction, UI->API->route->handler path,
config impact, ambiguous-call detection). Prints a PASS/FAIL report so the twin's real behavior on a
realistic project can be assessed and a remediation plan written.

Run: python scripts/twin_behavior_eval.py
Exit code is the number of failing checks (0 = all appropriate).
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from agent.project_twin.behavioral_graph import BehavioralAnalyzer
from agent.project_twin.contracts import ImpactRequest, PathTraceRequest, StaticAnalysisRequest
from agent.project_twin.projection import StaticProjectionService
from agent.project_twin.static_graph import StaticStructuralAnalyzer, nid
from agent.project_twin.store import SqliteProjectTwinStore

PID = "virtual"


VFILES = {
    "app/__init__.py": "",
    "app/config.py": (
        "import os\n\n"
        "def get_mode():\n"
        "    return os.environ.get('APP_MODE')\n\n"
        "def get_db_url():\n"
        "    return os.getenv('DATABASE_URL')\n"
    ),
    "app/db.py": (
        "import sqlite3\n\n"
        "def connect():\n"
        "    return sqlite3.connect('app.db')\n\n"
        "def save_item(conn, item):\n"
        "    conn.execute('INSERT INTO items VALUES (?)', (item,))\n"
        "    conn.commit()\n\n"
        "def load_items(conn):\n"
        "    cur = conn.cursor()\n"
        "    return cur.fetchall()\n"
    ),
    "app/services.py": (
        "from app.db import save_item, load_items, connect\n"
        "from app.config import get_mode\n\n"
        "def create_item(item):\n"
        "    mode = get_mode()\n"
        "    conn = connect()\n"
        "    save_item(conn, item)\n"
        "    return mode\n\n"
        "def list_items():\n"
        "    conn = connect()\n"
        "    return load_items(conn)\n"
    ),
    "app/api.py": (
        "from fastapi import APIRouter\n"
        "from app.services import create_item, list_items\n\n"
        "router = APIRouter()\n\n"
        "@router.post('/items')\n"
        "def post_item(item: str):\n"
        "    return create_item(item)\n\n"
        "@router.get('/items')\n"
        "def get_items():\n"
        "    return list_items()\n"
    ),
    "web/app.js": (
        "addItemBtn.addEventListener('click', () => {\n"
        "    fetch('/items', { method: 'POST' });\n"
        "});\n"
        "listBtn.addEventListener('click', () => {\n"
        "    fetch('/items');\n"
        "});\n"
    ),
    "tests/test_services.py": (
        "from app.services import create_item\n\n"
        "def test_create_item():\n"
        "    assert create_item('x') is not None\n"
    ),
    "tests/test_api.py": (
        "from app.api import get_items\n\n"
        "def test_get_items():\n"
        "    assert get_items() is not None\n"
    ),
    # --- edge/adversarial inputs to surface imprecision ---
    "app/models.py": (
        "class ItemRepo:\n"
        "    def save(self, item):\n"
        "        self._validate(item)\n"
        "        return item\n\n"
        "    def _validate(self, item):\n"
        "        return bool(item)\n"
    ),
    "app/legacy.py": (
        "import os\n\n"
        "def legacy_flag():\n"
        "    return os.environ['LEGACY_FLAG']\n"
    ),
}


def build_virtual_project(root: Path) -> None:
    for rel, content in VFILES.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")


def build_twin(root: Path) -> SqliteProjectTwinStore:
    store = SqliteProjectTwinStore(":memory:")
    StaticProjectionService(store).refresh(project_id=PID, project_path=str(root), full_rebuild=True)
    delta = BehavioralAnalyzer().analyze(
        StaticAnalysisRequest(project_id=PID, project_path=str(root), full_rebuild=True)
    ).delta
    store.apply_delta(delta)
    return store


class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[bool, str, str]] = []

    def check(self, ok: bool, name: str, detail: str = "") -> None:
        self.rows.append((bool(ok), name, detail))

    def emit(self) -> int:
        fails = 0
        print("\n=== Digital Twin behavior evaluation (virtual project) ===\n")
        for ok, name, detail in self.rows:
            mark = "PASS" if ok else "FAIL"
            if not ok:
                fails += 1
            line = f"[{mark}] {name}"
            if detail:
                line += f"  -- {detail}"
            print(line)
        print(f"\n{len(self.rows) - fails}/{len(self.rows)} checks appropriate; {fails} failing.\n")
        return fails


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="twin_eval_"))
    try:
        return _run(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _run(tmp: Path) -> int:
    build_virtual_project(tmp)
    store = build_twin(tmp)
    r = Report()

    def impact(ref, **kw):
        kw.setdefault("change_kind", "body")
        kw.setdefault("min_confidence", 0.0)
        return store.assess_impact(ImpactRequest(project_id=PID, changed_refs=[ref], **kw))

    def refs(items):
        return {i.canonical_ref for i in items}

    # 1. Cross-file transitive impact: change db.save_item -> service create_item -> route -> test.
    imp = impact("py://app/db.py#save_item")
    impacted = refs(imp.direct_impacts) | refs(imp.transitive_impacts)
    r.check("py://app/services.py#create_item" in impacted, "db.save_item change impacts service create_item", str(sorted(impacted))[:200])
    r.check(any("post_item" in x or "route://POST /items" in x for x in impacted), "db.save_item change reaches POST /items route/handler")
    r.check(any(t.canonical_ref.endswith("test_create_item") for t in imp.recommended_tests), "db.save_item change recommends test_create_item")

    # 2. Route change -> handler + UI caller + test + side effects.
    imp_r = impact("route://GET /items", change_kind="signature")
    direct_r = refs(imp_r.direct_impacts)
    impacted_r = direct_r | refs(imp_r.transitive_impacts)
    r.check("py://app/api.py#get_items" in direct_r, "GET /items route surfaces backend handler get_items", str(sorted(direct_r))[:200])
    r.check(any(x.startswith("uievent://") for x in impacted_r), "GET /items route surfaces UI caller event")
    r.check(any(t.canonical_ref.endswith("test_get_items") for t in imp_r.recommended_tests), "GET /items route recommends test_get_items")

    # 3. Config change -> readers.
    imp_c = impact("resource://config:APP_MODE", change_kind="value")
    impacted_c = refs(imp_c.direct_impacts) | refs(imp_c.transitive_impacts)
    r.check("py://app/config.py#get_mode" in impacted_c, "APP_MODE config change impacts get_mode reader", str(sorted(impacted_c))[:200])
    r.check("py://app/services.py#create_item" in impacted_c, "APP_MODE config change reaches create_item (transitive via get_mode)")

    # 4. Resource direction + identity on db effects.
    snap = store.get_snapshot(PID)
    se_nodes = [n for n in snap.nodes if n.node_type == "side_effect"]
    dirs = {(n.properties.get("kind"), n.properties.get("direction")) for n in se_nodes if n.properties.get("direction")}
    r.check(any(k == "database" and d == "write" for k, d in dirs), "db write effect has direction=write", str(sorted(dirs))[:200])
    r.check(any(k == "config" and d == "read" for k, d in dirs), "config read effect has direction=read")
    res_nodes = {n.canonical_ref for n in snap.nodes if n.node_type == "resource"}
    r.check("resource://config:APP_MODE" in res_nodes, "config resource identity resource://config:APP_MODE present")
    r.check("resource://config:DATABASE_URL" in res_nodes, "config resource identity resource://config:DATABASE_URL present")

    # 5. UI event -> API -> route -> handler path discoverable.
    trace = store.trace_path(PathTraceRequest(
        project_id=PID, source_ref="uievent://web/app.js#click",
        target_ref="route://GET /items", min_confidence=0.0, max_depth=8))
    r.check(bool(trace.paths), "UI click event traces to a route", f"paths={len(trace.paths)}")

    # 6. Import-aware call resolution: services.create_item resolves to db.save_item (from-import).
    edge_triples = {(e.edge_type, e.source_node_id, e.target_node_id) for e in snap.edges}
    resolved_call = ("calls", nid("py://app/services.py#create_item"), nid("py://app/db.py#save_item")) in edge_triples
    r.check(resolved_call, "services.create_item -> db.save_item resolved to canonical ref (from-import)")

    # 7. Ambiguous-call diagnostics present in static analysis for an unresolved name.
    static_res = StaticStructuralAnalyzer().analyze(StaticAnalysisRequest(project_id=PID, project_path=str(tmp), full_rebuild=True))
    amb = {d.get("callee") for d in static_res.diagnostics if d.get("code") == "ambiguous_call"}
    # In this clean project all project calls resolve; builtins are filtered -> expect NO false ambiguous.
    r.check("save_item" not in amb and "create_item" not in amb, "resolved project calls are NOT flagged ambiguous", f"ambiguous={sorted(amb)}")

    # 8. All behavioral facts remain inferred / never verified.
    beh = [n for n in snap.nodes if n.domain == "behavioral"]
    r.check(all(n.status != "verified" for n in beh) and bool(beh), "no behavioral fact is marked verified")

    # --- precision / edge checks (expected to surface remediation items) ---
    _CONTAINER_TYPES = {"repository", "directory", "file", "module"}

    # 9. Impact results should not be polluted with structural container nodes (dir/file/module).
    cont = [i.canonical_ref for i in imp.direct_impacts + imp.transitive_impacts
            if i.item_type in _CONTAINER_TYPES]
    r.check(not cont, "impact result excludes structural container nodes (dir/file/module)", f"containers={sorted(cont)[:6]}")

    # 10. os.environ['X'] subscript config read should be modeled like environ.get('X').
    r.check("resource://config:LEGACY_FLAG" in res_nodes, "os.environ['LEGACY_FLAG'] subscript modeled as config resource")

    # 11. self-method call should resolve to the concrete method (not only name-based).
    self_call = ("calls", nid("py://app/models.py#ItemRepo.save"), nid("py://app/models.py#ItemRepo._validate")) in edge_triples
    r.check(self_call, "self._validate() resolves to ItemRepo._validate canonical ref")

    # 12. Impact result item_type should distinguish behavior vs structure (no raw 'module'/'file').
    bad_types = sorted({i.item_type for i in imp_r.direct_impacts if i.item_type in _CONTAINER_TYPES})
    r.check(not bad_types, "route impact direct items are not structural containers", f"types={bad_types}")

    fails = r.emit()
    store.close()
    return fails


if __name__ == "__main__":
    sys.exit(main())
