import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.portal import router as portal_router
from app.atlas.capsule.builder import CapsuleBuilder
from app.atlas.capsule.contracts import CapsuleBuildRequest
from app.atlas.play.contracts import LaunchKind, LaunchProfile, TrustState
from app.atlas.play.environment import build_structured_launch_adapter
from app.atlas.play.sessions import (
    PlayProcessPolicy,
    PlaySessionRecord,
    PlaySessionRepository,
    reconcile_play_startup_orphans,
)
from app.portal.contracts import PortalRunMode, PortalRunRequest
from app.portal.recovery import PortalRecoveryError, PortalRecoveryService, reconcile_portal_startup_recovery
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


def _install(tmp_path: Path) -> dict:
    work = _project(tmp_path)
    (work / "app.py").write_text("import time\nprint('recoverable', flush=True)\ntime.sleep(30)\n", encoding="utf-8")
    _save_success(tmp_path, work)
    package = CapsuleBuilder(tmp_path).build(
        CapsuleBuildRequest(
            project_id="demo",
            play_session_id="play-success",
            selected_profile_ids=["py"],
            package_id="portal.recovery.package",
            name="Portal Recovery Package",
            version="1.0.0",
        )
    )
    record = package["record"]
    installation = PortalRuntimeService(tmp_path).install_package(
        record["package_id"],
        record["version"],
        record["content_hash"],
        "inst",
    )["installation"]
    return {"package": package, "record": record, "installation": installation}


def _run(tmp_path: Path) -> dict:
    return PortalRuntimeService(tmp_path).run(
        PortalRunRequest(
            installation_id="inst",
            launch_profile_id="py",
            run_mode=PortalRunMode.START_EMPTY,
            trust_state=TrustState.TRUSTED_LOCAL_CAPSULE,
        )
    )


def _runtime_path(tmp_path: Path, play_session_id: str) -> Path:
    return tmp_path / "portal" / "recovery" / play_session_id / "portal_run.json"


def _client(tmp_path: Path) -> TestClient:
    app = FastAPI()
    app.state.atlas_ca_data_root = str(tmp_path)
    app.include_router(portal_router)
    return TestClient(app)


def test_heartbeat_uses_reconnect_token_and_hides_token_hash(tmp_path: Path) -> None:
    _install(tmp_path)
    result = _run(tmp_path)
    token = result["reconnect_token"]
    play_session_id = result["runtime"]["play_session_id"]
    service = PortalRuntimeService(tmp_path)

    heartbeat = service.heartbeat(play_session_id, token)
    try:
        service.heartbeat(play_session_id, "wrong")
    except PortalRuntimeError as exc:
        assert exc.code == "reconnect_token_invalid"
    else:
        raise AssertionError("wrong reconnect token must fail")

    assert "reconnect_token_hash" not in result["runtime"]
    assert heartbeat["runtime"]["recovery_state"] == "running"
    assert any(event["event_type"] == "heartbeat" for event in heartbeat["runtime"]["events"])
    service.discard_and_exit(play_session_id)


def test_disconnect_duplicate_resume_and_repeated_discard_are_idempotent(tmp_path: Path) -> None:
    _install(tmp_path)
    service = PortalRuntimeService(tmp_path)
    result = _run(tmp_path)
    token = result["reconnect_token"]
    runtime = result["runtime"]
    Path(runtime["data_root"], "save.db").write_text("changed", encoding="utf-8")

    disconnected = service.disconnect(runtime["play_session_id"], token)
    duplicate = service.disconnect(runtime["play_session_id"], token)
    resumed = service.resume(runtime["play_session_id"], token)
    discarded = service.discard_and_exit(runtime["play_session_id"])
    repeated = service.discard_and_exit(runtime["play_session_id"])

    assert disconnected["runtime"]["recovery_state"] == "recoverable"
    assert duplicate["runtime"]["recovery_state"] == "recoverable"
    assert resumed["runtime"]["recovery_state"] == "running"
    assert discarded["status"] == "discarded"
    assert repeated["status"] == "discarded"
    assert not Path(runtime["data_root"]).exists()


