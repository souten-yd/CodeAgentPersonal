import socket
import time
import zipfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.atlas_play import router as atlas_play_router
from app.api.portal import router as portal_router
from app.atlas.capsule.builder import CapsuleBuilder
from app.atlas.capsule.contracts import CapsuleBuildRequest
from app.atlas.play.contracts import LaunchKind, LaunchProfile, TrustState
from app.atlas.play.environment import build_structured_launch_adapter
from app.atlas.play.sessions import PlayProcessPolicy, PlaySessionManager, PlaySessionRecord, PlaySessionRepository
from app.portal.catalog import PortalCatalogError, PortalCatalogService
from app.portal.contracts import PortalRunMode, PortalRunRequest
from app.portal.recovery import PortalRecoveryService
from app.portal.runtime import PortalRuntimeService


def _project(tmp_path: Path, project_id: str = "demo") -> Path:
    work = tmp_path / "atlas" / "projects" / project_id / "work"
    work.mkdir(parents=True)
    return work


def _client(tmp_path: Path) -> TestClient:
    app = FastAPI()
    app.state.atlas_ca_data_root = str(tmp_path)
    app.include_router(atlas_play_router)
    app.include_router(portal_router)
    return TestClient(app)


def _wait_get(client: TestClient, url: str):
    deadline = time.monotonic() + 5
    last = None
    while time.monotonic() < deadline:
        last = client.get(url)
        if last.status_code < 500:
            return last
        time.sleep(0.05)
    return last


def _assert_port_released(port: int) -> None:
    deadline = time.monotonic() + 5
    last_error: OSError | None = None
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return
            except OSError as exc:
                last_error = exc
        time.sleep(0.05)
    raise AssertionError(f"port {port} was not released: {last_error}")


def _save_success_record(tmp_path: Path, work: Path, profiles: list[LaunchProfile], profile_id: str = "py") -> None:
    adapter = build_structured_launch_adapter(work, next(profile for profile in profiles if profile.profile_id == profile_id))
    PlaySessionRepository(tmp_path).save(
        PlaySessionRecord(
            session_id="play-success",
            project_id="demo",
            project_root=str(work),
            state="stopped",
            launch_profile_id=profile_id,
            launch_kind=adapter.kind,
            adapter=adapter.model_dump(mode="json"),
            process_policy=PlayProcessPolicy(uses_process_group=True, cleanup_strategy="test"),
            exit_code=0,
        )
    )


def _build_capsule(tmp_path: Path, work: Path, profiles: list[LaunchProfile], selected: list[str]) -> dict:
    _save_success_record(tmp_path, work, profiles, selected[0])
    return CapsuleBuilder(tmp_path).build(
        CapsuleBuildRequest(
            project_id="demo",
            play_session_id="play-success",
            selected_profile_ids=selected,
            package_id="acceptance.package",
            name="Acceptance Package",
            version="1.0.0",
            launch_profiles=profiles,
            default_profile_id=selected[-1],
        )
    )


def test_acceptance_static_preview_mobile_file_edit_restart_and_path_security(tmp_path: Path) -> None:
    work = _project(tmp_path, "web")
    (work / "assets" / "js").mkdir(parents=True)
    (work / "assets" / "css").mkdir(parents=True)
    (work / "index.html").write_text("<link rel='stylesheet' href='/assets/css/app.css'><script src='/assets/js/app.js'></script>", encoding="utf-8")
    (work / "assets" / "js" / "app.js").write_text("console.log('mobile')\n", encoding="utf-8")
    (work / "assets" / "css" / "app.css").write_text("body{color:#111}\n", encoding="utf-8")
    manager = PlaySessionManager(tmp_path)
    adapter = build_structured_launch_adapter(work, LaunchProfile(profile_id="web", name="Web", kind=LaunchKind.STATIC_WEB, entrypoint="index.html"))
    session = manager.start_session(project_id="web", project_root=work, adapter=adapter)
    client = _client(tmp_path)

    index = client.get(f"/api/atlas/play/preview/{session.session_id}/index.html")
    asset = client.get(f"/api/atlas/play/preview/{session.session_id}/assets/js/app.js")
    read = client.post("/api/atlas/play/workspace/files/read", json={"project_id": "web", "relative_path": "index.html"})
    write = client.post(
        "/api/atlas/play/workspace/files/write",
        json={"project_id": "web", "relative_path": "index.html", "content": "<h1>saved</h1>\n", "expected_sha256": read.json()["sha256"]},
    )
    escape = client.post("/api/atlas/play/workspace/files/read", json={"project_id": "web", "relative_path": "%2e%2e/secret.txt"})
    restarted = manager.restart_session(session.session_id)
    stopped = manager.stop_session(restarted.session_id)

    assert index.status_code == 200
    assert asset.status_code == 200
    assert write.status_code == 200
    assert (work / "index.html").read_text(encoding="utf-8") == "<h1>saved</h1>\n"
    assert escape.status_code == 400
    assert stopped.port is not None
    _assert_port_released(stopped.port)


