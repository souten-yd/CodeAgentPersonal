import zipfile
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.portal import router as portal_router
from app.atlas.capsule.builder import CapsuleBuilder
from app.atlas.capsule.contracts import CapsuleBuildRequest
from app.atlas.play.contracts import LaunchKind, LaunchProfile, TrustState
from app.atlas.play.environment import build_structured_launch_adapter
from app.atlas.play.sessions import PlayProcessPolicy, PlaySessionRecord, PlaySessionRepository
from app.portal.catalog import PortalCatalogService
from app.portal.contracts import PortalRunMode, PortalRunRequest
from app.portal.runtime import PortalRuntimeError, PortalRuntimeService


def _project(tmp_path: Path, project_id: str = "demo") -> Path:
    work = tmp_path / "atlas" / "projects" / project_id / "work"
    work.mkdir(parents=True)
    return work


def _save_success(tmp_path: Path, work: Path, entrypoint: str = "app.py") -> None:
    adapter = build_structured_launch_adapter(
        work,
        LaunchProfile(profile_id="py", name="Python", kind=LaunchKind.PYTHON_SCRIPT, entrypoint=entrypoint),
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


def _build_package(tmp_path: Path) -> dict:
    work = _project(tmp_path)
    (work / "app.py").write_text("import time\nprint('portal data', flush=True)\ntime.sleep(30)\n", encoding="utf-8")
    _save_success(tmp_path, work)
    return CapsuleBuilder(tmp_path).build(
        CapsuleBuildRequest(
            project_id="demo",
            play_session_id="play-success",
            selected_profile_ids=["py"],
            package_id="portal.data.package",
            name="Portal Data Package",
            version="1.0.0",
        )
    )


def _install(tmp_path: Path, installation_id: str = "inst") -> dict:
    package = _build_package(tmp_path)
    record = package["record"]
    installation = PortalRuntimeService(tmp_path).install_package(
        record["package_id"],
        record["version"],
        record["content_hash"],
        installation_id,
    )["installation"]
    return {"package": package, "record": record, "installation": installation}


def _run(tmp_path: Path, *, mode: PortalRunMode = PortalRunMode.CONTINUE_CURRENT_DATA, snapshot_id: str | None = None) -> dict:
    return PortalRuntimeService(tmp_path).run(
        PortalRunRequest(
            installation_id="inst",
            launch_profile_id="py",
            run_mode=mode,
            snapshot_id=snapshot_id,
            trust_state=TrustState.TRUSTED_LOCAL_CAPSULE,
        )
    )


def _client(tmp_path: Path) -> TestClient:
    app = FastAPI()
    app.state.atlas_ca_data_root = str(tmp_path)
    app.include_router(portal_router)
    return TestClient(app)


def test_save_persists_current_data_and_next_run_continues(tmp_path: Path) -> None:
    _install(tmp_path)
    service = PortalRuntimeService(tmp_path)
    first = _run(tmp_path, mode=PortalRunMode.START_EMPTY)
    Path(first["runtime"]["data_root"], "save.db").write_text("saved", encoding="utf-8")

    saved = service.save_and_exit(first["runtime"]["play_session_id"])
    second = _run(tmp_path)

    assert saved["data"]["current_data"]["bytes"] == 5
    assert Path(second["runtime"]["data_root"], "save.db").read_text(encoding="utf-8") == "saved"
    service.discard_and_exit(second["runtime"]["play_session_id"])


def test_discard_rolls_back_session_writes_and_ephemeral_defaults_to_discard(tmp_path: Path) -> None:
    _install(tmp_path)
    current = tmp_path / "portal" / "data" / "inst" / "current"
    current.mkdir(parents=True)
    (current / "save.db").write_text("old", encoding="utf-8")
    service = PortalRuntimeService(tmp_path)
    run = _run(tmp_path)
    Path(run["runtime"]["data_root"], "save.db").write_text("new", encoding="utf-8")

    discarded = service.discard_and_exit(run["runtime"]["play_session_id"])
    ephemeral = _run(tmp_path, mode=PortalRunMode.EPHEMERAL)

    assert discarded["status"] == "discarded"
    assert (current / "save.db").read_text(encoding="utf-8") == "old"
    assert not Path(ephemeral["runtime"]["data_root"], "save.db").exists()
    assert ephemeral["runtime"]["data_decision"] == "ephemeral_default_discard"
    service.discard_and_exit(ephemeral["runtime"]["play_session_id"])


def test_save_as_snapshot_does_not_mutate_current_or_source_snapshot(tmp_path: Path) -> None:
    _install(tmp_path)
    current = tmp_path / "portal" / "data" / "inst" / "current"
    current.mkdir(parents=True)
    (current / "save.db").write_text("current", encoding="utf-8")
    service = PortalRuntimeService(tmp_path)
    base = _run(tmp_path)
    Path(base["runtime"]["data_root"], "save.db").write_text("base", encoding="utf-8")
    service.save_snapshot_and_exit(base["runtime"]["play_session_id"], "base")

    from_snapshot = _run(tmp_path, mode=PortalRunMode.START_FROM_SNAPSHOT, snapshot_id="base")
    Path(from_snapshot["runtime"]["data_root"], "save.db").write_text("changed", encoding="utf-8")
    service.save_snapshot_and_exit(from_snapshot["runtime"]["play_session_id"], "derived")

    assert (current / "save.db").read_text(encoding="utf-8") == "current"
    assert (tmp_path / "portal" / "data" / "inst" / "snapshots" / "base" / "data" / "save.db").read_text(encoding="utf-8") == "base"
    assert (tmp_path / "portal" / "data" / "inst" / "snapshots" / "derived" / "data" / "save.db").read_text(encoding="utf-8") == "changed"


def test_atomic_commit_failure_preserves_previous_current_data(tmp_path: Path, monkeypatch) -> None:
    _install(tmp_path)
    current = tmp_path / "portal" / "data" / "inst" / "current"
    current.mkdir(parents=True)
    (current / "save.db").write_text("old", encoding="utf-8")
    service = PortalRuntimeService(tmp_path)
    run = _run(tmp_path)
    Path(run["runtime"]["data_root"], "save.db").write_text("new", encoding="utf-8")

    def fail_copy(_source, _target):
        raise RuntimeError("copy failed")

    monkeypatch.setattr(service.data, "_copy_contents", fail_copy)
    try:
        service.save_and_exit(run["runtime"]["play_session_id"])
    except PortalRuntimeError as exc:
        assert exc.code == "current_data_commit_failed"
    else:
        raise AssertionError("commit failure must fail closed")

    assert (current / "save.db").read_text(encoding="utf-8") == "old"
    service.discard_and_exit(run["runtime"]["play_session_id"])


def test_package_export_excludes_data_while_data_backup_is_separate(tmp_path: Path) -> None:
    installed = _install(tmp_path)
    current = tmp_path / "portal" / "data" / "inst" / "current"
    current.mkdir(parents=True)
    (current / "save.db").write_text("data", encoding="utf-8")

    package_path = PortalCatalogService(tmp_path).export_package_path(
        installed["record"]["package_id"],
        installed["record"]["version"],
        installed["record"]["content_hash"],
    )
    backup_path = PortalRuntimeService(tmp_path).data_backup_path("inst")

    with zipfile.ZipFile(package_path) as zf:
        assert not any(name.startswith(("current/", "snapshots/", "data/")) for name in zf.namelist())
    with zipfile.ZipFile(backup_path) as zf:
        assert "metadata/portal_data_backup.json" in zf.namelist()
        assert "current/save.db" in zf.namelist()


def test_data_delete_requires_confirmation_and_does_not_uninstall_package(tmp_path: Path) -> None:
    installed = _install(tmp_path)
    current = tmp_path / "portal" / "data" / "inst" / "current"
    current.mkdir(parents=True)
    (current / "save.db").write_text("data", encoding="utf-8")
    service = PortalRuntimeService(tmp_path)

    try:
        service.delete_data("inst", confirm_delete_data=False)
    except PortalRuntimeError as exc:
        assert exc.code == "data_delete_confirmation_required"
    else:
        raise AssertionError("delete data must require confirmation")
    deleted = service.delete_data("inst", confirm_delete_data=True)
    package_path = PortalCatalogService(tmp_path).export_package_path(
        installed["record"]["package_id"],
        installed["record"]["version"],
        installed["record"]["content_hash"],
    )

    assert deleted["status"] == "data_deleted"
    assert package_path.exists()


def test_portal_data_api_and_managed_environment_contract(tmp_path: Path) -> None:
    installed = _install(tmp_path)
    client = _client(tmp_path)
    run = client.post(
        "/api/portal/run",
        json={
            "installation_id": "inst",
            "launch_profile_id": "py",
            "run_mode": "start_empty",
            "trust_state": "trusted_local_capsule",
        },
    )
    play_session_id = run.json()["runtime"]["play_session_id"]
    Path(run.json()["runtime"]["data_root"], "api.txt").write_text("api", encoding="utf-8")

    saved = client.post(f"/api/portal/runs/{play_session_id}/data/save")
    summary = client.get("/api/portal/installations/inst/data")
    backup = client.get("/api/portal/installations/inst/data/backup")
    delete_missing_confirm = client.request("DELETE", "/api/portal/installations/inst/data", json={"confirm_delete_data": False})

    adapter_env = run.json()["play_session"]["adapter"]["environment"]
    assert run.status_code == 200
    assert saved.status_code == 200
    assert summary.json()["current_data"]["bytes"] == 3
    assert backup.status_code == 200
    assert delete_missing_confirm.status_code == 400
    assert adapter_env["PORTAL_DATA_DIR"] == run.json()["runtime"]["data_root"]
    assert installed["installation"]["package_immutable"] is True
