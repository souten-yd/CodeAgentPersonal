"""Comprehensive Digital Twin / Deep Behavioral Graph evaluation.

Builds a larger multi-package virtual project (packages, classes, relative + alias + self imports,
config via .get/.getenv/subscript, db/net/process resources, FastAPI routes, JS event->API paths,
tests across files) and runs a wide scenario matrix to assess — comprehensively — whether the twin can
be USED for change impact and whether it can DETECT the right relationships across multiple change
kinds and multiple change locations (including multi-ref/simultaneous changes and historical risk).

Run: python scripts/twin_comprehensive_eval.py   (exit code = number of failing checks)
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from agent.project_twin.behavioral_graph import BehavioralAnalyzer
from agent.project_twin.contracts import (
    ImpactRequest,
    PathTraceRequest,
    StaticAnalysisRequest,
    TwinDelta,
    TwinEdge,
    TwinNode,
)
from agent.project_twin.projection import StaticProjectionService
from agent.project_twin.static_graph import StaticStructuralAnalyzer, nid
from agent.project_twin.store import SqliteProjectTwinStore

PID = "virtual"

VFILES = {
    "core/__init__.py": "",
    "core/config.py": (
        "import os\n\n"
        "def get_mode():\n    return os.environ.get('APP_MODE')\n\n"
        "def get_db_url():\n    return os.getenv('DATABASE_URL')\n\n"
        "def debug_flag():\n    return os.environ['DEBUG']\n"
    ),
    "core/db.py": (
        "import sqlite3\n\n"
        "def connect():\n    return sqlite3.connect('app.db')\n\n"
        "def save(conn, item):\n    conn.execute('INSERT INTO items VALUES (?)', (item,))\n    conn.commit()\n\n"
        "def load(conn):\n    cur = conn.cursor()\n    return cur.fetchall()\n"
    ),
    "core/net.py": (
        "import requests\n\n"
        "def fetch(url):\n    return requests.get(url)\n"
    ),
    "core/util.py": (
        "def slugify(text):\n    return str(text).lower().replace(' ', '-')\n"
    ),
    "services/__init__.py": "",
    "services/items.py": (
        "from core.db import save, load, connect\n"
        "from core.config import get_mode\n"
        "from core.util import slugify\n\n"
        "def create_item(item):\n"
        "    slug = slugify(item)\n"
        "    mode = get_mode()\n"
        "    conn = connect()\n"
        "    save(conn, slug)\n"
        "    return mode\n\n"
        "def list_items():\n"
        "    conn = connect()\n"
        "    return load(conn)\n"
    ),
    "services/jobs.py": (
        "from . import items\n\n"
        "def run_job(name):\n    return items.create_item(name)\n"
    ),
    "api/__init__.py": "",
    "api/routes.py": (
        "from fastapi import APIRouter\n"
        "from services.items import create_item, list_items\n\n"
        "router = APIRouter()\n\n"
        "@router.post('/items')\n"
        "def create_handler(item: str):\n    return create_item(item)\n\n"
        "@router.get('/items')\n"
        "def list_handler():\n    return list_items()\n"
    ),
    "models/repo.py": (
        "class Repo:\n"
        "    def save(self, item):\n        self._validate(item)\n        return item\n\n"
        "    def _validate(self, item):\n        return bool(item)\n"
    ),
    "web/app.js": (
        "addBtn.addEventListener('click', () => { fetch('/items', { method: 'POST' }); });\n"
        "listBtn.addEventListener('click', () => { fetch('/items'); });\n"
    ),
    "tests/test_items.py": (
        "from services.items import create_item\n\n"
        "def test_create_item():\n    assert create_item('Hello World') is not None\n"
    ),
    "tests/test_routes.py": (
        "from api.routes import list_handler\n\n"
        "def test_list_handler():\n    assert list_handler() is not None\n"
    ),
}


def build(root: Path) -> None:
    for rel, content in VFILES.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")


def build_twin(root: Path) -> SqliteProjectTwinStore:
    store = SqliteProjectTwinStore(":memory:")
    StaticProjectionService(store).refresh(project_id=PID, project_path=str(root), full_rebuild=True)
    delta = BehavioralAnalyzer().analyze(StaticAnalysisRequest(project_id=PID, project_path=str(root), full_rebuild=True)).delta
    store.apply_delta(delta)
    return store


def _incident_delta(target_ref: str, oid: str) -> TwinDelta:
    now = datetime.now(timezone.utc)
    common = dict(project_id=PID, source_kind="runtime", source_ref=oid, derivation="runtime_observation",
                  status="observed", valid_from=now, created_at=now, updated_at=now)
    inc = f"incident://{oid}"
    node = TwinNode(node_id=nid(inc), domain="runtime", node_type="incident", canonical_ref=inc,
                    label="failed", confidence=0.9, **common)
    edge = TwinEdge(edge_id=nid(f"affects|{inc}|{target_ref}"), domain="runtime", source_node_id=nid(inc),
                    target_node_id=nid(target_ref), edge_type="affects", confidence=0.85, **common)
    return TwinDelta(project_id=PID, idempotency_key=f"inc-{oid}", trigger_type="runtime_observation.recorded", nodes=[node], edges=[edge])


class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[bool, str, str]] = []

    def check(self, ok: bool, name: str, detail: str = "") -> None:
        self.rows.append((bool(ok), name, detail))

    def emit(self) -> int:
        groups: dict[str, list] = {}
        for ok, name, detail in self.rows:
            groups.setdefault(name.split(":", 1)[0], []).append((ok, name, detail))
        fails = 0
        print("\n=== Comprehensive Digital Twin / Behavioral Graph evaluation ===\n")
        for group, rows in groups.items():
            print(f"# {group}")
            for ok, name, detail in rows:
                if not ok:
                    fails += 1
                line = f"  [{'PASS' if ok else 'FAIL'}] {name}"
                if detail:
                    line += f"  -- {detail}"
                print(line)
            print()
        print(f"{len(self.rows) - fails}/{len(self.rows)} checks appropriate; {fails} failing.\n")
        return fails


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="twin_comp_"))
    try:
        return _run(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _run(tmp: Path) -> int:
    build(tmp)
    store = build_twin(tmp)
    snap = store.get_snapshot(PID)
    triples = {(e.edge_type, e.source_node_id, e.target_node_id) for e in snap.edges}
    r = Report()

    def impact(*refs, **kw):
        kw.setdefault("change_kind", "body")
        kw.setdefault("min_confidence", 0.0)
        return store.assess_impact(ImpactRequest(project_id=PID, changed_refs=list(refs), **kw))

    def imp_refs(res):
        return {i.canonical_ref for i in res.direct_impacts + res.transitive_impacts}

    def tests_of(res):
        return {t.canonical_ref for t in res.recommended_tests}

    # --- Impact: single change, multiple locations -------------------------------
    util = impact("py://core/util.py#slugify")
    util_imp = imp_refs(util)
    r.check("py://services/items.py#create_item" in util_imp, "impact: shared util change reaches services.create_item", str(sorted(util_imp))[:160])
    r.check(any("create_handler" in x or "route://POST /items" in x for x in util_imp), "impact: shared util change reaches POST /items route/handler")
    r.check(any(t.endswith("test_create_item") for t in tests_of(util)), "impact: shared util change recommends test_create_item")

    db = impact("py://core/db.py#save")
    db_imp = imp_refs(db)
    r.check("py://services/items.py#create_item" in db_imp, "impact: db.save change reaches services.create_item")
    r.check(any("create_handler" in x or "route://POST /items" in x for x in db_imp), "impact: db.save change reaches POST /items")

    # --- Impact: route change -> handler/UI/test ---------------------------------
    route = impact("route://GET /items", change_kind="signature")
    route_direct = {i.canonical_ref for i in route.direct_impacts}
    route_imp = imp_refs(route)
    r.check("py://api/routes.py#list_handler" in route_direct, "impact: GET /items surfaces handler list_handler", str(sorted(route_direct))[:160])
    r.check(any(x.startswith("uievent://") for x in route_imp), "impact: GET /items surfaces UI caller event")
    r.check(any(t.endswith("test_list_handler") for t in tests_of(route)), "impact: GET /items recommends test_list_handler")

    # --- Impact: config (3 detection forms) --------------------------------------
    cfg = impact("resource://config:APP_MODE", change_kind="value")
    cfg_imp = imp_refs(cfg)
    r.check("py://core/config.py#get_mode" in cfg_imp, "impact: APP_MODE change reaches get_mode reader")
    r.check("py://services/items.py#create_item" in cfg_imp, "impact: APP_MODE change reaches create_item (transitive)")
    res_refs = {n.canonical_ref for n in snap.nodes if n.node_type == "resource"}
    r.check("resource://config:APP_MODE" in res_refs, "config: .get() form modeled (APP_MODE)")
    r.check("resource://config:DATABASE_URL" in res_refs, "config: getenv() form modeled (DATABASE_URL)")
    r.check("resource://config:DEBUG" in res_refs, "config: subscript form modeled (DEBUG)")

    # --- Impact: multiple simultaneous changes -----------------------------------
    multi = impact("py://core/util.py#slugify", "py://core/db.py#save")
    multi_imp = imp_refs(multi)
    r.check(util_imp <= multi_imp and db_imp <= multi_imp, "impact: multi-ref change unions both impacted sets")

    # --- Resource direction + identity -------------------------------------------
    se = [n for n in snap.nodes if n.node_type == "side_effect"]
    dirs = {(n.properties.get("kind"), n.properties.get("direction")) for n in se if n.properties.get("direction")}
    r.check(("database", "write") in dirs, "resource: db write direction", str(sorted(dirs))[:160])
    r.check(("database", "read") in dirs, "resource: db read direction")
    r.check(("config", "read") in dirs, "resource: config read direction")
    r.check(any(k == "network" for k, _ in dirs), "resource: network effect detected")

    # --- Call resolution variety -------------------------------------------------
    r.check(("calls", nid("py://services/items.py#create_item"), nid("py://core/db.py#save")) in triples,
            "calls: from-import resolved (create_item -> db.save)")
    r.check(("calls", nid("py://services/jobs.py#run_job"), nid("py://services/items.py#create_item")) in triples,
            "calls: relative module import resolved (jobs.run_job -> items.create_item)")
    r.check(("calls", nid("py://models/repo.py#Repo.save"), nid("py://models/repo.py#Repo._validate")) in triples,
            "calls: self-method resolved (Repo.save -> Repo._validate)")

    # --- UI -> API -> route path discoverable ------------------------------------
    trace = store.trace_path(PathTraceRequest(project_id=PID, source_ref="uievent://web/app.js#click",
                                              target_ref="route://GET /items", min_confidence=0.0, max_depth=8))
    r.check(bool(trace.paths), "path: UI click event traces to GET /items route", f"paths={len(trace.paths)}")

    # --- Historical risk memory + gating -----------------------------------------
    store.apply_delta(_incident_delta("py://core/db.py#save", "o1"))
    hist_on = impact("py://core/db.py#save", include_historical_risks=True)
    hist_off = impact("py://core/db.py#save", include_historical_risks=False)
    r.check(any(i.canonical_ref == "incident://o1" for i in hist_on.past_incidents), "history: failed-obs incident surfaces in impact when requested")
    r.check(hist_off.past_incidents == [], "history: incident excluded when not requested")

    # --- Uncertainty + inferred invariant ----------------------------------------
    # Import-resolved cross-file impacts are high-confidence (0.9) so they are NOT over-flagged; but
    # impacts reached through heuristic behavioral edges (config/resource, ~0.65) ARE flagged with an
    # honest path_confidence. The structural invariant (every uncertainty entry carries path_confidence)
    # must always hold.
    all_unc = util.uncertainty + db.uncertainty + cfg.uncertainty + route.uncertainty
    r.check(all("path_confidence" in u for u in all_unc), "uncertainty: every entry carries path_confidence")
    r.check(bool(cfg.uncertainty) and any(float(u["path_confidence"]) < 0.7 for u in cfg.uncertainty),
            "uncertainty: heuristic config-impact path is flagged uncertain (not false certainty)")
    beh = [n for n in snap.nodes if n.domain == "behavioral"]
    r.check(bool(beh) and all(n.status != "verified" for n in beh), "invariant: no behavioral fact is verified")

    fails = r.emit()
    store.close()
    return fails


if __name__ == "__main__":
    sys.exit(main())
