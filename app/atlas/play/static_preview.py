from __future__ import annotations

import ipaddress
import json
import logging
import mimetypes
import os
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
from urllib.parse import urlparse

from pydantic import Field, ValidationError

from app.atlas.play.contracts import LaunchKind, StrictContractModel
from app.atlas.play.sessions import ACTIVE_SESSION_STATES, PlaySessionError, PlaySessionRecord, PlaySessionRepository
from app.atlas.play.workspace_policy import WorkspacePermission, decide_workspace_access, normalize_workspace_relative_path


STATIC_PREVIEW_SCHEMA_VERSION = "atlas.play.static_preview.v1"
_ALLOWED_HOSTS = {"testserver", "localhost", "127.0.0.1", "::1"}
_OBSERVATION_LOCK_STALE_SECONDS = 10.0
_SERVED_PATH_DEBOUNCE_SECONDS = 2.0
_LOGGER = logging.getLogger(__name__)


class StaticPreviewError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class StaticPreviewConsoleEvent(StrictContractModel):
    schema_version: str = STATIC_PREVIEW_SCHEMA_VERSION
    level: str = Field(default="log", max_length=16)
    message: str = Field(default="", max_length=2000)
    source: str = Field(default="", max_length=500)
    created_at: str = ""


class StaticPreviewFailedRequest(StrictContractModel):
    schema_version: str = STATIC_PREVIEW_SCHEMA_VERSION
    url: str = Field(default="", max_length=2000)
    method: str = Field(default="GET", max_length=16)
    status_code: int = 0
    resource_type: str = Field(default="", max_length=64)
    reason: str = Field(default="", max_length=128)
    created_at: str = ""


