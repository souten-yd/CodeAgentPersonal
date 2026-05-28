"""Runner that prepares an autonomous loop session from a confirmed envelope.

This module is the bridge between a persisted ``pre_authorized_*_envelope``
manifest and the existing autopilot routes (``multi_item_autopilot`` etc.).
It does not execute commands or apply patches itself. Its responsibility is:

1. Read the latest confirmed envelope manifest under
   ``<data_root>/atlas/pre_authorized_envelopes/``.
2. Validate that the envelope is ``status="active"`` and pre-authorises the
   requested loop action (autonomous code generation or self-improvement).
3. Enforce bounds (max_actions_per_loop, max_files_changed, command allowlist,
   blocked paths, max_runtime_seconds, max_risk_level).
4. Emit a ``session_record`` dict that downstream autopilot routes consume.

The session record carries an explicit ``permit_autonomous_loop_execution``
flag derived from the envelope. Autopilot routes still own the actual
execution; they can read this record to decide whether to skip per-action
human approvals inside the bounded scope.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.atlas.pre_authorized_bounded_dev_envelope import (
    ENVELOPE_BOUNDED_DEV,
    ENVELOPE_NONE,
    ENVELOPE_SELF_IMPROVEMENT,
    SCHEMA_VERSION as ENVELOPE_SCHEMA_VERSION,
)

SCHEMA_VERSION = "atlas.autonomous_loop_envelope_runner.v1"
TRACK_PR = "POST-SCALE-160-CLAUDE-CHAT-COMPLETE-AUTOMATION-PROFILE"

REQUEST_KIND_DEV = "autonomous_dev_loop"
REQUEST_KIND_SELF_IMPROVEMENT = "autonomous_self_improvement_loop"

_ALLOWED_REQUEST_KINDS = frozenset({REQUEST_KIND_DEV, REQUEST_KIND_SELF_IMPROVEMENT})

_ENVELOPE_REQUEST_COMPATIBILITY: dict[str, set[str]] = {
    ENVELOPE_BOUNDED_DEV: {REQUEST_KIND_DEV},
    ENVELOPE_SELF_IMPROVEMENT: {
        REQUEST_KIND_DEV,
        REQUEST_KIND_SELF_IMPROVEMENT,
    },
}


def prepare_autonomous_loop_session(
    *,
    data_root: str | Path,
    request_kind: str,
    loop_goal: str,
    requested_actions: int,
    requested_files: int,
    requested_runtime_seconds: int,
    requested_risk_level: str,
    requested_paths: list[str] | None = None,
    requested_commands: list[str] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Validate the request against the latest envelope and emit a session record.

    Returns a dict with ``status`` (``"active"`` or ``"blocked"``) plus a
    ``blocking_reasons`` list. The session is only safe to consume when status
    is ``"active"``.
    """

    root = Path(data_root).expanduser().resolve()
    blocked: list[str] = []

    if request_kind not in _ALLOWED_REQUEST_KINDS:
        blocked.append("request_kind_not_allowed")
        request_kind = REQUEST_KIND_DEV

    envelope = _load_latest_envelope(root)
    if envelope is None:
        blocked.append("envelope_manifest_missing")
        envelope = {}

    if envelope and envelope.get("status") != "active":
        blocked.append("envelope_not_active")
    if envelope and envelope.get("schema_version") != ENVELOPE_SCHEMA_VERSION:
        blocked.append("envelope_schema_unsupported")

    envelope_id = str(envelope.get("envelope_id") or ENVELOPE_NONE)
    compatible_kinds = _ENVELOPE_REQUEST_COMPATIBILITY.get(envelope_id, set())
    if envelope and request_kind not in compatible_kinds:
        blocked.append("envelope_does_not_authorize_request_kind")

    bounds = envelope.get("bounds") if isinstance(envelope, dict) else {}
    bounds = bounds if isinstance(bounds, dict) else {}

    blocked.extend(
        _enforce_bounds(
            bounds=bounds,
            requested_actions=requested_actions,
            requested_files=requested_files,
            requested_runtime_seconds=requested_runtime_seconds,
            requested_risk_level=requested_risk_level,
            requested_paths=requested_paths or [],
            requested_commands=requested_commands or [],
        )
    )

    permit = bool(envelope.get("autonomous_loop_execution_enabled")) and not blocked
    status = "active" if permit else "blocked"

    session_record = {
        "schema_version": SCHEMA_VERSION,
        "track_pr": TRACK_PR,
        "session_id": _session_id(),
        "created_at": created_at or _utc_now(),
        "status": status,
        "blocking_reasons": sorted(set(blocked)),
        "request_kind": request_kind,
        "loop_goal": loop_goal,
        "envelope_id": envelope_id,
        "envelope_safety_profile_id": envelope.get("safety_profile_id") or "",
        "bounds": {
            "max_actions_per_loop": int(bounds.get("max_actions_per_loop") or 0),
            "max_files_changed": int(bounds.get("max_files_changed") or 0),
            "max_runtime_seconds": int(bounds.get("max_runtime_seconds") or 0),
            "max_risk_level": str(bounds.get("max_risk_level") or "low"),
            "allowed_paths": list(bounds.get("allowed_paths") or []),
            "blocked_paths": list(bounds.get("blocked_paths") or []),
            "command_allowlist": list(bounds.get("command_allowlist") or []),
        },
        "requested": {
            "actions": int(requested_actions),
            "files": int(requested_files),
            "runtime_seconds": int(requested_runtime_seconds),
            "risk_level": str(requested_risk_level or "low"),
            "paths": list(requested_paths or []),
            "commands": list(requested_commands or []),
        },
        "permit_autonomous_loop_execution": permit,
        "draft_pr_only": bool(envelope.get("draft_pr_only", True)),
        "candidate_workspace_required": bool(
            envelope.get("candidate_workspace_required", True)
        ),
        "backend_authoritative": True,
    }
    return session_record


