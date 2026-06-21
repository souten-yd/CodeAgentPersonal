from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.project_twin.contracts import TwinDelta, TwinEdge, TwinNode
from agent.project_twin.static_graph import nid
from agent.project_twin.store import SqliteProjectTwinStore
from app.api.forge import router


NOW = datetime(2026, 6, 21, tzinfo=timezone.utc)


def _node(ref: str) -> TwinNode:
    return TwinNode(
        node_id=nid(ref), project_id="p1", domain="structural", node_type="function",
        canonical_ref=ref, label=ref, source_kind="git", source_ref="app.py",
        derivation="deterministic_static", confidence=0.9, status="declared",
        valid_from=NOW, created_at=NOW, updated_at=NOW,
    )


def _client(tmp_path):
    store = SqliteProjectTwinStore(":memory:")
    caller, target = "py://app.py#caller", "py://app.py#target"
    store.apply_delta(TwinDelta(
        project_id="p1", idempotency_key="seed", trigger_type="seed",
        nodes=[_node(caller), _node(target)],
        edges=[TwinEdge(
            edge_id=nid(f"calls|{caller}|{target}"), project_id="p1", domain="structural",
            source_node_id=nid(caller), target_node_id=nid(target), edge_type="calls",
            source_kind="git", source_ref="app.py", derivation="deterministic_static",
            confidence=0.9, status="declared", valid_from=NOW, created_at=NOW, updated_at=NOW,
        )],
    ))
    app = FastAPI()
    app.state.atlas_ca_data_root = str(tmp_path)
    app.state.project_twin_store = store
    app.include_router(router)
    return TestClient(app), store


def test_twin_settings_facade_is_reversible_and_strict(tmp_path, monkeypatch):
    client, store = _client(tmp_path)
    monkeypatch.setenv("ATLAS_TWIN_PIPELINE_MODE", "shadow")
    try:
        got = client.get("/api/forge/twin/settings")
        assert got.status_code == 200
        assert got.json()["settings"]["mode"] == "shadow"
        assert got.json()["reversible"] is True
        assert client.post("/api/forge/twin/settings", json={"mode": "off"}).status_code == 200
        assert client.post(
            "/api/forge/twin/settings", json={"mode": "off", "execute": True}
        ).status_code == 422
    finally:
        store.close()


def test_twin_profiles_facade_reuses_control_plane_profiles(tmp_path):
    client, store = _client(tmp_path)
    try:
        body = client.get("/api/forge/twin/profiles").json()
        assert body == {"profiles": [], "count": 0}
    finally:
        store.close()


def test_twin_context_and_impact_facades_are_read_only(tmp_path):
    client, store = _client(tmp_path)
    try:
        context = client.post("/api/forge/twin/inspect/context", json={
            "project_id": "p1", "objective": "inspect", "phase": "planning",
            "token_budget": 4000,
        })
        assert context.status_code == 200
        assert context.json()["read_only"] is True
        assert context.json()["context"]["phase"] == "planning"

        impact = client.post("/api/forge/twin/inspect/impact", json={
            "project_id": "p1", "changed_refs": ["py://app.py#target"],
            "change_kind": "edit", "min_confidence": 0.0,
        })
        assert impact.status_code == 200
        assert impact.json()["read_only"] is True
        refs = {
            item["canonical_ref"]
            for item in impact.json()["impact"]["direct_impacts"]
            + impact.json()["impact"]["transitive_impacts"]
        }
        assert "py://app.py#caller" in refs
    finally:
        store.close()


def test_twin_inspect_rejects_extra_fields_and_exposes_no_apply_route(tmp_path):
    client, store = _client(tmp_path)
    try:
        invalid = client.post("/api/forge/twin/inspect/context", json={
            "project_id": "p1", "objective": "inspect", "phase": "planning",
            "token_budget": 4000, "apply": True,
        })
        assert invalid.status_code == 422
        paths = [route.path for route in router.routes if "/twin/" in route.path]
        assert not any(any(token in path for token in ("apply", "execute", "mutate")) for path in paths)
    finally:
        store.close()
