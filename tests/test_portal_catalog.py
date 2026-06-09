import json
import zipfile
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.portal import router as portal_router
from app.atlas.capsule.builder import CapsuleBuilder
from app.atlas.capsule.contracts import CapsuleBuildRequest
from app.atlas.play.contracts import LaunchKind, LaunchProfile
from app.atlas.play.environment import build_structured_launch_adapter
from app.atlas.play.sessions import PlayProcessPolicy, PlaySessionRecord, PlaySessionRepository
from app.portal.catalog import PortalCatalogError, PortalCatalogService


def _project(tmp_path: Path, project_id: str = "demo") -> Path:
    work = tmp_path / "atlas" / "projects" / project_id / "work"
    work.mkdir(parents=True)
    return work


def _success_session(tmp_path: Path, work: Path) -> None:
    (work / "app.py").write_text("print('ok')\n", encoding="utf-8")
    adapter = build_structured_launch_adapter(
        work,
        LaunchProfile(profile_id="py", name="Python", kind=LaunchKind.PYTHON_SCRIPT, entrypoint="app.py"),
    )
    PlaySessionRepository(tmp_path).save(
        PlaySessionRecord(
            session_id="play-success",
            project_id="demo",
            project_root=str(work),
            state="stopped",
            launch_profile_id="py",
            launch_kind=LaunchKind.PYTHON_SCRIPT,
            adapter=adapter.model_dump(mode="json"),
            process_policy=PlayProcessPolicy(uses_process_group=True, cleanup_strategy="test"),
            exit_code=0,
        )
    )


def _package(tmp_path: Path) -> dict:
    work = _project(tmp_path)
    _success_session(tmp_path, work)
    return CapsuleBuilder(tmp_path).build(
        CapsuleBuildRequest(
            project_id="demo",
            play_session_id="play-success",
            selected_profile_ids=["py"],
            package_id="demo.package",
            name="Demo",
            version="1.0.0",
        )
    )


def _client(tmp_path: Path) -> TestClient:
    app = FastAPI()
    app.state.atlas_ca_data_root = str(tmp_path)
    app.include_router(portal_router)
    return TestClient(app)


def _bad_zip(path: Path, entries: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)


def test_catalog_lists_capsule_builder_records_and_exports_package_only(tmp_path: Path) -> None:
    built = _package(tmp_path)
    service = PortalCatalogService(tmp_path)
    catalog = service.list_packages()
    export_path = service.export_package_path("demo.package", "1.0.0", built["record"]["content_hash"])

    assert catalog["packages"][0]["package_id"] == "demo.package"
    assert export_path == Path(built["record"]["storage_path"])
    with zipfile.ZipFile(export_path) as zf:
        assert not any(name.startswith("data/") for name in zf.namelist())


def test_import_preflight_rejects_traversal_absolute_drive_and_duplicate_entries(tmp_path: Path) -> None:
    service = PortalCatalogService(tmp_path)
    for name in ["../x", "/abs", "C:/x", "a\\..\\x"]:
        archive = tmp_path / f"bad-{name.replace('/', '_').replace(':', '')}.zip"
        _bad_zip(archive, {name: b"x"})
        try:
            service.preflight_archive(archive)
        except PortalCatalogError as exc:
            assert exc.code == "archive_entry_unsafe"
        else:
            raise AssertionError(name)

    duplicate = tmp_path / "dup.zip"
    with zipfile.ZipFile(duplicate, "w") as zf:
        zf.writestr("application/a.txt", b"1")
        zf.writestr("application/A.txt", b"2")
    try:
        service.preflight_archive(duplicate)
    except PortalCatalogError as exc:
        assert exc.code == "duplicate_archive_entry"
    else:
        raise AssertionError("duplicate must fail")


def test_import_rejects_invalid_manifest_and_checksum_mismatch(tmp_path: Path) -> None:
    service = PortalCatalogService(tmp_path)
    invalid = tmp_path / "invalid.zip"
    _bad_zip(invalid, {"metadata/manifest.json": b"{}", "metadata/checksums.json": b"{}", "application/app.py": b"x"})
    mismatch = tmp_path / "mismatch.zip"
    manifest = {
        "schema_version": "atlas.capsule.v1",
        "package_id": "pkg",
        "name": "Pkg",
        "version": "1",
        "launch_profiles": [{"schema_version": "atlas.play.v1", "profile_id": "py", "name": "Py", "kind": "python_script", "entrypoint": "app.py"}],
        "default_profile_id": "py",
    }
    _bad_zip(
        mismatch,
        {
            "metadata/manifest.json": json.dumps(manifest).encode("utf-8"),
            "metadata/checksums.json": json.dumps({"files": {"app.py": "bad"}}).encode("utf-8"),
            "application/app.py": b"x",
        },
    )

    for archive, code in [(invalid, "manifest_invalid"), (mismatch, "checksum_mismatch")]:
        try:
            service.preflight_archive(archive)
        except PortalCatalogError as exc:
            assert exc.code == code
        else:
            raise AssertionError(code)


def test_import_classifies_untrusted_and_detects_version_conflict(tmp_path: Path) -> None:
    built = _package(tmp_path)
    archive = Path(built["record"]["storage_path"])
    service = PortalCatalogService(tmp_path)

    imported = service.import_archive(archive)
    assert imported["record"]["trust_state"] == "untrusted_imported_package"

    tampered = tmp_path / "tampered.zip"
    tampered.write_bytes(archive.read_bytes() + b"x")
    try:
        service.import_archive(tampered)
    except PortalCatalogError as exc:
        assert exc.code in {"manifest_invalid", "package_version_conflict"}
    else:
        raise AssertionError("conflict must fail")


def test_uninstall_does_not_delete_installation_data_and_fork_is_immutable(tmp_path: Path) -> None:
    built = _package(tmp_path)
    service = PortalCatalogService(tmp_path)
    data = tmp_path / "portal" / "data" / "install-1" / "current"
    data.mkdir(parents=True)
    (data / "save.db").write_text("save", encoding="utf-8")
    record = built["record"]
    forked = service.fork_to_atlas(record["package_id"], record["version"], record["content_hash"], "forked")
    uninstalled = service.uninstall_package(record["package_id"], record["version"], record["content_hash"])

    assert Path(forked["project_work_root"], "app.py").exists()
    assert uninstalled["data_deleted"] is False
    assert (data / "save.db").exists()
    try:
        service.fork_to_atlas(record["package_id"], record["version"], record["content_hash"], "forked")
    except PortalCatalogError as exc:
        assert exc.code == "package_not_found"
    else:
        raise AssertionError("uninstalled package must not fork")


def test_portal_catalog_api_import_export_and_fork(tmp_path: Path) -> None:
    built = _package(tmp_path)
    client = _client(tmp_path)
    archive = built["record"]["storage_path"]

    catalog = client.get("/api/portal/catalog")
    preflight = client.post("/api/portal/import/preflight", json={"archive_path": archive})
    exported = client.get(f"/api/portal/packages/demo.package/1.0.0/{built['record']['content_hash']}/export")
    forked = client.post(
        "/api/portal/fork-to-atlas",
        json={"package_id": "demo.package", "version": "1.0.0", "content_hash": built["record"]["content_hash"], "new_project_id": "api-fork"},
    )

    assert catalog.status_code == 200
    assert preflight.status_code == 200
    assert exported.status_code == 200
    assert forked.status_code == 200
    assert forked.json()["status"] == "forked"