def _enforce_bounds(
    *,
    bounds: dict[str, Any],
    requested_actions: int,
    requested_files: int,
    requested_runtime_seconds: int,
    requested_risk_level: str,
    requested_paths: list[str],
    requested_commands: list[str],
) -> list[str]:
    """Compare the request against the bound recipe."""

    blocked: list[str] = []
    risk_order = {"low": 0, "medium": 1, "high": 2}

    max_actions = int(bounds.get("max_actions_per_loop") or 0)
    if max_actions <= 0:
        blocked.append("envelope_bounds_missing_max_actions")
    elif requested_actions > max_actions:
        blocked.append("requested_actions_exceed_envelope_bound")

    max_files = int(bounds.get("max_files_changed") or 0)
    if max_files <= 0:
        blocked.append("envelope_bounds_missing_max_files")
    elif requested_files > max_files:
        blocked.append("requested_files_exceed_envelope_bound")

    max_runtime = int(bounds.get("max_runtime_seconds") or 0)
    if max_runtime <= 0:
        blocked.append("envelope_bounds_missing_max_runtime")
    elif requested_runtime_seconds > max_runtime:
        blocked.append("requested_runtime_exceeds_envelope_bound")

    requested_rank = risk_order.get(requested_risk_level, 99)
    max_risk_rank = risk_order.get(str(bounds.get("max_risk_level") or "low"), 0)
    if requested_rank > max_risk_rank:
        blocked.append("requested_risk_level_exceeds_envelope_bound")

    allowed_paths = list(bounds.get("allowed_paths") or [])
    blocked_paths = list(bounds.get("blocked_paths") or [])
    for path in requested_paths:
        if blocked_paths and any(path.startswith(item) for item in blocked_paths):
            blocked.append("requested_path_blocked_by_envelope")
            break
    for path in requested_paths:
        if allowed_paths and not any(path.startswith(item) for item in allowed_paths):
            blocked.append("requested_path_outside_envelope_allowlist")
            break

    command_allowlist = list(bounds.get("command_allowlist") or [])
    for command in requested_commands:
        if command_allowlist and not any(
            command.startswith(item) for item in command_allowlist
        ):
            blocked.append("requested_command_outside_envelope_allowlist")
            break

    return blocked


def _load_latest_envelope(data_root: Path) -> dict[str, Any] | None:
    envelope_dir = data_root / "atlas" / "pre_authorized_envelopes"
    if not envelope_dir.is_dir():
        return None
    files = [p for p in envelope_dir.iterdir() if p.is_file() and p.suffix == ".json"]
    if not files:
        return None
    files.sort(key=lambda path: path.stat().st_mtime)
    latest = files[-1]
    try:
        return json.loads(latest.read_text(encoding="utf-8"))
    except (ValueError, FileNotFoundError, json.JSONDecodeError):
        return None


def _session_id() -> str:
    return f"autonomous_loop_envelope_session_{uuid.uuid4().hex[:12]}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