def test_acceptance_python_output_failure_and_asgi_proxy_sse_websocket(tmp_path: Path) -> None:
    work = _project(tmp_path, "server")
    (work / "ok.py").write_text("print('python-ok')\n", encoding="utf-8")
    (work / "fail.py").write_text("import sys\nprint('python-fail')\nsys.exit(7)\n", encoding="utf-8")
    (work / "api.py").write_text(
        """
from fastapi import FastAPI, WebSocket
from fastapi.responses import StreamingResponse

app = FastAPI()

@app.get('/hello')
def hello():
    return {'ok': True}

@app.get('/events')
def events():
    return StreamingResponse(iter(['data: one\\n\\n']), media_type='text/event-stream')

@app.websocket('/ws')
async def ws(websocket: WebSocket):
    await websocket.accept()
    text = await websocket.receive_text()
    await websocket.send_text('echo:' + text)
    await websocket.close()
""".lstrip(),
        encoding="utf-8",
    )
    manager = PlaySessionManager(tmp_path)
    ok = manager.wait_for_terminal(
        manager.start_session(
            project_id="server",
            project_root=work,
            adapter=build_structured_launch_adapter(work, LaunchProfile(profile_id="ok", name="OK", kind=LaunchKind.PYTHON_SCRIPT, entrypoint="ok.py")),
        ).session_id
    )
    failed = manager.wait_for_terminal(
        manager.start_session(
            project_id="server",
            project_root=work,
            adapter=build_structured_launch_adapter(work, LaunchProfile(profile_id="fail", name="Fail", kind=LaunchKind.PYTHON_SCRIPT, entrypoint="fail.py")),
        ).session_id
    )
    asgi = manager.start_session(
        project_id="server",
        project_root=work,
        adapter=build_structured_launch_adapter(work, LaunchProfile(profile_id="api", name="API", kind=LaunchKind.PYTHON_ASGI, entrypoint="api.py")),
    )
    client = _client(tmp_path)
    hello = _wait_get(client, f"/api/atlas/play/proxy/{asgi.session_id}/hello")
    events = _wait_get(client, f"/api/atlas/play/proxy/{asgi.session_id}/events")
    with client.websocket_connect(f"/api/atlas/play/proxy/{asgi.session_id}/ws/ws") as websocket:
        websocket.send_text("hello")
        received = websocket.receive_text()
    stopped = manager.stop_session(asgi.session_id)

    assert ok.state == "stopped"
    assert any("python-ok" in line for line in ok.log_tail)
    assert failed.state == "failed"
    assert failed.exit_code == 7
    assert hello.json() == {"ok": True}
    assert "data: one" in events.text
    assert received == "echo:hello"
    assert stopped.port is not None
    _assert_port_released(stopped.port)


