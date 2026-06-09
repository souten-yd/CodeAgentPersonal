from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from pydantic import Field

from app.atlas.play.contracts import LaunchKind, LaunchProfile, PlayResourceLimits, StrictContractModel
from app.atlas.play.environment import StructuredLaunchAdapter, build_structured_launch_adapter, validate_composite_launch_profiles
from app.atlas.play.paths import AtlasPlayPathLayout
from app.atlas.play.workspace_policy import WorkspacePermission, decide_workspace_access


PLAY_SESSION_SCHEMA_VERSION = "atlas.play.session.v1"
ACTIVE_SESSION_STATES = {"starting", "running"}
TERMINAL_SESSION_STATES = {"stopped", "failed", "expired", "purged"}


class PlaySessionError(RuntimeError):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


class PlayProcessPolicy(StrictContractModel):
    schema_version: str = PLAY_SESSION_SCHEMA_VERSION
    platform: str = sys.platform
    uses_process_group: bool
    windows_job_object_required: bool = False
    windows_child_tree_cleanup_strategy: str = ""
    cleanup_strategy: str


class PlayCompositeServiceStatus(StrictContractModel):
    schema_version: str = PLAY_SESSION_SCHEMA_VERSION
    service_id: str = Field(min_length=1)
    session_id: str = ""
    state: str = "pending"
    port: int | None = None
    readiness_status: str = "pending"
    readiness_error: str = ""


class PlaySessionRecord(StrictContractModel):
    schema_version: str = PLAY_SESSION_SCHEMA_VERSION
    session_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    project_root: str = Field(min_length=1)
    state: str
    launch_profile_id: str
    launch_kind: LaunchKind
    adapter: dict[str, Any]
    pid: int | None = None
    port: int | None = None
    preview_url: str | None = None
    process_policy: PlayProcessPolicy
    runtime_dir: str = ""
    working_directory: str = "."
    started_at: str = ""
    updated_at: str = ""
    deadline_at: str = ""
    exit_code: int | None = None
    stop_reason: str = ""
    log_tail: list[str] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    parent_session_id: str | None = None
    service_id: str = ""
    child_session_ids: list[str] = Field(default_factory=list)
    services: list[PlayCompositeServiceStatus] = Field(default_factory=list)
    readiness_status: str = ""


class _ActiveProcess:
    def __init__(self, process: subprocess.Popen[str], record: PlaySessionRecord) -> None:
        self.process = process
        self.record = record
        self.lock = threading.Lock()
        self.reader: threading.Thread | None = None


_ACTIVE: dict[str, _ActiveProcess] = {}
_ACTIVE_LOCK = threading.Lock()
_RECORD_LOCKS: dict[str, threading.RLock] = {}
_RECORD_LOCKS_LOCK = threading.Lock()


def _record_lock(session_id: str) -> threading.RLock:
    with _RECORD_LOCKS_LOCK:
        lock = _RECORD_LOCKS.get(session_id)
        if lock is None:
            lock = threading.RLock()
            _RECORD_LOCKS[session_id] = lock
        return lock


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None = None) -> str:
    return (value or _now()).isoformat()


def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _process_policy() -> PlayProcessPolicy:
    if os.name == "nt":
        return PlayProcessPolicy(
            uses_process_group=True,
            windows_job_object_required=True,
            windows_child_tree_cleanup_strategy="job_object_or_taskkill_tree",
            cleanup_strategy="windows_process_group_and_taskkill_tree",
        )
    return PlayProcessPolicy(
        uses_process_group=True,
        cleanup_strategy="posix_process_group",
    )


def _append_event(record: PlaySessionRecord, event_type: str, before: str, after: str, message: str = "", **details: Any) -> None:
    record.events.append(
        {
            "schema_version": PLAY_SESSION_SCHEMA_VERSION,
            "session_id": record.session_id,
            "event_type": event_type,
            "state_before": before,
            "state_after": after,
            "message": message,
            "details": details,
            "created_at": _iso(),
        }
    )
    record.updated_at = _iso()


