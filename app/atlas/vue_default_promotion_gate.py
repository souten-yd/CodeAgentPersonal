from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.atlas.fully_autonomous_code_agent_milestone import (
    RUNTIME_LEVEL as FULLY_AUTONOMOUS_RUNTIME_LEVEL,
    SCHEMA_VERSION as FULLY_AUTONOMOUS_SCHEMA_VERSION,
    TRACK_PR as FULLY_AUTONOMOUS_TRACK,
    validate_fully_autonomous_code_agent_milestone,
)

SCHEMA_VERSION = "atlas.vue_default_promotion_gate.v1"
TRACK_PR = "POST-SCALE-160-VUE-DEFAULT-PROMOTION-GATE"
NEXT_REQUIRED_PR = "POST-SCALE-160-VUE-DEFAULT-PROMOTION-APPLY"
REQUIRED_CONFIRMATION_TEXT = "PREPARE VUE DEFAULT PROMOTION GATE"
_REQUIRED_FALSE_FLAGS = (
    "default_route_changed",
    "root_redirect_enabled",
    "ui_html_redirect_enabled",
    "fallback_bypass_enabled",
    "raw_source_serving_enabled",
    "server_startup_build_enabled",
    "vue_authoritative",
    "vue_execution_controls_enabled",
    "stable_runtime_mutation_enabled",
    "direct_merge_enabled",
    "remote_git_push_enabled",
    "self_apply_enabled",
    "self_modification_enabled",
)


def create_vue_default_promotion_gate(
    *,
    fully_autonomous_milestone_path: str | Path,
    data_root: str | Path,
    current_default_route: str = "/",
    candidate_default_route: str = "/atlas-next/",
    legacy_ui_route: str = "/ui/",
    dist_artifact_path: str = "web/atlas-next/dist",
    smoke_evidence_refs: list[str] | None = None,
    rollback_evidence_refs: list[str] | None = None,
    valid_dist_present: bool = False,
    route_smoke_passed: bool = False,
    legacy_route_available: bool = False,
    fail_closed_verified: bool = False,
    rollback_plan_ready: bool = False,
    strict_gate_approved: bool = False,
    confirmation_token_present: bool = False,
    confirmation_text: str = "",
    approval_status: str = "missing",
    explicit_decision: str = "unknown",
    reviewer: str = "atlas",
    created_at: str | None = None,
) -> dict[str, Any]:
    created = created_at or _utc_now()
    root = Path(data_root).expanduser().resolve()
    milestone_path = Path(fully_autonomous_milestone_path).expanduser().resolve()
    blocked: list[str] = []
    try:
        _ensure_under(root, milestone_path, "fully_autonomous_milestone_outside_data_root")
    except ValueError as exc:
        blocked.append(str(exc))

    milestone = _read_milestone(milestone_path=milestone_path, blocked=blocked)
    blocked.extend(_validate_milestone_for_vue_gate(milestone))
    smoke_refs = _safe_refs_or_block(smoke_evidence_refs or [], "smoke_evidence_refs", blocked)
    rollback_refs = _safe_refs_or_block(rollback_evidence_refs or [], "rollback_evidence_refs", blocked)
    try:
        dist_ref = _safe_ref(dist_artifact_path, allow_plain=True)
    except ValueError:
        dist_ref = str(dist_artifact_path)
        blocked.append("dist_artifact_path_invalid")
    if current_default_route not in {"/", "ui.html", "/ui/"}:
        blocked.append("current_default_route_unexpected")
    if candidate_default_route.rstrip("/") != "/atlas-next":
        blocked.append("candidate_default_route_must_be_atlas_next")
    if legacy_ui_route.rstrip("/") not in {"/ui", "ui.html"}:
        blocked.append("legacy_ui_route_required")
    if not smoke_refs:
        blocked.append("smoke_evidence_refs_required")
    if not rollback_refs:
        blocked.append("rollback_evidence_refs_required")
    if not valid_dist_present:
        blocked.append("valid_dist_required")
    if not route_smoke_passed:
        blocked.append("route_smoke_required")
    if not legacy_route_available:
        blocked.append("legacy_route_required")
    if not fail_closed_verified:
        blocked.append("fail_closed_verification_required")
    if not rollback_plan_ready:
        blocked.append("rollback_plan_required")
    if not strict_gate_approved:
        blocked.append("strict_gate_approval_required")
    if not confirmation_token_present:
        blocked.append("confirmation_token_required")
    if confirmation_text != REQUIRED_CONFIRMATION_TEXT:
        blocked.append("confirmation_text_mismatch")
    if approval_status != "approved" or explicit_decision != "approve":
        blocked.append("explicit_human_approval_required")

    ready = not blocked
    gate = {
        "schema_version": SCHEMA_VERSION,
        "gate_id": _gate_id(created),
        "created_at": created,
        "track_pr": TRACK_PR,
        "next_required_pr": NEXT_REQUIRED_PR,
        "status": "ready" if ready else "blocked",
        "blocking_reasons": list(dict.fromkeys(blocked)),
        "runtime_level": FULLY_AUTONOMOUS_RUNTIME_LEVEL,
        "backend_authoritative": True,
        "reviewer": reviewer,
        "fully_autonomous_milestone_path": str(milestone_path),
        "fully_autonomous_schema_version": str(milestone.get("schema_version", "")),
        "fully_autonomous_track_pr": str(milestone.get("track_pr", "")),
        "fully_autonomous_ready": milestone.get("fully_autonomous_code_agent_ready") is True,
        "current_default_route": current_default_route,
        "candidate_default_route": candidate_default_route,
        "legacy_ui_route": legacy_ui_route,
        "dist_artifact_path": dist_ref,
        "smoke_evidence_refs": smoke_refs if ready else [],
        "rollback_evidence_refs": rollback_refs if ready else [],
        "vue_default_promotion_gate_enabled": ready,
        "vue_default_promotion_ready": ready,
        "valid_dist_present": bool(valid_dist_present),
        "route_smoke_passed": bool(route_smoke_passed),
        "legacy_route_available": bool(legacy_route_available),
        "fail_closed_verified": bool(fail_closed_verified),
        "rollback_plan_ready": bool(rollback_plan_ready),
        "separate_apply_pr_required": True,
        "backend_remains_authoritative": True,
        "default_route_changed": False,
        "root_redirect_enabled": False,
        "ui_html_redirect_enabled": False,
        "fallback_bypass_enabled": False,
        "raw_source_serving_enabled": False,
        "server_startup_build_enabled": False,
        "vue_authoritative": False,
        "vue_execution_controls_enabled": False,
        "stable_runtime_mutation_enabled": False,
        "direct_merge_enabled": False,
        "remote_git_push_enabled": False,
        "self_apply_enabled": False,
        "self_modification_enabled": False,
    }
    return validate_vue_default_promotion_gate(gate)


