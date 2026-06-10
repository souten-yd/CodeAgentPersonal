"""PI-7 behavioral graph v2 tests.

Acceptance criteria (implementation plan PI-7):
- fixture paths cover branch/error/retry behavior;
- HTTP request-to-persistence path is queryable;
- UI event-to-render path is queryable for supported fixtures;
- concrete file/table/route targets are recorded where resolvable;
- false certainty tests pass (heuristics never verified; confidence < 1.0).
Plus: static graph identities reused; incremental invalidation; provenance on every fact.
"""

from __future__ import annotations

from pathlib import Path

from agent.project_twin.analyzers.behavioral import (
    BehavioralAnalyzer,
    trace_request_to_persistence,
    trace_ui_to_api,
)
from agent.project_twin.analyzers.default import build_default_registry

ROOT = Path(".")

API_FIXTURE = (
    "from fastapi import APIRouter\n"
    "router = APIRouter()\n"
    "@router.get('/users')\n"
    "def list_users(db):\n"
    "    return repo_fetch(db)\n"
    "def repo_fetch(db):\n"
    "    return db.execute('SELECT id FROM users')\n"
)

RETRY_FIXTURE = (
    "def save(conn, data):\n"
    "    for attempt in range(3):\n"
    "        try:\n"
    "            conn.execute('INSERT INTO orders VALUES (1)')\n"
    "            return True\n"
    "        except Exception:\n"
    "            conn.rollback()\n"
    "    return False\n"
)

UI_FIXTURE = (
    "const btn = document.querySelector('#go');\n"
    "btn.addEventListener('click', () => { fetch('/users').then(r => render(r)); });\n"
)


def _behavioral(files: dict[str, str]):
    sem = build_default_registry().analyze_project(ROOT, files).graph
    beh, diags = BehavioralAnalyzer().analyze_project(files)
    return sem, beh, diags


# --- Control flow: branch / error / retry ------------------------------------

def test_control_flow_and_retry_recovery() -> None:
    _, beh, _ = _behavioral({"svc.py": RETRY_FIXTURE})
    cf = beh.get("cf://py://svc#save")
    assert cf is not None
    assert cf.properties["loops"] >= 1 and cf.properties["has_try"] is True
    # retry + rollback recovery facts present.
    recoveries = {f.label for f in beh.facts(kind="recovery")}
    assert "retry" in recoveries
    assert "rollback" in recoveries


# --- HTTP request-to-persistence path ----------------------------------------

def test_http_request_to_persistence_path_is_queryable() -> None:
    sem, beh, _ = _behavioral({"api.py": API_FIXTURE})
    trace = trace_request_to_persistence(beh, sem, "route://GET /users")
    assert trace["handler"] == "py://api#list_users"
    # The resolved call list_users -> repo_fetch reaches the users table.
    assert "py://api#repo_fetch" in trace["path"]
    assert "table://users" in trace["tables"]


def test_concrete_targets_recorded() -> None:
    _, beh, _ = _behavioral({"api.py": API_FIXTURE})
    db_effects = [f for f in beh.facts(kind="side_effect") if f.properties.get("category") == "database"]
    assert any(f.properties.get("resource") == "users" for f in db_effects)
    routes = {f.label for f in beh.facts(kind="route")}
    assert "GET /users" in routes


def test_file_side_effect_resource_recorded() -> None:
    _, beh, _ = _behavioral({"io.py": "def w():\n    open('/tmp/out.log', 'w')\n"})
    files = [f for f in beh.facts(kind="side_effect") if f.properties.get("category") == "file"]
    assert any(f.properties.get("resource") == "/tmp/out.log" for f in files)


# --- UI event-to-API path ----------------------------------------------------

def test_ui_event_to_api_path_is_queryable() -> None:
    _, beh, _ = _behavioral({"ui.js": UI_FIXTURE})
    events = beh.facts(kind="ui_event")
    assert events, "expected a ui_event fact"
    trace = trace_ui_to_api(beh, events[0].ref)
    assert trace["api_calls"], "ui event should invoke an api call"
    assert "route://GET /users" in trace["routes"]


# --- False certainty: heuristics never verified ------------------------------

def test_all_behavioral_facts_are_inferred_with_confidence_below_one() -> None:
    _, beh, _ = _behavioral({"api.py": API_FIXTURE, "ui.js": UI_FIXTURE})
    for fact in beh.facts():
        assert fact.status == "inferred"
        assert fact.confidence < 1.0
        assert fact.derivation  # provenance present
    for rel in beh.relations():
        assert rel.status == "inferred"
        assert rel.confidence < 1.0


# --- Static identity reuse + incremental invalidation ------------------------

def test_behavior_owner_refs_reuse_static_identities() -> None:
    sem, beh, _ = _behavioral({"api.py": API_FIXTURE})
    # The owner of the route handler is the SAME ref the semantic graph defines.
    assert sem.get("py://api#list_users") is not None
    owners = {f.owner_ref for f in beh.facts() if f.owner_ref.startswith("py://")}
    assert "py://api#list_users" in owners


def test_incremental_invalidation_behavioral() -> None:
    analyzer = BehavioralAnalyzer()
    beh, _ = analyzer.analyze_project({"a.py": "def f():\n    open('/x')\n",
                                       "b.py": "def g():\n    open('/y')\n"})
    assert beh.get("cf://py://a#f") and beh.get("cf://py://b#g")
    analyzer.analyze_project({"b.py": "def g2():\n    open('/z')\n"}, behavioral=beh)
    assert beh.get("cf://py://a#f") is not None      # untouched
    assert beh.get("cf://py://b#g") is None           # invalidated
    assert beh.get("cf://py://b#g2") is not None       # rebuilt


def test_unsupported_js_emits_diagnostic_not_fabrication() -> None:
    _, _, diags = _behavioral({"empty.js": "const x = 1;\n"})
    assert any("no UI events/api calls" in d for d in diags)
