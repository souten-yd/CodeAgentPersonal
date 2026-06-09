"""PDT-13 tests for the Project Twin inspection API."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.project_twin.contracts import TwinDelta, TwinEdge, TwinNode
from agent.project_twin.static_graph import nid
from agent.project_twin.store import SqliteProjectTwinStore
from app.api.project_twin import router as twin_router

NOW = datetime(2026, 6, 10, tzinfo=timezone.utc)


def _node(ref, node_type="function", label=None) -> TwinNode:
    return TwinNode(
        node_id=nid(ref), project_id="p1", domain="structural", node_type=node_type,
        canonical_ref=ref, label=label or ref, source_kind="git", source_ref="m.py",
        derivation="deterministic_static", confidence=0.9, status="declared",
        valid_from=NOW, created_at=NOW, updated_at=NOW,
    )


def _edge(src, tgt, etype="calls") -> TwinEdge:
    return TwinEdge(
        edge_id=nid(f"{etype}|{src}|{tgt}"), project_id="p1", domain="structural",
        source_node_id=nid(src), target_node_id=nid(tgt), edge_type=etype, source_kind="git",
        source_ref="m.py", derivation="deterministic_static", confidence=0.9, status="declared",
        valid_from=NOW, created_at=NOW, updated_at=NOW,
    )


@pytest.fixture()
def client():
    store = SqliteProjectTwinStore(":memory:")
    nodes = [_node(f"py://m.py#f{i}") for i in range(5)] + [_node("py://m.py#caller")]
    edges = [_edge("py://m.py#caller", "py://m.py#f0")]
    store.apply_delta(TwinDelta(project_id="p1", idempotency_key="seed", trigger_type="seed", nodes=nodes, edges=edges))

    app = FastAPI()
    app.state.project_twin_store = store
    app.include_router(twin_router)
    yield TestClient(app)
    store.close()


def test_health_endpoint(client):
    r = client.get("/api/project-twin/health", params={"project_id": "p1"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["node_count"] == 6


def test_query_is_bounded_and_paginated(client):
    r = client.post("/api/project-twin/query", json={"project_id": "p1", "limit": 2})
    assert r.status_code == 200
    body = r.json()
    assert len(body["nodes"]) == 2
    assert body["truncated"] is True and body["cursor"] == "2"


def test_query_limit_is_capped(client):
    # Requesting an over-large limit must be rejected by validation or capped server-side.
    r = client.post("/api/project-twin/query", json={"project_id": "p1", "limit": 999999})
    # pydantic rejects > 1000 at the contract boundary
    assert r.status_code == 422


def test_node_neighbours_lazy_expansion(client):
    r = client.get("/api/project-twin/node", params={"project_id": "p1", "canonical_ref": "py://m.py#caller"})
    assert r.status_code == 200
    body = r.json()
    assert body["node"]["canonical_ref"] == "py://m.py#caller"
    assert any(nb["edge_type"] == "calls" for nb in body["neighbours"])


def test_node_not_found(client):
    r = client.get("/api/project-twin/node", params={"project_id": "p1", "canonical_ref": "py://nope#x"})
    assert r.status_code == 404


def test_impact_and_context_endpoints(client):
    imp = client.post("/api/project-twin/impact", json={"project_id": "p1", "changed_refs": ["py://m.py#f0"], "change_kind": "edit", "min_confidence": 0.0})
    assert imp.status_code == 200
    refs = {i["canonical_ref"] for i in imp.json()["direct_impacts"] + imp.json()["transitive_impacts"]}
    assert "py://m.py#caller" in refs

    ctx = client.post("/api/project-twin/context", json={"project_id": "p1", "objective": "inspect", "phase": "planning", "token_budget": 4000})
    assert ctx.status_code == 200
    assert ctx.json()["phase"] == "planning"


def test_api_exposes_no_mutation_or_execution_route():
    # The router must be read-only: no PUT/DELETE/PATCH and no apply/execute/mutate paths.
    methods_paths = [(m, r.path) for r in twin_router.routes for m in getattr(r, "methods", set())]
    for method, path in methods_paths:
        assert method in {"GET", "POST"}, f"unexpected method {method} on {path}"
        assert not any(tok in path for tok in ("apply", "delete", "execute", "mutate", "run", "command")), path