def test_startup_reconciliation_marks_portal_runtime_recoverable_after_play_orphan(tmp_path: Path) -> None:
    _install(tmp_path)
    service = PortalRuntimeService(tmp_path)
    result = _run(tmp_path)
    play_session_id = result["runtime"]["play_session_id"]

    service.stop(play_session_id)
    play = PlaySessionRepository(tmp_path).load(play_session_id)
    play.pid = 99999999
    play.state = "running"
    PlaySessionRepository(tmp_path).save(play)
    play_reconciled = reconcile_play_startup_orphans(tmp_path)
    portal_reconciled = reconcile_portal_startup_recovery(tmp_path)

    assert [item.session_id for item in play_reconciled] == [play_session_id]
    assert portal_reconciled[0]["recovery_state"] == "recoverable"
    assert portal_reconciled[0]["status"] == "recoverable"
    assert any(event["event_type"] == "startup_reconciled" for event in portal_reconciled[0]["events"])
    service.discard_and_exit(play_session_id)


def test_expired_recovery_purges_staged_application_and_session_data(tmp_path: Path) -> None:
    _install(tmp_path)
    service = PortalRuntimeService(tmp_path)
    result = _run(tmp_path)
    play_session_id = result["runtime"]["play_session_id"]
    token = result["reconnect_token"]
    runtime = service.disconnect(play_session_id, token)["runtime"]
    Path(runtime["data_root"], "save.db").write_text("changed", encoding="utf-8")
    path = _runtime_path(tmp_path, play_session_id)
    stored = json.loads(path.read_text(encoding="utf-8"))
    stored["recovery_expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    path.write_text(json.dumps(stored), encoding="utf-8")

    expired = PortalRecoveryService(tmp_path).expire_recoveries()

    assert expired[0]["recovery_state"] == "expired"
    assert expired[0]["data_decision"] == "expired_discard"
    assert not Path(runtime["application_root"]).exists()
    assert not Path(runtime["data_root"]).exists()


def test_recovery_api_disconnect_resume_and_expire(tmp_path: Path) -> None:
    _install(tmp_path)
    client = _client(tmp_path)
    run = client.post(
        "/api/portal/run",
        json={
            "installation_id": "inst",
            "launch_profile_id": "py",
            "run_mode": "start_empty",
            "trust_state": "trusted_local_capsule",
        },
    ).json()
    play_session_id = run["runtime"]["play_session_id"]
    token = run["reconnect_token"]

    heartbeat = client.post(f"/api/portal/runs/{play_session_id}/heartbeat", json={"reconnect_token": token})
    disconnected = client.post(f"/api/portal/runs/{play_session_id}/disconnect", json={"reconnect_token": token})
    resumed = client.post(f"/api/portal/runs/{play_session_id}/resume", json={"reconnect_token": token})
    bad_token = client.post(f"/api/portal/runs/{play_session_id}/heartbeat", json={"reconnect_token": "bad"})
    expired = client.post("/api/portal/recoveries/expire")

    assert heartbeat.status_code == 200
    assert disconnected.json()["runtime"]["recovery_state"] == "recoverable"
    assert resumed.json()["runtime"]["recovery_state"] == "running"
    assert bad_token.status_code == 400
    assert expired.status_code == 200
    PortalRuntimeService(tmp_path).discard_and_exit(play_session_id)


def test_interrupted_extraction_record_can_expire_without_process_handle(tmp_path: Path) -> None:
    _install(tmp_path)
    result = _run(tmp_path)
    play_session_id = result["runtime"]["play_session_id"]
    token = result["reconnect_token"]
    runtime = PortalRuntimeService(tmp_path).disconnect(play_session_id, token)["runtime"]
    partial = Path(runtime["application_root"]) / "partial.tmp"
    partial.parent.mkdir(parents=True, exist_ok=True)
    partial.write_text("partial", encoding="utf-8")
    path = _runtime_path(tmp_path, play_session_id)
    stored = json.loads(path.read_text(encoding="utf-8"))
    stored["recovery_expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    path.write_text(json.dumps(stored), encoding="utf-8")

    expired = PortalRecoveryService(tmp_path).expire_recoveries()

    assert expired[0]["status"] == "expired"
    assert not partial.exists()
