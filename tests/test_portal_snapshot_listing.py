import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.portal import router as portal_router
from app.portal.paths import PortalPathLayout


def _client(tmp_path: Path) -> TestClient:
    app = FastAPI()
    app.state.atlas_ca_data_root = str(tmp_path)
    app.include_router(portal_router)
    return TestClient(app)


def _write_snapshot(tmp_path: Path, installation_id: str, snapshot_id: str, payload: bytes) -> None:
    layout = PortalPathLayout(tmp_path)
    snap_root = layout.snapshot_root(installation_id, snapshot_id)
    (snap_root / "data").mkdir(parents=True, exist_ok=True)
    (snap_root / "data" / "save.dat").write_bytes(payload)
    (snap_root / "snapshot.json").write_text(
        json.dumps({
            "schema_version": "portal.v1",
            "snapshot_id": snapshot_id,
            "installation_id": installation_id,
            "source": "sess-1",
            "immutable": True,
            "data_hash": "deadbeef",
        }),
        encoding="utf-8",
    )


def test_snapshot_listing_empty_is_available_and_truthful(tmp_path: Path) -> None:
    resp = _client(tmp_path).get("/api/portal/installations/inst-1/snapshots")
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert body["snapshots"] == []


def test_snapshot_listing_returns_saved_snapshots(tmp_path: Path) -> None:
    _write_snapshot(tmp_path, "inst-1", "snap-a", b"x" * 10)
    _write_snapshot(tmp_path, "inst-1", "snap-b", b"y" * 20)
    # An unrelated installation's snapshot must not leak into this list.
    _write_snapshot(tmp_path, "inst-2", "other", b"z" * 5)

    body = _client(tmp_path).get("/api/portal/installations/inst-1/snapshots").json()
    ids = {s["snapshot_id"]: s for s in body["snapshots"]}
    assert set(ids) == {"snap-a", "snap-b"}
    assert ids["snap-a"]["data_bytes"] == 10
    assert ids["snap-b"]["data_bytes"] == 20
    assert ids["snap-a"]["source"] == "sess-1"
