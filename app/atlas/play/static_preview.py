from __future__ import annotations

import ipaddress
import json
import mimetypes
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from pydantic import Field

from app.atlas.play.contracts import LaunchKind, StrictContractModel
from app.atlas.play.sessions import ACTIVE_SESSION_STATES, PlaySessionError, PlaySessionRecord, PlaySessionRepository
from app.atlas.play.workspace_policy import WorkspacePermission, decide_workspace_access, normalize_workspace_relative_path


STATIC_PREVIEW_SCHEMA_VERSION = "atlas.play.static_preview.v1"
_ALLOWED_HOSTS = {"testserver", "localhost", "127.0.0.1", "::1"}


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
    def __init__(self, repository: PlaySessionRepository) -> None:
        self.repository = repository

    def path(self, session_id: str) -> Path:
        return self.repository.session_dir(session_id) / "static_preview_observations.json"

    def load(self, session_id: str) -> StaticPreviewObservationRecord:
        path = self.path(session_id)
        if not path.exists():
            return StaticPreviewObservationRecord(session_id=session_id, updated_at=_now_iso())
        return StaticPreviewObservationRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def save(self, record: StaticPreviewObservationRecord) -> None:
        record.updated_at = _now_iso()
        path = self.path(record.session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(f"{path.name}.tmp")
        tmp_path.write_text(json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(path)

    def record_served_path(self, session_id: str, relative_path: str) -> None:
        record = self.load(session_id)
        record.served_paths = list(dict.fromkeys([*record.served_paths, relative_path]))[-500:]
        self.save(record)

    def record_failed_request(self, session_id: str, event: StaticPreviewFailedRequest) -> StaticPreviewObservationRecord:
        record = self.load(session_id)
        event.created_at = event.created_at or _now_iso()
        record.failed_requests = [*record.failed_requests, event][-500:]
        self.save(record)
        return record

    def record_console_event(self, session_id: str, event: StaticPreviewConsoleEvent) -> StaticPreviewObservationRecord:
        record = self.load(session_id)
        event.created_at = event.created_at or _now_iso()
        record.console_events = [*record.console_events, event][-500:]
        self.save(record)
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