def test_acceptance_capsule_portal_import_export_data_snapshot_recovery_and_fork(tmp_path: Path) -> None:
    work = _project(tmp_path)
    (work / "app.py").write_text("import time\nprint('portal', flush=True)\ntime.sleep(30)\n", encoding="utf-8")
    (work / "index.html").write_text("<h1>portal</h1>", encoding="utf-8")
    profiles = [
        LaunchProfile(profile_id="py", name="Python", kind=LaunchKind.PYTHON_SCRIPT, entrypoint="app.py"),
        LaunchProfile(profile_id="web", name="Web", kind=LaunchKind.STATIC_WEB, entrypoint="index.html"),
        LaunchProfile(profile_id="combo", name="Combo", kind=LaunchKind.COMPOSITE, depends_on=["py", "web"]),
    ]
    package = _build_capsule(tmp_path, work, profiles, ["py", "web", "combo"])
    record = package["record"]
    catalog = PortalCatalogService(tmp_path)
    runtime_service = PortalRuntimeService(tmp_path)
    installation = runtime_service.install_package(record["package_id"], record["version"], record["content_hash"], "inst")["installation"]
    exported = catalog.export_package_path(record["package_id"], record["version"], record["content_hash"])
    imported = catalog.import_archive(exported)

    run = runtime_service.run(
        PortalRunRequest(
            installation_id=installation["installation_id"],
            launch_profile_id="py",
            run_mode=PortalRunMode.START_EMPTY,
            trust_state=TrustState.TRUSTED_LOCAL_CAPSULE,
        )
    )
    Path(run["runtime"]["data_root"], "save.db").write_text("saved", encoding="utf-8")
    saved = runtime_service.save_and_exit(run["runtime"]["play_session_id"])
    next_run = runtime_service.run(
        PortalRunRequest(
            installation_id="inst",
            launch_profile_id="py",
            trust_state=TrustState.TRUSTED_LOCAL_CAPSULE,
        )
    )
    assert Path(next_run["runtime"]["data_root"], "save.db").read_text(encoding="utf-8") == "saved"
    runtime_service.discard_and_exit(next_run["runtime"]["play_session_id"])
    snapshot_run = runtime_service.run(
        PortalRunRequest(
            installation_id="inst",
            launch_profile_id="py",
            run_mode=PortalRunMode.START_EMPTY,
            trust_state=TrustState.TRUSTED_LOCAL_CAPSULE,
        )
    )
    Path(snapshot_run["runtime"]["data_root"], "snapshot.txt").write_text("snapshot", encoding="utf-8")
    snapshot = runtime_service.save_snapshot_and_exit(snapshot_run["runtime"]["play_session_id"], "snap")
    from_snapshot = runtime_service.run(
        PortalRunRequest(
            installation_id="inst",
            launch_profile_id="py",
            run_mode=PortalRunMode.START_FROM_SNAPSHOT,
            snapshot_id="snap",
            trust_state=TrustState.TRUSTED_LOCAL_CAPSULE,
        )
    )
    assert Path(from_snapshot["runtime"]["data_root"], "snapshot.txt").read_text(encoding="utf-8") == "snapshot"
    runtime_service.discard_and_exit(from_snapshot["runtime"]["play_session_id"])
    ephemeral = runtime_service.run(
        PortalRunRequest(
            installation_id="inst",
            launch_profile_id="py",
            run_mode=PortalRunMode.EPHEMERAL,
            trust_state=TrustState.TRUSTED_LOCAL_CAPSULE,
        )
    )
    disconnected = runtime_service.disconnect(ephemeral["runtime"]["play_session_id"], ephemeral["reconnect_token"])["runtime"]
    stored = tmp_path / "portal" / "recovery" / disconnected["play_session_id"] / "portal_run.json"
    data = __import__("json").loads(stored.read_text(encoding="utf-8"))
    data["recovery_expires_at"] = "2000-01-01T00:00:00+00:00"
    stored.write_text(__import__("json").dumps(data), encoding="utf-8")
    expired = PortalRecoveryService(tmp_path).expire_recoveries()
    forked = catalog.fork_to_atlas(record["package_id"], record["version"], record["content_hash"], "forked")

    with zipfile.ZipFile(exported) as zf:
        assert not any(name.startswith(("current/", "snapshots/", "data/")) for name in zf.namelist())
    assert len(package["manifest"]["launch_profiles"]) == 3
    assert imported["record"]["trust_state"] == "untrusted_imported_package"
    assert saved["data"]["current_data"]["bytes"] == 5
    assert snapshot["snapshot"]["immutable"] is True
    assert expired[0]["data_decision"] == "expired_discard"
    assert Path(forked["project_work_root"], "app.py").exists()


@pytest.mark.parametrize("bad_name", ["../x", "/abs", "C:/x", "a\\..\\x"])
def test_acceptance_import_quarantine_rejects_unsafe_archive_matrix(tmp_path: Path, bad_name: str) -> None:
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(bad_name, b"x")

    try:
        PortalCatalogService(tmp_path).preflight_archive(archive)
    except PortalCatalogError as exc:
        assert exc.code == "archive_entry_unsafe"
    else:
        raise AssertionError("unsafe archive entry must be rejected")


def test_acceptance_node_and_vite_structured_adapters_are_supported_without_free_form_commands(tmp_path: Path) -> None:
    work = _project(tmp_path, "node")
    (work / "server.js").write_text("console.log('node')\n", encoding="utf-8")
    (work / "package.json").write_text('{"scripts":{"dev":"vite --host 127.0.0.1"}}\n', encoding="utf-8")
    node = build_structured_launch_adapter(work, LaunchProfile(profile_id="node", name="Node", kind=LaunchKind.NODE_SCRIPT, entrypoint="server.js"))
    vite = build_structured_launch_adapter(work, LaunchProfile(profile_id="vite", name="Vite", kind=LaunchKind.VITE, entrypoint="server.js"))

    assert node.status == "ready"
    assert vite.status == "ready"
    assert "shell" not in " ".join(node.argv + vite.argv).lower()
    assert node.host_mutation_allowed is False
    assert vite.host_mutation_allowed is False
    assert node.port.loopback_only is True
    assert vite.port.loopback_only is True