def validate_vue_default_promotion_gate(gate: dict[str, Any]) -> dict[str, Any]:
    required = [
        "schema_version",
        "track_pr",
        "next_required_pr",
        "status",
        "blocking_reasons",
        "runtime_level",
        "backend_authoritative",
        "fully_autonomous_schema_version",
        "fully_autonomous_track_pr",
        "fully_autonomous_ready",
        "current_default_route",
        "candidate_default_route",
        "legacy_ui_route",
        "dist_artifact_path",
        "smoke_evidence_refs",
        "rollback_evidence_refs",
        "vue_default_promotion_gate_enabled",
        "vue_default_promotion_ready",
        "valid_dist_present",
        "route_smoke_passed",
        "legacy_route_available",
        "fail_closed_verified",
        "rollback_plan_ready",
        "separate_apply_pr_required",
        "backend_remains_authoritative",
        *_REQUIRED_FALSE_FLAGS,
    ]
    missing = [field for field in required if field not in gate]
    if missing:
        raise ValueError(f"missing_required_fields:{','.join(missing)}")
    ready = gate.get("status") == "ready"
    invariants = {
        "schema_version": gate.get("schema_version") == SCHEMA_VERSION,
        "track_pr": gate.get("track_pr") == TRACK_PR,
        "next_required_pr": gate.get("next_required_pr") == NEXT_REQUIRED_PR,
        "status": gate.get("status") in {"ready", "blocked"},
        "blocking_reasons": ready or bool(gate.get("blocking_reasons")),
        "runtime_level": gate.get("runtime_level") == FULLY_AUTONOMOUS_RUNTIME_LEVEL,
        "backend_authoritative": gate.get("backend_authoritative") is True,
        "fully_autonomous_schema_version": (not ready) or gate.get("fully_autonomous_schema_version") == FULLY_AUTONOMOUS_SCHEMA_VERSION,
        "fully_autonomous_track_pr": (not ready) or gate.get("fully_autonomous_track_pr") == FULLY_AUTONOMOUS_TRACK,
        "fully_autonomous_ready": (not ready) or gate.get("fully_autonomous_ready") is True,
        "candidate_default_route": str(gate.get("candidate_default_route", "")).rstrip("/") == "/atlas-next",
        "legacy_ui_route": str(gate.get("legacy_ui_route", "")).rstrip("/") in {"/ui", "ui.html"},
        "smoke_evidence_refs": (not ready) or bool(gate.get("smoke_evidence_refs")),
        "rollback_evidence_refs": (not ready) or bool(gate.get("rollback_evidence_refs")),
        "vue_default_promotion_gate_enabled": gate.get("vue_default_promotion_gate_enabled") is ready,
        "vue_default_promotion_ready": gate.get("vue_default_promotion_ready") is ready,
        "valid_dist_present": (not ready) or gate.get("valid_dist_present") is True,
        "route_smoke_passed": (not ready) or gate.get("route_smoke_passed") is True,
        "legacy_route_available": (not ready) or gate.get("legacy_route_available") is True,
        "fail_closed_verified": (not ready) or gate.get("fail_closed_verified") is True,
        "rollback_plan_ready": (not ready) or gate.get("rollback_plan_ready") is True,
        "separate_apply_pr_required": gate.get("separate_apply_pr_required") is True,
        "backend_remains_authoritative": gate.get("backend_remains_authoritative") is True,
    }
    invariants.update({key: gate.get(key) is False for key in _REQUIRED_FALSE_FLAGS})
    violations = [key for key, ok in invariants.items() if not ok]
    if violations:
        raise ValueError(f"invariant_violation:{','.join(sorted(violations))}")
    return gate


