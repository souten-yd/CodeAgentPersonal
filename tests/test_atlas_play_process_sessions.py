import socket
import sys
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.atlas_play import router as atlas_play_router
from app.atlas.play.contracts import LaunchKind, LaunchProfile, PlayResourceLimits
from app.atlas.play.environment import build_structured_launch_adapter
from app.atlas.play.sessions import (
    PlayProcessPolicy,
    PlaySessionError,
    PlaySessionManager,
    PlaySessionRecord,
    PlaySessionRepository,
    reconcile_play_startup_orphans,
)


def _project(tmp_path: Path, project_id: str = "demo") -> Path:
    work = tmp_path / "atlas" / "projects" / project_id / "work"
    work.mkdir(parents=True)
    return work


def _python_adapter(work: Path, entrypoint: str = "app.py"):
    return build_structured_launch_adapter(
        work,
        LaunchProfile(profile_id="py", name="Python", kind=LaunchKind.PYTHON_SCRIPT, entrypoint=entrypoint),
    )


def _static_adapter(work: Path):
    return build_structured_launch_adapter(
        work,
        LaunchProfile(profile_id="web", name="Web", kind=LaunchKind.STATIC_WEB, entrypoint="index.html"),
    )


def _client(tmp_path: Path) -> TestClient:
    app = FastAPI()
    app.state.atlas_ca_data_root = str(tmp_path)
    app.include_router(atlas_play_router)
    return TestClient(app)


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


def test_short_lived_python_success_and_failure_are_recorded(tmp_path: Path) -> None:
    work = _project(tmp_path)
    (work / "ok.py").write_text("print('hello from play')\n", encoding="utf-8")
    (work / "fail.py").write_text("import sys\nprint('bad')\nsys.exit(3)\n", encoding="utf-8")
    manager = PlaySessionManager(tmp_path)

    success = manager.start_session(project_id="demo", project_root=work, adapter=_python_adapter(work, "ok.py"))
    success = manager.wait_for_terminal(success.session_id)
    failure = manager.start_session(project_id="demo", project_root=work, adapter=_python_adapter(work, "fail.py"))
    failure = manager.wait_for_terminal(failure.session_id)

    assert success.state == "stopped"
    assert success.exit_code == 0
    assert any("hello from play" in line for line in success.log_tail)
    assert failure.state == "failed"
    assert failure.exit_code == 3


def test_long_lived_python_stop_releases_port(tmp_path: Path) -> None:
    work = _project(tmp_path)
    (work / "sleepy.py").write_text("import time\nprint('ready', flush=True)\ntime.sleep(30)\n", encoding="utf-8")
    manager = PlaySessionManager(tmp_path)

    record = manager.start_session(project_id="demo", project_root=work, adapter=_python_adapter(work, "sleepy.py"))
    stopped = manager.stop_session(record.session_id)

    assert stopped.state == "stopped"
    assert stopped.stop_reason == "user_stop"
    assert stopped.port is not None
    _assert_port_released(stopped.port)


def test_restart_reuses_session_id_and_process_contract(tmp_path: Path) -> None:
    work = _project(tmp_path)
    (work / "sleepy.py").write_text("import time\nprint('ready', flush=True)\ntime.sleep(30)\n", encoding="utf-8")
    manager = PlaySessionManager(tmp_path)

    record = manager.start_session(project_id="demo", project_root=work, adapter=_python_adapter(work, "sleepy.py"))
    restarted = manager.restart_session(record.session_id)
    manager.stop_session(restarted.session_id)

    assert restarted.session_id == record.session_id
    assert restarted.pid != record.pid
    assert any(event["event_type"] == "session_restarted" for event in restarted.events)


def test_session_timeout_expiry_and_purge_cleanup_runtime_dir(tmp_path: Path) -> None:
    work = _project(tmp_path)
    (work / "sleepy.py").write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
    manager = PlaySessionManager(tmp_path)

    record = manager.start_session(
        project_id="demo",
        project_root=work,
        adapter=_python_adapter(work, "sleepy.py"),
        max_session_seconds=1,
    )
    time.sleep(1.2)
    expired = manager.reap_expired_sessions()
    purged = manager.purge_session(record.session_id)

    assert [item.session_id for item in expired] == [record.session_id]
    assert expired[0].state == "expired"
    assert purged.state == "purged"
    assert purged.runtime_dir
    assert not Path(purged.runtime_dir).exists()


