import stat
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


ROOT = Path(__file__).resolve().parents[1]


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


def _build_package(tmp_path: Path, *, profiles: list[LaunchProfile] | None = None, selected: list[str] | None = None) -> dict:
    work = _project(tmp_path)
    (work / "app.py").write_text("import time\nprint('portal', flush=True)\ntime.sleep(30)\n", encoding="utf-8")
    (work / "api.py").write_text(
        "import os, socket, time\nsock=socket.socket(); sock.bind(('127.0.0.1', int(os.environ['ATLAS_PLAY_PORT']))); sock.listen(1); print('ready', flush=True); time.sleep(30)\n",
        encoding="utf-8",
    )
    _save_success(tmp_path, work)
    return CapsuleBuilder(tmp_path).build(
        CapsuleBuildRequest(
            project_id="demo",
            play_session_id="play-success",
            selected_profile_ids=selected or ["py"],
            package_id="portal.package",
            name="Portal Package",
            version="1.0.0",
            launch_profiles=profiles or [],
            default_profile_id=(selected or ["py"])[-1],
        )
    )


def _client(tmp_path: Path) -> TestClient:
    app = FastAPI()
    app.state.atlas_ca_data_root = str(tmp_path)
    app.include_router(portal_router)
    return TestClient(app)


def _install(tmp_path: Path, package: dict, installation_id: str = "inst") -> dict:
    record = package["record"]
    return PortalRuntimeService(tmp_path).install_package(
        record["package_id"],
        record["version"],
        record["content_hash"],
        installation_id,
    )


def test_portal_run_revalidates_hash_stages_readonly_and_uses_play_runtime(tmp_path: Path) -> None:
    package = _build_package(tmp_path)
    installation = _install(tmp_path, package)["installation"]
    service = PortalRuntimeService(tmp_path)

    result = service.run(
        PortalRunRequest(
            installation_id=installation["installation_id"],
            launch_profile_id="py",
            run_mode=PortalRunMode.EPHEMERAL,
            trust_state=TrustState.TRUSTED_LOCAL_CAPSULE,
        )
    )
    app_file = Path(result["runtime"]["application_root"]) / "app.py"
    readonly = not (app_file.stat().st_mode & stat.S_IWRITE)
    stopped = service.stop(result["runtime"]["play_session_id"])
    purged = service.purge(result["runtime"]["play_session_id"])

    assert result["play_session"]["project_id"] == installation["installation_id"]
    assert readonly
    assert stopped["status"] == "stopped"
    assert purged["status"] == "purged"
    assert not Path(result["runtime"]["application_root"]).exists()


def test_portal_run_rejects_tampered_stored_package(tmp_path: Path) -> None:
    package = _build_package(tmp_path)
    installation = _install(tmp_path, package)["installation"]
    Path(installation["package_path"]).write_bytes(Path(installation["package_path"]).read_bytes() + b"tamper")

    try:
        PortalRuntimeService(tmp_path).run(
            PortalRunRequest(
                installation_id="inst",
                launch_profile_id="py",
                trust_state=TrustState.TRUSTED_LOCAL_CAPSULE,
            )
        )
    except PortalRuntimeError as exc:
        assert exc.code == "package_hash_mismatch"
    else:
        raise AssertionError("tampered package must fail")


def test_untrusted_imported_package_is_blocked_without_override(tmp_path: Path) -> None:
    package = _build_package(tmp_path)
    archive = package["record"]["storage_path"]
    imported = PortalCatalogService(tmp_path).import_archive(archive)
    installation = PortalRuntimeService(tmp_path).install_package(
        imported["record"]["package_id"],
        imported["record"]["version"],
        imported["record"]["content_hash"],
        "untrusted",
    )["installation"]

    try:
        PortalRuntimeService(tmp_path).run(
            PortalRunRequest(
                installation_id=installation["installation_id"],
                launch_profile_id="py",
                trust_state=TrustState.UNTRUSTED_IMPORTED_PACKAGE,
            )
        )
    except PortalRuntimeError as exc:
        assert exc.code == "untrusted_package_run_blocked_by_default"
    else:
        raise AssertionError("untrusted run must require override")


def test_portal_composite_profile_runs_through_play_composite_contract(tmp_path: Path) -> None:
    profiles = [
        LaunchProfile(profile_id="api", name="API", kind=LaunchKind.PYTHON_SCRIPT, entrypoint="api.py"),
        LaunchProfile(profile_id="stack", name="Stack", kind=LaunchKind.COMPOSITE, depends_on=["api"]),
    ]
    package = _build_package(tmp_path, profiles=profiles, selected=["api", "stack"])
    installation = _install(tmp_path, package)["installation"]
    service = PortalRuntimeService(tmp_path)

    result = service.run(
        PortalRunRequest(
            installation_id=installation["installation_id"],
            launch_profile_id="stack",
            trust_state=TrustState.TRUSTED_LOCAL_CAPSULE,
        )
    )
    service.stop(result["runtime"]["play_session_id"])

    assert result["play_session"]["launch_kind"] == "composite"
    assert result["play_session"]["services"][0]["service_id"] == "api"


def test_portal_runtime_does_not_directly_spawn_processes() -> None:
    text = (ROOT / "app/portal/runtime.py").read_text(encoding="utf-8")

    assert "subprocess" not in text
    assert "Popen" not in text
    assert "PlaySessionManager" in text


def test_portal_runtime_api_install_run_stop_purge(tmp_path: Path) -> None:
    package = _build_package(tmp_path)
    record = package["record"]
    client = _client(tmp_path)

    installed = client.post(
        "/api/portal/install",
        json={"package_id": record["package_id"], "version": record["version"], "content_hash": record["content_hash"], "installation_id": "api-inst"},
    )
    run = client.post(
        "/api/portal/run",
        json={
            "installation_id": "api-inst",
            "launch_profile_id": "py",
            "run_mode": "ephemeral",
            "trust_state": "trusted_local_capsule",
        },
    )
    play_session_id = run.json()["runtime"]["play_session_id"]
    stopped = client.post(f"/api/portal/runs/{play_session_id}/stop")
    purged = client.post(f"/api/portal/runs/{play_session_id}/purge")

    assert installed.status_code == 200
    assert run.status_code == 200
    assert stopped.status_code == 200
    assert purged.status_code == 200
