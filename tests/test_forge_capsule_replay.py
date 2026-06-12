"""PFG-29 — Capsule Forge metadata and replay.

Forge metadata is a sidecar (the package ZIP and content_hash are never touched), and
replay records a Portal-style run outcome into the model profile while verifying the ZIP
is byte-for-byte unchanged (no source mutation).
"""
from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.forge import router as forge_router
from app.portal.paths import PortalPathLayout


def _client(tmp_path):
    app = FastAPI()
    app.state.atlas_ca_data_root = str(tmp_path)
    app.include_router(forge_router)
    return TestClient(app)


def _make_package(tmp_path: Path, package_id="demo", version="1.0.0") -> tuple[str, bytes]:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("metadata/manifest.json", '{"package_id":"demo"}')
        zf.writestr("application/index.html", "<html></html>")
    zip_bytes = buf.getvalue()
    content_hash = hashlib.sha256(zip_bytes).hexdigest()
    root = PortalPathLayout(tmp_path).package_store_root() / package_id / version
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{content_hash}.zip").write_bytes(zip_bytes)
    return content_hash, zip_bytes


def test_forge_meta_is_sidecar_and_zip_unchanged(tmp_path):
    c = _client(tmp_path)
    content_hash, zip_bytes = _make_package(tmp_path)
    resp = c.post("/api/forge/capsule/forge-meta", json={
        "package_id": "demo", "version": "1.0.0", "content_hash": content_hash,
        "provider_id": "local", "model_id": "mistral", "route_id": "greenfield_skeleton",
        "stage": "planning", "dimension": "greenfield",
    })
    assert resp.status_code == 200
    assert resp.json()["model_id"] == "mistral"
    # Sidecar exists; ZIP bytes + hash unchanged.
    root = PortalPathLayout(tmp_path).package_store_root() / "demo" / "1.0.0"
    assert (root / f"{content_hash}.forge.json").exists()
    after = (root / f"{content_hash}.zip").read_bytes()
    assert after == zip_bytes
    assert hashlib.sha256(after).hexdigest() == content_hash
    # Readable back.
    got = c.get("/api/forge/capsule/forge-meta",
                params={"package_id": "demo", "version": "1.0.0", "content_hash": content_hash}).json()
    assert got["available"] is True and got["forge_meta"]["model_id"] == "mistral"


def test_forge_meta_unknown_package_404(tmp_path):
    c = _client(tmp_path)
    resp = c.post("/api/forge/capsule/forge-meta", json={
        "package_id": "nope", "version": "1.0.0", "content_hash": "deadbeef", "model_id": "x",
    })
    assert resp.status_code == 404


def test_replay_updates_profile_and_verifies_immutability(tmp_path):
    c = _client(tmp_path)
    content_hash, zip_bytes = _make_package(tmp_path)
    c.post("/api/forge/capsule/forge-meta", json={
        "package_id": "demo", "version": "1.0.0", "content_hash": content_hash,
        "provider_id": "local", "model_id": "mistral", "dimension": "greenfield",
    })
    # A successful replay records strong runtime evidence + verifies the package is immutable.
    resp = c.post("/api/forge/capsule/replay", json={
        "package_id": "demo", "version": "1.0.0", "content_hash": content_hash,
        "runtime_passed": True,
    })
    assert resp.status_code == 200
    ev = resp.json()
    assert ev["evidence_strength"] == "strong_runtime"
    assert ev["profile_updated"] is True
    assert ev["package_immutable_verified"] is True
    # The model profile was updated via the replay.
    profiles = c.get("/api/forge/profiles").json()["profiles"]
    assert profiles and profiles[0]["model_id"] == "mistral"
    assert profiles[0]["dimension_scores"]["greenfield"] == 1.0
    # ZIP still byte-for-byte unchanged after replay (no source mutation).
    root = PortalPathLayout(tmp_path).package_store_root() / "demo" / "1.0.0"
    assert (root / f"{content_hash}.zip").read_bytes() == zip_bytes


def test_replay_without_meta_is_rejected(tmp_path):
    c = _client(tmp_path)
    content_hash, _ = _make_package(tmp_path)
    # No forge-meta attached -> cannot attribute the run to a model.
    resp = c.post("/api/forge/capsule/replay", json={
        "package_id": "demo", "version": "1.0.0", "content_hash": content_hash,
        "runtime_passed": True,
    })
    assert resp.status_code == 400