def _append_log(record: PlaySessionRecord, text: str, max_bytes: int) -> None:
    line = text.rstrip("\r\n")
    if not line:
        return
    record.log_tail.append(line)
    while len(json.dumps(record.log_tail, ensure_ascii=False).encode("utf-8")) > max_bytes and record.log_tail:
        record.log_tail.pop(0)
    record.updated_at = _iso()


def _allocate_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


def _base_environment(adapter: StructuredLaunchAdapter, port: int) -> dict[str, str]:
    env = {
        "PYTHONUNBUFFERED": "1",
        "ATLAS_PLAY_PORT": str(port),
    }
    for key in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA"):
        value = os.environ.get(key)
        if value:
            env[key] = value
    for key, configured_value in adapter.environment.items():
        if key not in {"PATH", "PYTHONPATH", "NODE_OPTIONS"}:
            env[key] = str(configured_value) if configured_value else os.environ.get(key, "")
    return env


def _terminate_process_tree(process: subprocess.Popen[str], timeout_seconds: float = 5.0) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except ProcessLookupError:
            return
        except OSError:
            process.terminate()
    try:
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        if os.name != "nt":
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except OSError:
                process.kill()
        else:
            process.kill()
        process.wait(timeout=timeout_seconds)


def _cleanup_process_id(pid: int) -> None:
    if pid <= 0:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        try:
            os.killpg(pid, signal.SIGTERM)
        except OSError:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass


