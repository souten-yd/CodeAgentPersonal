from __future__ import annotations

import hmac
import json
import shutil
import stat
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.atlas.play.sessions import PlaySessionError, PlaySessionManager
from app.portal.data_lifecycle import PortalDataLifecycleService
from app.portal.paths import PortalPathLayout


PORTAL_RECOVERY_SCHEMA_VERSION = "portal.recovery.v1"
DEFAULT_RECOVERY_RETENTION_SECONDS = 3600


class PortalRecoveryError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _token_hash(token: str) -> str:
    h = __import__("hashlib").sha256()
    h.update(token.encode("utf-8"))
    return h.hexdigest()


class PortalRecoveryService:
    def __init__(self, data_root: str | Path, *, retention_seconds: int = DEFAULT_RECOVERY_RETENTION_SECONDS) -> None:
        self.data_root = Path(data_root).expanduser().resolve()
        self.paths = PortalPathLayout(self.data_root)
        self.play = PlaySessionManager(self.data_root)
        self.data = PortalDataLifecycleService(self.data_root)
        self.retention_seconds = max(60, int(retention_seconds))

    def initialize_runtime(self, runtime: dict) -> tuple[dict, str]:
        token = f"portal-rt-{uuid.uuid4().hex}"
        now = _now()
        runtime.update(
            {
                "recovery_schema_version": PORTAL_RECOVERY_SCHEMA_VERSION,
                "reconnect_token_hash": _token_hash(token),
                "recovery_state": "running",
                "last_heartbeat_at": _iso(now),
                "recovery_expires_at": "",
                "diagnostics": [],
            }
        )
        self.append_event(runtime, "portal_run_started", "running", "running", "portal run recovery record created")
        self.save_runtime(runtime["play_session_id"], runtime)
        return runtime, token

    def heartbeat(self, play_session_id: str, reconnect_token: str) -> dict:
        runtime = self._load_and_validate(play_session_id, reconnect_token)
        self._raise_if_expired(runtime)
        before = runtime.get("recovery_state", "")
        runtime["last_heartbeat_at"] = _iso(_now())
        runtime["recovery_state"] = "running"
        self.append_event(runtime, "heartbeat", before, "running", "portal heartbeat accepted")
        self.save_runtime(play_session_id, runtime)
        return {"schema_version": PORTAL_RECOVERY_SCHEMA_VERSION, "status": "heartbeat", "runtime": self.public_runtime(runtime)}

    def mark_disconnected(self, play_session_id: str, reconnect_token: str) -> dict:
        runtime = self._load_and_validate(play_session_id, reconnect_token)
        if runtime.get("recovery_state") == "recoverable":
            return {"schema_version": PORTAL_RECOVERY_SCHEMA_VERSION, "status": "recoverable", "runtime": self.public_runtime(runtime)}
        try:
            self.play.stop_session(play_session_id, reason="browser_disconnect")
        except PlaySessionError:
            pass
        before = runtime.get("recovery_state", "")
        runtime["status"] = "recoverable"
        runtime["recovery_state"] = "recoverable"
        runtime["recovery_expires_at"] = _iso(_now() + timedelta(seconds=self.retention_seconds))
        self.append_event(runtime, "browser_disconnected", before, "recoverable", "session retained for resume/save/discard")
        self.save_runtime(play_session_id, runtime)
        return {"schema_version": PORTAL_RECOVERY_SCHEMA_VERSION, "status": "recoverable", "runtime": self.public_runtime(runtime)}

    def resume(self, play_session_id: str, reconnect_token: str) -> dict:
        runtime = self._load_and_validate(play_session_id, reconnect_token)
        self._raise_if_expired(runtime)
        before = runtime.get("recovery_state", "")
        if runtime.get("recovery_state") == "recoverable":
            try:
                self.play.restart_session(play_session_id)
            except PlaySessionError as exc:
                runtime.setdefault("diagnostics", []).append(f"resume_restart_failed:{exc.code}")
        runtime["status"] = "running"
        runtime["recovery_state"] = "running"
        runtime["recovery_expires_at"] = ""
        runtime["last_heartbeat_at"] = _iso(_now())
        self.append_event(runtime, "resumed", before, "running", "portal recovery resumed")
        self.save_runtime(play_session_id, runtime)
        return {"schema_version": PORTAL_RECOVERY_SCHEMA_VERSION, "status": "resumed", "runtime": self.public_runtime(runtime)}

    def expire_recoveries(self, *, now: datetime | None = None) -> list[dict]:
        current = now or _now()
        expired: list[dict] = []
        for play_session_id, runtime in self.iter_runtime_records():
            expires_at = _parse_iso(runtime.get("recovery_expires_at"))
            if runtime.get("recovery_state") != "recoverable" or not expires_at or expires_at > current:
                continue
            expired.append(self._expire_runtime(play_session_id, runtime, "recovery_expired"))
        return expired

    def reconcile_startup(self) -> list[dict]:
        reconciled: list[dict] = []
        for play_session_id, runtime in self.iter_runtime_records():
            if runtime.get("data_decision") not in {"pending", "ephemeral_default_discard"}:
                continue
            if runtime.get("recovery_state") in {"recoverable", "expired"}:
                continue
            before = runtime.get("recovery_state", "")
            runtime["status"] = "recoverable"
            runtime["recovery_state"] = "recoverable"
            runtime["recovery_expires_at"] = _iso(_now() + timedelta(seconds=self.retention_seconds))
            self.append_event(runtime, "startup_reconciled", before, "recoverable", "server restart retained session data")
            self.save_runtime(play_session_id, runtime)
            reconciled.append(self.public_runtime(runtime))
        reconciled.extend(self.expire_recoveries())
        return reconciled

    def iter_runtime_records(self) -> list[tuple[str, dict]]:
        root = self.data_root / "portal" / "recovery"
        if not root.exists():
            return []
        records: list[tuple[str, dict]] = []
        for path in sorted(root.glob("*/portal_run.json")):
            try:
                records.append((path.parent.name, json.loads(path.read_text(encoding="utf-8"))))
            except (OSError, json.JSONDecodeError):
                continue
        return records

    def save_runtime(self, play_session_id: str, runtime: dict) -> None:
        recovery = self.paths.recovery_root(play_session_id)
        recovery.mkdir(parents=True, exist_ok=True)
        (recovery / "portal_run.json").write_text(json.dumps(runtime, ensure_ascii=False, indent=2), encoding="utf-8")

    def public_runtime(self, runtime: dict) -> dict:
        return {key: value for key, value in runtime.items() if key != "reconnect_token_hash"}

    def append_event(self, runtime: dict, event_type: str, before: str, after: str, message: str) -> None:
        runtime.setdefault("events", []).append(
            {
                "event_type": event_type,
                "before": before,
                "after": after,
                "message": message,
                "at": _iso(_now()),
            }
        )

    def _load_and_validate(self, play_session_id: str, reconnect_token: str) -> dict:
        path = self.paths.recovery_root(play_session_id) / "portal_run.json"
        if not path.exists():
            raise PortalRecoveryError("portal_runtime_not_found")
        runtime = json.loads(path.read_text(encoding="utf-8"))
        expected = str(runtime.get("reconnect_token_hash") or "")
        if not expected or not hmac.compare_digest(expected, _token_hash(reconnect_token)):
            raise PortalRecoveryError("reconnect_token_invalid")
        return runtime

    def _raise_if_expired(self, runtime: dict) -> None:
        expires_at = _parse_iso(runtime.get("recovery_expires_at"))
        if runtime.get("recovery_state") == "recoverable" and expires_at and expires_at <= _now():
            raise PortalRecoveryError("recovery_expired")

    def _expire_runtime(self, play_session_id: str, runtime: dict, reason: str) -> dict:
        try:
            self.play.stop_session(play_session_id, reason=reason, terminal_state="expired")
        except PlaySessionError:
            pass
        self._rmtree(runtime.get("application_root", ""))
        self.data.discard_session_data(runtime["portal_session_id"])
        before = runtime.get("recovery_state", "")
        runtime["status"] = "expired"
        runtime["recovery_state"] = "expired"
        runtime["data_decision"] = "expired_discard"
        self.append_event(runtime, reason, before, "expired", "expired recovery purged")
        self.save_runtime(play_session_id, runtime)
        return self.public_runtime(runtime)

    def _rmtree(self, path: str | Path) -> None:
        if not path:
            return
        target = Path(path)
        if not target.exists():
            return

        def onerror(_func, failed_path, _exc_info):
            try:
                Path(failed_path).chmod(stat.S_IWRITE)
                Path(failed_path).unlink()
            except OSError:
                pass

        shutil.rmtree(target, ignore_errors=False, onerror=onerror)


def reconcile_portal_startup_recovery(data_root: str | Path) -> list[dict]:
    return PortalRecoveryService(data_root).reconcile_startup()