class StaticPreviewObservationRecord(StrictContractModel):
    schema_version: str = STATIC_PREVIEW_SCHEMA_VERSION
    session_id: str
    served_paths: list[str] = Field(default_factory=list)
    failed_requests: list[StaticPreviewFailedRequest] = Field(default_factory=list)
    console_events: list[StaticPreviewConsoleEvent] = Field(default_factory=list)
    updated_at: str = ""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _host_name(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.startswith("["):
        return text.split("]", 1)[0].strip("[]").lower()
    return text.split(":", 1)[0].lower()


_LOCAL_HOST_SUFFIXES = (".local", ".lan", ".home", ".internal", ".home.arpa")
# Carrier-grade NAT / shared address space (RFC 6598). Tailscale and similar
# mesh VPNs hand phones an address in this range, which ipaddress does NOT
# classify as private, yet it is never publicly routable.
_CGNAT_NETWORK = ipaddress.ip_network("100.64.0.0/10")


def _is_private_ip_host(host: str) -> bool:
    """Loopback / private (RFC1918) / link-local / CGNAT IP literals reachable
    on the user's own LAN or mesh VPN. iPhone access uses the host's LAN IP,
    e.g. 192.168.x.x, or a Tailscale 100.x address."""
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    if ip.version == 4 and ip in _CGNAT_NETWORK:
        return True
    return bool(ip.is_loopback or ip.is_private or ip.is_link_local)


def _is_local_network_hostname(host: str) -> bool:
    """Non-public hostnames that only resolve on the local network.

    A phone reaching a Windows/LAN host by name uses either the bare machine
    name (a single DNS label with no dot, e.g. "DESKTOP-AB12", never a public
    FQDN) or an mDNS / router-local name (``host.local``, ``host.lan`` ...).
    Such names are inherently LAN-scoped, so allowing them keeps mobile access
    working while still rejecting arbitrary public hostnames (DNS rebinding)."""
    if not host:
        return False
    if "." not in host:
        return True
    return any(host == suffix.lstrip(".") or host.endswith(suffix) for suffix in _LOCAL_HOST_SUFFIXES)


def _configured_preview_hosts() -> set[str]:
    """Explicit allow-list extensions from the environment (comma separated).

    Lets a deployment pin its public hostname, e.g. a custom domain or tunnel."""
    raw = os.environ.get("ATLAS_PREVIEW_ALLOWED_HOSTS", "")
    hosts: set[str] = set()
    for part in raw.replace(";", ",").split(","):
        name = _host_name(part)
        if name:
            hosts.add(name)
    return hosts


def _is_allowed_preview_host(host: str) -> bool:
    """Decide whether a request Host / Origin host may reach a Play preview.

    The whole app is intentionally exposed on LAN and on the RunPod proxy
    (CORS allow_origins=["*"]), so the preview must be reachable from a phone
    on the same network or through the RunPod proxy. We still reject arbitrary
    public hostnames (DNS-rebinding protection) by only allowing localhost,
    the user's own private LAN IPs, local network hostnames (bare machine names
    and mDNS/router-local names), the RunPod proxy domain, and any host pinned
    via ATLAS_PREVIEW_ALLOWED_HOSTS."""
    if not host:
        return True
    if host in _ALLOWED_HOSTS or host in _configured_preview_hosts():
        return True
    if _is_private_ip_host(host):
        return True
    if _is_local_network_hostname(host):
        return True
    # RunPod exposes ports as "{pod_id}-{port}.proxy.runpod.net".
    if host == "proxy.runpod.net" or host.endswith(".proxy.runpod.net"):
        return True
    return False


def validate_preview_request_headers(headers: dict[str, str]) -> None:
    host = _host_name(headers.get("host", ""))
    if host and not _is_allowed_preview_host(host):
        raise StaticPreviewError("host_not_allowed")
    for header_name in ("origin", "referer"):
        value = headers.get(header_name, "")
        if not value:
            continue
        parsed = urlparse(value)
        origin_host = _host_name(parsed.netloc)
        # Legitimate preview requests are same-origin with the page the user
        # navigated to, so the Origin/Referer host matches the request Host.
        # Anything else must independently satisfy the host policy.
        same_origin = bool(host) and origin_host == host
        if parsed.scheme not in {"http", "https"} or not (same_origin or _is_allowed_preview_host(origin_host)):
            raise StaticPreviewError(f"{header_name}_not_allowed")


class StaticPreviewObservationStore:
    _thread_locks: dict[str, threading.RLock] = {}
    _thread_locks_guard = threading.Lock()
    _served_path_seen: dict[tuple[str, str], float] = {}
    _served_path_seen_guard = threading.Lock()

    def __init__(self, repository: PlaySessionRepository) -> None:
        self.repository = repository

    def path(self, session_id: str) -> Path:
        return self.repository.session_dir(session_id) / "static_preview_observations.json"

    def load(self, session_id: str) -> StaticPreviewObservationRecord:
        return self._load_best_effort(session_id)

    def _empty_record(self, session_id: str) -> StaticPreviewObservationRecord:
        return StaticPreviewObservationRecord(session_id=session_id, updated_at=_now_iso())

    def _thread_lock(self, session_id: str) -> threading.RLock:
        with self._thread_locks_guard:
            lock = self._thread_locks.get(session_id)
            if lock is None:
                lock = threading.RLock()
                self._thread_locks[session_id] = lock
            return lock

    @contextmanager
    def _file_lock(self, session_id: str) -> Iterator[bool]:
        lock_path = self.repository.session_dir(session_id) / "static_preview_observations.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        fd: int | None = None
        acquired = False
        try:
            try:
                fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, f"{os.getpid()} {time.time()}".encode("utf-8"))
                acquired = True
            except FileExistsError:
                try:
                    age = time.time() - lock_path.stat().st_mtime
                    if age > _OBSERVATION_LOCK_STALE_SECONDS:
                        lock_path.unlink(missing_ok=True)
                        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                        os.write(fd, f"{os.getpid()} {time.time()}".encode("utf-8"))
                        acquired = True
                except OSError as exc:
                    _LOGGER.warning("Static preview observation lock unavailable for session %s: %s", session_id, exc)
            except OSError as exc:
                _LOGGER.warning("Static preview observation lock unavailable for session %s: %s", session_id, exc)
            yield acquired
        finally:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
            if acquired:
                try:
                    lock_path.unlink(missing_ok=True)
                except OSError as exc:
                    _LOGGER.warning("Static preview observation lock cleanup failed for session %s: %s", session_id, exc)

    def _load_best_effort(self, session_id: str) -> StaticPreviewObservationRecord:
        path = self.path(session_id)
        try:
            if not path.exists():
                return self._empty_record(session_id)
            payload = json.loads(path.read_text(encoding="utf-8"))
            return StaticPreviewObservationRecord.model_validate(payload)
        except json.JSONDecodeError as exc:
            _LOGGER.warning("Static preview observations corrupt for session %s: %s", session_id, exc)
            self._quarantine_corrupt_file(path)
        except (OSError, ValidationError) as exc:
            _LOGGER.warning("Static preview observations unavailable for session %s: %s", session_id, exc)
            if isinstance(exc, ValidationError):
                self._quarantine_corrupt_file(path)
        return self._empty_record(session_id)

    def _quarantine_corrupt_file(self, path: Path) -> None:
        if not path.exists():
            return
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        target = path.with_name(f"static_preview_observations.corrupt-{timestamp}.json")
        try:
            path.replace(target)
            _LOGGER.warning("Moved corrupt static preview observations to %s", target)
        except OSError as exc:
            _LOGGER.warning("Failed to move corrupt static preview observations %s: %s", path, exc)

    def save(self, record: StaticPreviewObservationRecord) -> None:
        self._save_best_effort(record)

    def _save_best_effort(self, record: StaticPreviewObservationRecord) -> bool:
        record.updated_at = _now_iso()
        path = self.path(record.session_id)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = path.with_name(
                f"{path.stem}.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex}.tmp"
            )
            data = json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2)
            with tmp_path.open("w", encoding="utf-8") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, path)
            self._fsync_parent(path.parent)
            return True
        except OSError as exc:
            _LOGGER.warning("Static preview observation save failed for session %s: %s", record.session_id, exc)
            try:
                if "tmp_path" in locals():
                    tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            return False

    def _fsync_parent(self, path: Path) -> None:
        try:
            fd = os.open(str(path), os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(fd)
        except OSError:
            pass
        finally:
            try:
                os.close(fd)
            except OSError:
                pass

    def _should_skip_served_path_save(self, session_id: str, relative_path: str) -> bool:
        key = (session_id, relative_path)
        now = time.monotonic()
        with self._served_path_seen_guard:
            previous = self._served_path_seen.get(key)
            self._served_path_seen[key] = now
            return previous is not None and (now - previous) < _SERVED_PATH_DEBOUNCE_SECONDS

    def _load_update_save(
        self,
        session_id: str,
        update,
    ) -> StaticPreviewObservationRecord:
        with self._thread_lock(session_id):
            with self._file_lock(session_id) as acquired:
                record = self._load_best_effort(session_id)
                update(record)
                if not acquired:
                    _LOGGER.warning("Static preview observation lock skipped for session %s", session_id)
                    return record
                self._save_best_effort(record)
                return record

    def record_served_path(self, session_id: str, relative_path: str) -> None:
        if self._should_skip_served_path_save(session_id, relative_path):
            return
        try:
            self._load_update_save(
                session_id,
                lambda record: setattr(
                    record,
                    "served_paths",
                    list(dict.fromkeys([*record.served_paths, relative_path]))[-500:],
                ),
            )
        except (OSError, PermissionError, ValidationError, json.JSONDecodeError) as exc:
            _LOGGER.warning("Static preview served-path observation skipped for session %s: %s", session_id, exc)

    def record_failed_request(self, session_id: str, event: StaticPreviewFailedRequest) -> StaticPreviewObservationRecord:
        try:
            return self._load_update_save(
                session_id,
                lambda record: (
                    setattr(event, "created_at", event.created_at or _now_iso()),
                    setattr(record, "failed_requests", [*record.failed_requests, event][-500:]),
                ),
            )
        except (OSError, PermissionError, ValidationError, json.JSONDecodeError) as exc:
            _LOGGER.warning("Static preview failed-request observation skipped for session %s: %s", session_id, exc)
            record = self._empty_record(session_id)
            event.created_at = event.created_at or _now_iso()
            record.failed_requests = [event]
            return record

    def record_console_event(self, session_id: str, event: StaticPreviewConsoleEvent) -> StaticPreviewObservationRecord:
        try:
            return self._load_update_save(
                session_id,
                lambda record: (
                    setattr(event, "created_at", event.created_at or _now_iso()),
                    setattr(record, "console_events", [*record.console_events, event][-500:]),
                ),
            )
        except (OSError, PermissionError, ValidationError, json.JSONDecodeError) as exc:
            _LOGGER.warning("Static preview console observation skipped for session %s: %s", session_id, exc)
            record = self._empty_record(session_id)
            event.created_at = event.created_at or _now_iso()
            record.console_events = [event]
            return record


class StaticPreviewService:
    def __init__(self, data_root: str | Path) -> None:
        self.repository = PlaySessionRepository(data_root)
        self.observations = StaticPreviewObservationStore(self.repository)

    def get_record(self, session_id: str) -> PlaySessionRecord:
        try:
            record = self.repository.load(session_id)
        except PlaySessionError as exc:
            raise StaticPreviewError("session_not_found") from exc
        if record.launch_kind != LaunchKind.STATIC_WEB:
            raise StaticPreviewError("session_not_static_web")
        if record.state not in ACTIVE_SESSION_STATES:
            raise StaticPreviewError("session_not_active")
        return record

    def resolve_static_file(self, session_id: str, requested_path: str) -> tuple[Path, str, str]:
        record = self.get_record(session_id)
        project_root = Path(record.project_root).resolve()
        static_root = self._static_root(record)
        try:
            relative_path = normalize_workspace_relative_path(requested_path or "index.html")
        except ValueError as exc:
            raise StaticPreviewError("static_path_unsafe") from exc
        if relative_path == ".":
            relative_path = "index.html"
        file_path = self._resolve_under_static_root(project_root, static_root, relative_path)
        if file_path.is_dir():
            file_path = file_path / "index.html"
            relative_path = f"{relative_path.rstrip('/')}/index.html".lstrip("./")
        if not file_path.exists() or not file_path.is_file():
            fallback = static_root / "index.html"
            if "." not in Path(relative_path).name and fallback.exists():
                return fallback, "index.html", self._content_type(fallback)
            self.observations.record_failed_request(
                session_id,
                StaticPreviewFailedRequest(url=relative_path, status_code=404, reason="static_file_missing"),
            )
            raise StaticPreviewError("static_file_missing")
        safe_relative = file_path.relative_to(static_root).as_posix()
        self.observations.record_served_path(session_id, safe_relative)
        return file_path, safe_relative, self._content_type(file_path)

    def record_console_event(self, session_id: str, event: StaticPreviewConsoleEvent) -> StaticPreviewObservationRecord:
        self.get_record(session_id)
        return self.observations.record_console_event(session_id, event)

    def record_failed_request(self, session_id: str, event: StaticPreviewFailedRequest) -> StaticPreviewObservationRecord:
        self.get_record(session_id)
        return self.observations.record_failed_request(session_id, event)

    def observation_record(self, session_id: str) -> StaticPreviewObservationRecord:
        self.get_record(session_id)
        return self.observations.load(session_id)

    def _static_root(self, record: PlaySessionRecord) -> Path:
        project_root = Path(record.project_root).resolve()
        decision = decide_workspace_access(
            project_root=project_root,
            relative_path=record.working_directory or ".",
            permission=WorkspacePermission.SERVE,
            allow_root=True,
        )
        if not decision.allowed:
            raise StaticPreviewError("static_root_unsafe")
        static_root = Path(decision.resolved_path).resolve()
        if not static_root.is_dir():
            raise StaticPreviewError("static_root_missing")
        return static_root

    def _resolve_under_static_root(self, project_root: Path, static_root: Path, relative_path: str) -> Path:
        joined_relative = (Path(static_root).relative_to(project_root) / relative_path).as_posix()
        decision = decide_workspace_access(
            project_root=project_root,
            relative_path=joined_relative,
            permission=WorkspacePermission.SERVE,
        )
        if not decision.allowed:
            raise StaticPreviewError("static_path_unsafe")
        target = Path(decision.resolved_path).resolve()
        if os.path.commonpath([str(static_root), str(target)]) != str(static_root):
            raise StaticPreviewError("static_path_escape")
        return target

    def _content_type(self, path: Path) -> str:
        return mimetypes.guess_type(path.name)[0] or "application/octet-stream"
