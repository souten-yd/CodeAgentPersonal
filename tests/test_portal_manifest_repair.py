import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.portal import router as portal_router
from app.atlas.capsule.builder import CapsuleBuilder
from app.atlas.capsule.contracts import CapsuleBuildRequest
from app.atlas.play.contracts import LaunchKind, LaunchProfile
from app.atlas.play.environment import build_structured_launch_adapter
from app.atlas.play.sessions import PlayProcessPolicy, PlaySessionRecord, PlaySessionRepository
from app.portal.catalog import PortalCatalogService


def _client(tmp_path: Path) -> TestClient:
    app = FastAPI()
    app.state.atlas_ca_data_root = str(tmp_path)
    app.include_router(portal_router)
    return TestClient(app)


def _import_package(tmp_path: Path) -> tuple[PortalCatalogService, dict]:
    work = tmp_path / "atlas" / "projects" / "demo" / "work"
    work.mkdir(parents=True)
    (work / "app.py").write_text("print('ok')\n", encoding="utf-8")
    adapter = build_structured_launch_adapter(
        work, LaunchProfile(profile_id="py", name="Python", kind=LaunchKind.PYTHON_SCRIPT, entrypoint="app.py")
    )
    PlaySessionRepository(tmp_path).save(
        PlaySessionRecord(
            session_id="play-success", project_id="demo", project_root=str(work), state="stopped",
            launch_profile_id="py", launch_kind=LaunchKind.PYTHON_SCRIPT,
            adapter=adapter.model_dump(mode="json"),
            process_policy=PlayProcessPolicy(uses_process_group=True, cleanup_strategy="test"), exit_code=0,
        )
    )
    built = CapsuleBuilder(tmp_path).build(
        CapsuleBuildRequest(
            project_id="demo", play_session_id="play-success", selected_profile_ids=["py"],
            package_id="demo.package", name="Demo", version="1.0.0",
        )
    )
    svc = PortalCatalogService(tmp_path)
    archive = tmp_path / "demo.portal.zip"
    archive.write_bytes(Path(built["record"]["storage_path"]).read_bytes())
    record = svc.import_archive(archive)["record"]
    return svc, record


def _make_legacy(svc: PortalCatalogService, record: dict) -> None:
    """Simulate a legacy record: delete the manifest sidecar and clear manifest_path."""
    Path(record["manifest_path"]).unlink()
    record_path = (
        svc.paths.package_store_root() / record["package_id"] / record["version"]
        / f"{record['content_hash']}.record.json"
    )
    data = json.loads(record_path.read_text(encoding="utf-8"))
    data["manifest_path"] = ""
    record_path.write_text(json.dumps(data), encoding="utf-8")


def test_repair_recreates_sidecar_shows_profiles_and_does_not_mutate_archive(tmp_path: Path) -> None:
    svc, record = _import_package(tmp_path)
    pid, ver, chash = record["package_id"], record["version"], record["content_hash"]
    zip_path = Path(record["storage_path"])
    zip_before = zip_path.read_bytes()

    _make_legacy(svc, record)
    assert svc.list_packages()["packages"][0]["manifest"] is None  # profiles unavailable

    resp = _client(tmp_path).post(f"/api/portal/packages/{pid}/{ver}/{chash}/repair-manifest")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "repaired"
    assert body["manifest"]["launch_profiles"]

    # Sidecar restored and catalog now exposes launch profiles again.
    assert Path(body["record"]["manifest_path"]).exists()
    assert svc.list_packages()["packages"][0]["manifest"]["launch_profiles"]
    # The package ZIP is never mutated.
    assert zip_path.read_bytes() == zip_before


def test_repair_reports_unrecoverable_when_archive_missing(tmp_path: Path) -> None:
    svc, record = _import_package(tmp_path)
    pid, ver, chash = record["package_id"], record["version"], record["content_hash"]
    _make_legacy(svc, record)
    Path(record["storage_path"]).unlink()  # archive gone -> unrecoverable

    body = _client(tmp_path).post(f"/api/portal/packages/{pid}/{ver}/{chash}/repair-manifest").json()
    assert body["status"] == "unrecoverable"
    assert body["reason"] == "package_archive_missing"


def test_repair_unknown_package_returns_404(tmp_path: Path) -> None:
    resp = _client(tmp_path).post("/api/portal/packages/nope/1.0.0/deadbeef/repair-manifest")
    assert resp.status_code == 404