def write_vue_default_promotion_gate(*, data_root: str | Path, gate: dict[str, Any]) -> Path:
    validated = validate_vue_default_promotion_gate(gate)
    root = Path(data_root).expanduser().resolve()
    gate_id = str(validated.get("gate_id", _gate_id(_utc_now())))
    path = root / "atlas" / "vue_default_promotion_gates" / gate_id / "manifest.json"
    _ensure_under(root, path, "vue_default_promotion_gate_outside_data_root")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(validated, indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_vue_default_promotion_gate(
    *, manifest_path: str | Path, data_root: str | Path | None = None
) -> dict[str, Any]:
    path = Path(manifest_path).expanduser().resolve()
    if data_root is not None:
        _ensure_under(Path(data_root).expanduser().resolve(), path, "vue_default_promotion_gate_outside_data_root")
    return validate_vue_default_promotion_gate(json.loads(path.read_text(encoding="utf-8")))


def _read_milestone(*, milestone_path: Path, blocked: list[str]) -> dict[str, Any]:
    try:
        return validate_fully_autonomous_code_agent_milestone(json.loads(milestone_path.read_text(encoding="utf-8")))
    except Exception as exc:  # pragma: no cover - defensive metadata path
        blocked.append(f"fully_autonomous_milestone_read_failed:{type(exc).__name__}")
        return {}


def _validate_milestone_for_vue_gate(milestone: dict[str, Any]) -> list[str]:
    blocked: list[str] = []
    if milestone.get("schema_version") != FULLY_AUTONOMOUS_SCHEMA_VERSION:
        blocked.append("fully_autonomous_schema_required")
    if milestone.get("track_pr") != FULLY_AUTONOMOUS_TRACK:
        blocked.append("fully_autonomous_track_required")
    if milestone.get("status") != "ready":
        blocked.append("ready_fully_autonomous_milestone_required")
    if milestone.get("fully_autonomous_code_agent_ready") is not True:
        blocked.append("fully_autonomous_ready_required")
    for key in _REQUIRED_FALSE_FLAGS:
        if milestone.get(key) is not False and key in milestone:
            blocked.append(f"{key}_must_be_false")
    return blocked


def _safe_refs_or_block(values: list[str], field: str, blocked: list[str]) -> list[str]:
    refs: list[str] = []
    for value in values:
        try:
            refs.append(_safe_ref(value))
        except ValueError as exc:
            blocked.append(f"{field}_{exc}")
    return refs


def _safe_ref(value: str, *, allow_plain: bool = False) -> str:
    ref = str(value).strip().replace("\\", "/").strip("/")
    if not ref:
        raise ValueError("empty")
    path = Path(ref)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError("must_be_relative")
    if not allow_plain and len(path.parts) < 2:
        raise ValueError("must_include_directory")
    return path.as_posix()


def _gate_id(created_at: str) -> str:
    created_norm = created_at.replace(":", "").replace("-", "").replace("+", "").replace(".", "")
    return f"vue_default_promotion_gate_{created_norm}_{uuid.uuid4().hex[:8]}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_under(root: Path, target: Path, code: str) -> Path:
    rr = root.resolve()
    tt = target.resolve()
    if os.path.commonpath([str(rr), str(tt)]) != str(rr):
        raise ValueError(code)
    return tt
