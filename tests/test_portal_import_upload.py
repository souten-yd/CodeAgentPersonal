from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.atlas.capsule.builder import CapsuleBuilder
from app.atlas.capsule.contracts import CapsuleBuildRequest
from app.atlas.play.contracts import LaunchKind, LaunchProfile
from app.atlas.play.environment import build_structured_launch_adapter
from app.atlas.play.sessions import PlayProcessPolicy, PlaySessionRecord, PlaySessionRepository
from app.api.portal import router as portal_router


def _client(tmp_path: Path) -> TestClient:
    app = FastAPI()
    app.state.atlas_ca_data_root = str(tmp_path)
    app.include_router(portal_router)
    return TestClient(app)


def _built_archive_bytes(tmp_path: Path) -> bytes:
    work = tmp_path / "atlas" / "projects" / "demo" / "work"
    work.mkdir(parents=True)
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
    built = CapsuleBuilder(tmp_path).build(
        CapsuleBuildRequest(
            project_id="demo", play_session_id="play-success", selected_profile_ids=["py"],
            package_id="demo.package", name="Demo", version="1.0.0",
        )
    )
    return Path(built["record"]["storage_path"]).read_bytes()


def _quarantine_files(tmp_path: Path) -> list[Path]:
    qroot = tmp_path / "portal" / "quarantine"
    return [p for p in qroot.rglob("*") if p.is_file()] if qroot.exists() else []


def test_upload_import_classifies_untrusted_and_appears_in_catalog(tmp_path: Path) -> None:
    data = _built_archive_bytes(tmp_path)
    client = _client(tmp_path)

    resp = client.post(
        "/api/portal/import/upload",
        files={"file": ("demo.portal.zip", data, "application/zip")},
    )
    assert resp.status_code == 200
    assert resp.json()["record"]["trust_state"] == "untrusted_imported_package"

    catalog = client.get("/api/portal/catalog").json()
    assert any(p["package_id"] == "demo.package" for p in catalog["packages"])
    # Quarantine staging is cleaned up after import.
    assert _quarantine_files(tmp_path) == []


def test_upload_rejects_non_archive_extension(tmp_path: Path) -> None:
    resp = _client(tmp_path).post(
        "/api/portal/import/upload",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "unsupported_archive_extension"


def test_upload_rejects_empty_file(tmp_path: Path) -> None:
    resp = _client(tmp_path).post(
        "/api/portal/import/upload",
        files={"file": ("demo.portal.zip", b"", "application/zip")},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "empty_upload"


def test_upload_unsafe_archive_fails_closed_and_is_not_cataloged(tmp_path: Path) -> None:
    client = _client(tmp_path)
    resp = client.post(
        "/api/portal/import/upload",
        files={"file": ("bad.zip", b"not a real zip", "application/zip")},
    )
    assert resp.status_code == 400  # fails closed on an invalid/non-capsule archive
    catalog = client.get("/api/portal/catalog").json()
    assert catalog["packages"] == []
    # No quarantine residue left behind on failure.
    assert _quarantine_files(tmp_path) == []