def test_log_tail_is_bounded(tmp_path: Path) -> None:
    work = _project(tmp_path)
    (work / "noisy.py").write_text(
        "for i in range(9000):\n    print('line-' + str(i) + '-' + ('x' * 80))\n",
        encoding="utf-8",
    )
    manager = PlaySessionManager(tmp_path, limits=PlayResourceLimits(max_log_bytes_per_session=64_000))

    record = manager.start_session(project_id="demo", project_root=work, adapter=_python_adapter(work, "noisy.py"))
    record = manager.wait_for_terminal(record.session_id, timeout_seconds=10)

    assert record.state == "stopped"
    assert len("\n".join(record.log_tail).encode("utf-8")) <= 64_000
    assert not any("line-0-" in line for line in record.log_tail)


def test_concurrent_total_session_limit_fails_closed(tmp_path: Path) -> None:
    work = _project(tmp_path)
    (work / "sleepy.py").write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
    manager = PlaySessionManager(tmp_path, limits=PlayResourceLimits(max_total_sessions=1))
    record = manager.start_session(project_id="demo", project_root=work, adapter=_python_adapter(work, "sleepy.py"))

    with pytest.raises(PlaySessionError) as exc:
        manager.start_session(project_id="demo", project_root=work, adapter=_python_adapter(work, "sleepy.py"))

    manager.stop_session(record.session_id)
    assert exc.value.code == "total_session_limit_reached"


def test_static_web_session_uses_loopback_port_and_releases_it(tmp_path: Path) -> None:
    work = _project(tmp_path)
    (work / "index.html").write_text("<h1>ok</h1>", encoding="utf-8")
    manager = PlaySessionManager(tmp_path)

    record = manager.start_session(project_id="demo", project_root=work, adapter=_static_adapter(work))
    stopped = manager.stop_session(record.session_id)

    assert record.preview_url == f"http://127.0.0.1:{record.port}/"
    assert stopped.port is not None
    _assert_port_released(stopped.port)


def test_startup_orphan_reconciliation_marks_active_records_failed(tmp_path: Path) -> None:
    repository = PlaySessionRepository(tmp_path)
    record = PlaySessionRecord(
        session_id="play-orphan",
        project_id="demo",
        project_root=str(_project(tmp_path)),
        state="running",
        launch_profile_id="py",
        launch_kind=LaunchKind.PYTHON_SCRIPT,
        adapter={"status": "ready", "profile_id": "py", "kind": "python_script"},
        pid=99999999,
        process_policy=PlayProcessPolicy(uses_process_group=True, cleanup_strategy="test"),
    )
    repository.save(record)

    reconciled = reconcile_play_startup_orphans(tmp_path)

    assert [item.session_id for item in reconciled] == ["play-orphan"]
    updated = repository.load("play-orphan")
    assert updated.state == "failed"
    assert updated.stop_reason == "startup_orphan_reconciled"
    assert any(event["event_type"] == "startup_orphan_reconciled" for event in updated.events)


def test_windows_child_tree_cleanup_contract_is_first_class() -> None:
    policy = PlayProcessPolicy(
        uses_process_group=True,
        windows_job_object_required=True,
        windows_child_tree_cleanup_strategy="job_object_or_taskkill_tree",
        cleanup_strategy="windows_process_group_and_taskkill_tree",
    )

    assert policy.windows_job_object_required is True
    assert policy.windows_child_tree_cleanup_strategy == "job_object_or_taskkill_tree"


def test_session_api_starts_stops_and_blocks_deferred_launch_kind(tmp_path: Path) -> None:
    work = _project(tmp_path)
    (work / "sleepy.py").write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
    client = _client(tmp_path)

    response = client.post(
        "/api/atlas/play/sessions/start",
        json={
            "project_id": "demo",
            "launch_profile": {
                "profile_id": "py",
                "name": "Python",
                "kind": "python_script",
                "entrypoint": "sleepy.py",
            },
        },
    )
    data = response.json()
    stop = client.post(f"/api/atlas/play/sessions/{data['session_id']}/stop")
    deferred = client.post(
        "/api/atlas/play/sessions/start",
        json={
            "project_id": "demo",
                "launch_profile": {
                    "profile_id": "streamlit",
                    "name": "Streamlit",
                    "kind": "streamlit",
                    "entrypoint": "sleepy.py",
                },
            },
    )

    assert response.status_code == 200
    assert data["state"] == "running"
    assert stop.status_code == 200
    assert stop.json()["state"] == "stopped"
    assert deferred.status_code == 400
    assert deferred.json()["detail"]["error"] == "launch_kind_deferred_to_later_package"
