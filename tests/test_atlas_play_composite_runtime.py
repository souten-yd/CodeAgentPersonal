import socket
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.atlas_play import router as atlas_play_router
from app.atlas.play.contracts import LaunchKind, LaunchProfile
from app.atlas.play.sessions import PlaySessionManager


def _project(tmp_path: Path, project_id: str = "demo") -> Path:
    work = tmp_path / "atlas" / "projects" / project_id / "work"
    work.mkdir(parents=True)
    return work


def _client(tmp_path: Path) -> TestClient:
    app = FastAPI()
    app.state.atlas_ca_data_root = str(tmp_path)
    app.include_router(atlas_play_router)
    return TestClient(app)


def _write_port_server(path: Path, label: str) -> None:
    path.write_text(
        "\n".join(
            [
                "import os, socket, time",
                "sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)",
                "sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)",
                "sock.bind(('127.0.0.1', int(os.environ['ATLAS_PLAY_PORT'])))",
                "sock.listen(1)",
                f"print('{label} ready', flush=True)",
                "time.sleep(30)",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _assert_port_released(port: int) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return
            except OSError:
                time.sleep(0.05)
    raise AssertionError(f"port {port} was not released")


def _profiles() -> list[LaunchProfile]:
    return [
        LaunchProfile(profile_id="api", name="API", kind=LaunchKind.PYTHON_SCRIPT, entrypoint="api.py"),
        LaunchProfile(profile_id="web", name="Web", kind=LaunchKind.PYTHON_SCRIPT, entrypoint="web.py", depends_on=["api"]),
        LaunchProfile(profile_id="stack", name="Stack", kind=LaunchKind.COMPOSITE, depends_on=["web"]),
    ]


def test_composite_starts_services_in_dependency_order_and_records_ports(tmp_path: Path) -> None:
    work = _project(tmp_path)
    _write_port_server(work / "api.py", "api")
    _write_port_server(work / "web.py", "web")
    manager = PlaySessionManager(tmp_path)

    record = manager.start_composite_session(
        project_id="demo",
        project_root=work,
        launch_profiles=_profiles(),
        composite_profile_id="stack",
    )
    events = [event for event in record.events if event["event_type"] == "composite_service_started"]
    stopped = manager.stop_session(record.session_id)

    assert record.state == "running"
    assert record.readiness_status == "ready"
    assert [event["details"]["service_id"] for event in events] == ["api", "web"]
    assert [service.service_id for service in record.services] == ["api", "web"]
    assert all(service.readiness_status == "ready" for service in record.services)
    assert all(service.port for service in record.services)
    assert stopped.state == "stopped"


def test_composite_readiness_timeout_cleans_started_children_and_releases_ports(tmp_path: Path) -> None:
    work = _project(tmp_path)
    _write_port_server(work / "api.py", "api")
    (work / "web.py").write_text("import time\nprint('not listening', flush=True)\ntime.sleep(30)\n", encoding="utf-8")
    manager = PlaySessionManager(tmp_path)

    record = manager.start_composite_session(
        project_id="demo",
        project_root=work,
        launch_profiles=_profiles(),
        composite_profile_id="stack",
        readiness_timeout_seconds=0.5,
    )

    assert record.state == "failed"
    assert record.stop_reason == "readiness_timeout"
    assert any(service.service_id == "web" and service.readiness_status == "failed" for service in record.services)
    for child_id in record.child_session_ids:
        child = manager.get_session(child_id)
        assert child.state in {"stopped", "failed"}
        if child.port:
            _assert_port_released(child.port)


def test_composite_partial_service_failure_stops_already_ready_children(tmp_path: Path) -> None:
    work = _project(tmp_path)
    _write_port_server(work / "api.py", "api")
    (work / "web.py").write_text("import sys\nprint('boom', flush=True)\nsys.exit(7)\n", encoding="utf-8")
    manager = PlaySessionManager(tmp_path)

    record = manager.start_composite_session(
        project_id="demo",
        project_root=work,
        launch_profiles=_profiles(),
        composite_profile_id="stack",
        readiness_timeout_seconds=2,
    )

    assert record.state == "failed"
    assert record.stop_reason == "service_exit_before_ready"
    assert any(service.service_id == "web" and service.readiness_error == "service_exit_before_ready" for service in record.services)
    for child_id in record.child_session_ids:
        child = manager.get_session(child_id)
        assert child.state in {"stopped", "failed"}
        if child.port:
            _assert_port_released(child.port)


def test_stopping_composite_stops_all_children_and_releases_ports(tmp_path: Path) -> None:
    work = _project(tmp_path)
    _write_port_server(work / "api.py", "api")
    _write_port_server(work / "web.py", "web")
    manager = PlaySessionManager(tmp_path)
    record = manager.start_composite_session(
        project_id="demo",
        project_root=work,
        launch_profiles=_profiles(),
        composite_profile_id="stack",
    )
    child_ports = [service.port for service in record.services if service.port]

    stopped = manager.stop_session(record.session_id)

    assert stopped.state == "stopped"
    assert all(manager.get_session(child_id).state == "stopped" for child_id in record.child_session_ids)
    for port in child_ports:
        _assert_port_released(port)


def test_composite_start_api_returns_recovery_metadata(tmp_path: Path) -> None:
    work = _project(tmp_path)
    _write_port_server(work / "api.py", "api")
    _write_port_server(work / "web.py", "web")
    client = _client(tmp_path)

    response = client.post(
        "/api/atlas/play/sessions/composite/start",
        json={
            "project_id": "demo",
            "composite_profile_id": "stack",
            "launch_profiles": [
                {"profile_id": "api", "name": "API", "kind": "python_script", "entrypoint": "api.py"},
                {"profile_id": "web", "name": "Web", "kind": "python_script", "entrypoint": "web.py", "depends_on": ["api"]},
                {"profile_id": "stack", "name": "Stack", "kind": "composite", "depends_on": ["web"]},
            ],
        },
    )
    data = response.json()
    stop = client.post(f"/api/atlas/play/sessions/{data['session_id']}/stop")

    assert response.status_code == 200
    assert data["state"] == "running"
    assert data["launch_kind"] == "composite"
    assert [service["service_id"] for service in data["services"]] == ["api", "web"]
    assert stop.status_code == 200