class PlaySessionRepository:
    def __init__(self, data_root: str | Path) -> None:
        self.data_root = Path(data_root).expanduser().resolve()
        self.layout = AtlasPlayPathLayout(self.data_root)

    def session_dir(self, session_id: str) -> Path:
        return self.layout.play_session_root(session_id)

    def record_path(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "record.json"

    def save(self, record: PlaySessionRecord) -> None:
        with _record_lock(record.session_id):
            path = self.record_path(record.session_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
            tmp_path.write_text(json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
            tmp_path.replace(path)

    def load(self, session_id: str) -> PlaySessionRecord:
        with _record_lock(session_id):
            path = self.record_path(session_id)
            if not path.exists():
                raise PlaySessionError("session_not_found")
            return PlaySessionRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def list_records(self) -> list[PlaySessionRecord]:
        root = self.data_root / "atlas" / "play" / "sessions"
        if not root.exists():
            return []
        records: list[PlaySessionRecord] = []
        for path in sorted(root.glob("*/record.json")):
            try:
                records.append(PlaySessionRecord.model_validate_json(path.read_text(encoding="utf-8")))
            except Exception:
                continue
        return records

    def list_active(self) -> list[PlaySessionRecord]:
        return [record for record in self.list_records() if record.state in ACTIVE_SESSION_STATES]


class PlaySessionManager:
    def __init__(self, data_root: str | Path, *, limits: PlayResourceLimits | None = None) -> None:
        self.data_root = Path(data_root).expanduser().resolve()
        self.repository = PlaySessionRepository(self.data_root)
        self.layout = AtlasPlayPathLayout(self.data_root)
        self.limits = limits or PlayResourceLimits()

    def start_session(
        self,
        *,
        project_id: str,
        project_root: str | Path,
        adapter: StructuredLaunchAdapter,
        max_session_seconds: int | None = None,
        session_id: str | None = None,
        parent_session_id: str | None = None,
        service_id: str = "",
    ) -> PlaySessionRecord:
        self._assert_can_start(project_id, adapter)
        project_root_path = Path(project_root).expanduser().resolve()
        workdir = self._resolve_workdir(project_root_path, adapter)
        argv, port = self._build_argv(project_root_path, workdir, adapter)
        new_session_id = session_id or f"play-{uuid.uuid4().hex}"
        runtime_dir = self.layout.play_temp_root(new_session_id)
        runtime_dir.mkdir(parents=True, exist_ok=True)
        now = _now()
        seconds = min(int(max_session_seconds or self.limits.max_session_seconds), self.limits.max_session_seconds)
        record = PlaySessionRecord(
            session_id=new_session_id,
            project_id=project_id,
            project_root=str(project_root_path),
            state="starting",
            launch_profile_id=adapter.profile_id,
            launch_kind=adapter.kind,
            adapter=adapter.model_dump(mode="json"),
            port=port,
            preview_url=f"http://127.0.0.1:{port}/",
            process_policy=_process_policy(),
            runtime_dir=str(runtime_dir),
            working_directory=adapter.working_directory,
            started_at=_iso(now),
            updated_at=_iso(now),
            deadline_at=_iso(now + timedelta(seconds=seconds)),
            parent_session_id=parent_session_id,
            service_id=service_id,
        )
        _append_event(record, "session_starting", "", "starting", "starting play session")
        creationflags = 0
        start_new_session = False
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        else:
            start_new_session = True
        try:
            process = subprocess.Popen(
                argv,
                cwd=str(workdir),
                env=_base_environment(adapter, port),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=creationflags,
                start_new_session=start_new_session,
            )
        except OSError as exc:
            before = record.state
            record.state = "failed"
            record.stop_reason = "process_start_failed"
            _append_event(record, "session_failed", before, record.state, str(exc))
            self.repository.save(record)
            raise PlaySessionError("process_start_failed", str(exc)) from exc
        record.pid = process.pid
        before = record.state
        record.state = "running"
        _append_event(record, "session_started", before, "running", "process started", pid=process.pid, port=port)
        active = _ActiveProcess(process, record)
        with _ACTIVE_LOCK:
            _ACTIVE[record.session_id] = active
        active.reader = threading.Thread(target=self._read_output, args=(active,), name=f"atlas-play-log-{record.session_id}", daemon=True)
        active.reader.start()
        self.repository.save(record)
        return record

    def start_composite_session(
        self,
        *,
        project_id: str,
        project_root: str | Path,
        launch_profiles: list[LaunchProfile],
        composite_profile_id: str,
        readiness_timeout_seconds: float = 5.0,
        max_session_seconds: int | None = None,
        environment: dict[str, str] | None = None,
    ) -> PlaySessionRecord:
        validation = validate_composite_launch_profiles(launch_profiles)
        if not validation.valid:
            raise PlaySessionError("composite_profile_invalid", ",".join(validation.errors))
        profiles_by_id = {profile.profile_id: profile for profile in launch_profiles}
        composite = profiles_by_id.get(composite_profile_id)
        if composite is None or composite.kind != LaunchKind.COMPOSITE:
            raise PlaySessionError("composite_profile_missing")
        project_root_path = Path(project_root).expanduser().resolve()
        parent_id = f"play-{uuid.uuid4().hex}"
        now = _now()
        seconds = min(int(max_session_seconds or self.limits.max_session_seconds), self.limits.max_session_seconds)
        parent = PlaySessionRecord(
            session_id=parent_id,
            project_id=project_id,
            project_root=str(project_root_path),
            state="starting",
            launch_profile_id=composite.profile_id,
            launch_kind=LaunchKind.COMPOSITE,
            adapter=build_structured_launch_adapter(project_root_path, composite).model_dump(mode="json"),
            process_policy=_process_policy(),
            runtime_dir=str(self.layout.play_temp_root(parent_id)),
            started_at=_iso(now),
            updated_at=_iso(now),
            deadline_at=_iso(now + timedelta(seconds=seconds)),
        )
        Path(parent.runtime_dir).mkdir(parents=True, exist_ok=True)
        _append_event(parent, "composite_starting", "", "starting", "starting composite play session")
        self.repository.save(parent)
        started_children: list[PlaySessionRecord] = []

        def fail_parent(reason: str, message: str) -> PlaySessionRecord:
            for child in list(started_children):
                latest = self.refresh_session(child.session_id)
                if latest.state in ACTIVE_SESSION_STATES:
                    self.stop_session(child.session_id, reason="composite_partial_failure")
            previous = {service.service_id: service for service in parent.services}
            before = parent.state
            parent.state = "failed"
            parent.stop_reason = reason
            merged = self._composite_service_statuses(parent.child_session_ids)
            for index, service in enumerate(merged):
                prior = previous.get(service.service_id)
                if prior and prior.readiness_status == "failed":
                    merged[index] = prior.model_copy(update={"state": service.state, "port": service.port})
            parent.services = merged
            _append_event(parent, "composite_failed", before, parent.state, message, reason=reason)
            self.repository.save(parent)
            return parent

        for profile_id in validation.startup_order:
            profile = profiles_by_id[profile_id]
            if profile.kind == LaunchKind.COMPOSITE:
                continue
            adapter = build_structured_launch_adapter(project_root_path, profile)
            if environment:
                adapter.environment.update(environment)
            try:
                child = self.start_session(
                    project_id=project_id,
                    project_root=project_root_path,
                    adapter=adapter,
                    max_session_seconds=max_session_seconds,
                    parent_session_id=parent_id,
                    service_id=profile.profile_id,
                )
            except PlaySessionError as exc:
                parent.services.append(
                    PlayCompositeServiceStatus(
                        service_id=profile.profile_id,
                        state="failed",
                        readiness_status="failed",
                        readiness_error=exc.code,
                    )
                )
                return fail_parent(exc.code, f"service {profile.profile_id} failed to start")
            started_children.append(child)
            parent.child_session_ids.append(child.session_id)
            _append_event(
                parent,
                "composite_service_started",
                parent.state,
                parent.state,
                "service process started",
                service_id=profile.profile_id,
                session_id=child.session_id,
            )
            ready, readiness_error = self._wait_for_readiness(child.session_id, readiness_timeout_seconds)
            latest = self.refresh_session(child.session_id)
            parent.services.append(
                PlayCompositeServiceStatus(
                    service_id=profile.profile_id,
                    session_id=child.session_id,
                    state=latest.state,
                    port=latest.port,
                    readiness_status="ready" if ready else "failed",
                    readiness_error=readiness_error,
                )
            )
            if not ready:
                return fail_parent(readiness_error or "readiness_timeout", f"service {profile.profile_id} did not become ready")
            self.repository.save(parent)

        before = parent.state
        parent.state = "running"
        parent.readiness_status = "ready"
        parent.services = self._composite_service_statuses(parent.child_session_ids)
        _append_event(parent, "composite_started", before, parent.state, "all services ready")
        self.repository.save(parent)
        return parent

    def get_session(self, session_id: str) -> PlaySessionRecord:
        return self.refresh_session(session_id)

    def refresh_session(self, session_id: str) -> PlaySessionRecord:
        with _ACTIVE_LOCK:
            active = _ACTIVE.get(session_id)
        if not active:
            stored = self.repository.load(session_id)
            if stored.launch_kind == LaunchKind.COMPOSITE:
                return self._refresh_composite(stored)
            return stored
        process = active.process
        exit_code = process.poll()
        with active.lock:
            record = active.record
            if exit_code is not None and record.state in ACTIVE_SESSION_STATES:
                before = record.state
                record.exit_code = int(exit_code)
                record.state = "stopped" if exit_code == 0 else "failed"
                record.stop_reason = "process_exit"
                _append_event(record, "session_exited", before, record.state, "process exited", exit_code=exit_code)
                self.repository.save(record)
                with _ACTIVE_LOCK:
                    _ACTIVE.pop(session_id, None)
            else:
                self.repository.save(record)
            return record

    def stop_session(self, session_id: str, *, reason: str = "user_stop", terminal_state: str = "stopped") -> PlaySessionRecord:
        with _ACTIVE_LOCK:
            active = _ACTIVE.get(session_id)
        if not active:
            record = self.repository.load(session_id)
            if record.launch_kind == LaunchKind.COMPOSITE:
                for child_id in record.child_session_ids:
                    child = self.refresh_session(child_id)
                    if child.state in ACTIVE_SESSION_STATES:
                        self.stop_session(child_id, reason=reason, terminal_state=terminal_state)
                before = record.state
                record.state = terminal_state
                record.stop_reason = reason
                record.services = self._composite_service_statuses(record.child_session_ids)
                _append_event(record, "composite_stopped", before, record.state, "all composite child services stopped")
                self.repository.save(record)
                return record
            if record.state in ACTIVE_SESSION_STATES:
                before = record.state
                record.state = terminal_state
                record.stop_reason = reason
                _append_event(record, "session_stopped", before, record.state, "no active process handle")
                self.repository.save(record)
            return record
        _terminate_process_tree(active.process)
        active.process.wait(timeout=5)
        with active.lock:
            record = active.record
            before = record.state
            record.exit_code = active.process.returncode
            record.state = terminal_state
            record.stop_reason = reason
            _append_event(record, "session_stopped", before, terminal_state, "process tree stopped", exit_code=record.exit_code)
            self.repository.save(record)
        with _ACTIVE_LOCK:
            _ACTIVE.pop(session_id, None)
        return record

    def restart_session(self, session_id: str) -> PlaySessionRecord:
        record = self.repository.load(session_id)
        if record.state in ACTIVE_SESSION_STATES:
            self.stop_session(session_id, reason="restart")
        adapter = StructuredLaunchAdapter.model_validate(record.adapter)
        restarted = self.start_session(
            project_id=record.project_id,
            project_root=record.project_root,
            adapter=adapter,
            max_session_seconds=self.limits.max_session_seconds,
            session_id=session_id,
        )
        _append_event(restarted, "session_restarted", record.state, restarted.state, "session restarted")
        self.repository.save(restarted)
        return restarted

    def reap_expired_sessions(self) -> list[PlaySessionRecord]:
        expired: list[PlaySessionRecord] = []
        now = _now()
        for record in self.repository.list_active():
            deadline = _parse_iso(record.deadline_at)
            if deadline and deadline <= now:
                expired.append(self.stop_session(record.session_id, reason="deadline_expired", terminal_state="expired"))
        return expired

    def purge_session(self, session_id: str) -> PlaySessionRecord:
        record = self.repository.load(session_id)
        if record.state in ACTIVE_SESSION_STATES:
            record = self.stop_session(session_id, reason="purge", terminal_state="purged")
        else:
            before = record.state
            record.state = "purged"
            record.stop_reason = "purge"
            _append_event(record, "session_purged", before, "purged", "session purged")
        if record.runtime_dir:
            shutil.rmtree(record.runtime_dir, ignore_errors=True)
        self.repository.save(record)
        return record

    def wait_for_terminal(self, session_id: str, timeout_seconds: float = 5.0) -> PlaySessionRecord:
        deadline = time.monotonic() + timeout_seconds
        record = self.refresh_session(session_id)
        while record.state in ACTIVE_SESSION_STATES and time.monotonic() < deadline:
            time.sleep(0.05)
            record = self.refresh_session(session_id)
        return record

    def _assert_can_start(self, project_id: str, adapter: StructuredLaunchAdapter) -> None:
        if adapter.status != "ready":
            raise PlaySessionError("adapter_not_ready")
        if adapter.kind not in {LaunchKind.STATIC_WEB, LaunchKind.PYTHON_SCRIPT}:
            raise PlaySessionError("launch_kind_deferred_to_later_package")
        if not adapter.port.loopback_only or adapter.port.expose_directly:
            raise PlaySessionError("port_contract_not_loopback_only")
        active_records = [record for record in self.repository.list_active() if record.launch_kind != LaunchKind.COMPOSITE]
        active = [record for record in active_records if record.project_id == project_id]
        if len(active) >= self.limits.max_sessions_per_project:
            raise PlaySessionError("project_session_limit_reached")
        if len(active_records) >= self.limits.max_total_sessions:
            raise PlaySessionError("total_session_limit_reached")

    def _wait_for_readiness(self, session_id: str, timeout_seconds: float) -> tuple[bool, str]:
        deadline = time.monotonic() + timeout_seconds
        time.sleep(min(0.1, max(timeout_seconds / 2, 0.0)))
        while time.monotonic() < deadline:
            record = self.refresh_session(session_id)
            if record.state in TERMINAL_SESSION_STATES:
                return False, "service_exit_before_ready"
            if record.port and self._port_accepts_connection(record.port):
                record.readiness_status = "ready"
                self.repository.save(record)
                return True, ""
            time.sleep(0.05)
        record = self.refresh_session(session_id)
        if record.state in ACTIVE_SESSION_STATES:
            record.readiness_status = "timeout"
            self.repository.save(record)
        return False, "readiness_timeout"

    def _port_accepts_connection(self, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.05)
            try:
                return sock.connect_ex(("127.0.0.1", port)) == 0
            except OSError:
                return False

    def _composite_service_statuses(self, child_session_ids: list[str]) -> list[PlayCompositeServiceStatus]:
        statuses: list[PlayCompositeServiceStatus] = []
        for child_id in child_session_ids:
            with _ACTIVE_LOCK:
                has_active_handle = child_id in _ACTIVE
            child = self.refresh_session(child_id) if has_active_handle else self.repository.load(child_id)
            statuses.append(
                PlayCompositeServiceStatus(
                    service_id=child.service_id or child.launch_profile_id,
                    session_id=child.session_id,
                    state=child.state,
                    port=child.port,
                    readiness_status=child.readiness_status or ("ready" if child.state in ACTIVE_SESSION_STATES else child.state),
                )
            )
        return statuses

    def _refresh_composite(self, record: PlaySessionRecord) -> PlaySessionRecord:
        services = self._composite_service_statuses(record.child_session_ids)
        record.services = services
        if record.state in ACTIVE_SESSION_STATES and any(service.state == "failed" for service in services):
            for service in services:
                child = self.repository.load(service.session_id)
                if child.state in ACTIVE_SESSION_STATES:
                    self.stop_session(child.session_id, reason="composite_child_failed")
            before = record.state
            record.state = "failed"
            record.stop_reason = "composite_child_failed"
            record.services = self._composite_service_statuses(record.child_session_ids)
            _append_event(record, "composite_failed", before, record.state, "child service failed")
        self.repository.save(record)
        return record

    def _resolve_workdir(self, project_root: Path, adapter: StructuredLaunchAdapter) -> Path:
        decision = decide_workspace_access(
            project_root=project_root,
            relative_path=adapter.working_directory,
            permission=WorkspacePermission.READ,
            allow_root=True,
        )
        if not decision.allowed:
            raise PlaySessionError("working_directory_unsafe")
        path = Path(decision.resolved_path)
        if not path.exists() or not path.is_dir():
            raise PlaySessionError("working_directory_missing")
        return path

    def _build_argv(self, project_root: Path, workdir: Path, adapter: StructuredLaunchAdapter) -> tuple[list[str], int]:
        port = _allocate_loopback_port()
        if adapter.kind == LaunchKind.STATIC_WEB:
            entrypoint = adapter.argv[1] if len(adapter.argv) > 1 else ""
            decision = decide_workspace_access(
                project_root=project_root,
                relative_path=entrypoint,
                permission=WorkspacePermission.SERVE,
            )
            if not decision.allowed:
                raise PlaySessionError("static_entrypoint_unsafe")
            return [sys.executable, "-u", "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(workdir)], port
        if adapter.kind == LaunchKind.PYTHON_SCRIPT:
            if len(adapter.argv) < 2:
                raise PlaySessionError("python_entrypoint_missing")
            entrypoint = adapter.argv[1]
            decision = decide_workspace_access(
                project_root=project_root,
                relative_path=entrypoint,
                permission=WorkspacePermission.EXECUTE,
            )
            if not decision.allowed:
                raise PlaySessionError("python_entrypoint_unsafe")
            argv = [str(value).replace("{PORT}", str(port)) for value in adapter.argv]
            if Path(argv[0]).name.lower() in {"python", "python.exe"}:
                argv[0] = sys.executable
            return argv, port
        raise PlaySessionError("launch_kind_deferred_to_later_package")

    def _read_output(self, active: _ActiveProcess) -> None:
        if active.process.stdout is None:
            return
        last_saved = 0.0
        for line in active.process.stdout:
            with active.lock:
                _append_log(active.record, line, self.limits.max_log_bytes_per_session)
                now = time.monotonic()
                if now - last_saved >= 0.2:
                    self.repository.save(active.record)
                    last_saved = now
        with active.lock:
            self.repository.save(active.record)


def reconcile_play_startup_orphans(data_root: str | Path) -> list[PlaySessionRecord]:
    repository = PlaySessionRepository(data_root)
    reconciled: list[PlaySessionRecord] = []
    for record in repository.list_active():
        if record.pid:
            _cleanup_process_id(record.pid)
        before = record.state
        record.state = "failed"
        record.stop_reason = "startup_orphan_reconciled"
        _append_event(record, "startup_orphan_reconciled", before, record.state, "active session had no live supervisor handle")
        repository.save(record)
        reconciled.append(record)
    return reconciled
