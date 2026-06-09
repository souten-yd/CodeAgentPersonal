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

from app.atlas.play.contracts import LaunchKind, PlayResourceLimits, StrictContractModel
from app.atlas.play.environment import StructuredLaunchAdapter
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


class _ActiveProcess:
    def __init__(self, process: subprocess.Popen[str], record: PlaySessionRecord) -> None:
        self.process = process
        self.record = record
        self.lock = threading.Lock()
        self.reader: threading.Thread | None = None


_ACTIVE: dict[str, _ActiveProcess] = {}
_ACTIVE_LOCK = threading.Lock()


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
    for key in adapter.environment:
        if key not in {"PATH", "PYTHONPATH", "NODE_OPTIONS"}:
            env[key] = os.environ.get(key, "")
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
        path = self.record_path(record.session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")

    def load(self, session_id: str) -> PlaySessionRecord:
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

    def get_session(self, session_id: str) -> PlaySessionRecord:
        return self.refresh_session(session_id)

    def refresh_session(self, session_id: str) -> PlaySessionRecord:
        with _ACTIVE_LOCK:
            active = _ACTIVE.get(session_id)
        if not active:
            return self.repository.load(session_id)
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
        active = [record for record in self.repository.list_active() if record.project_id == project_id]
        if len(active) >= self.limits.max_sessions_per_project:
            raise PlaySessionError("project_session_limit_reached")
        if len(self.repository.list_active()) >= self.limits.max_total_sessions:
            raise PlaySessionError("total_session_limit_reached")

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
