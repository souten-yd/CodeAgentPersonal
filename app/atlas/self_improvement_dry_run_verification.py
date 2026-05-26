from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.atlas.self_improvement_patch_preview import (
    SCHEMA_VERSION as PATCH_PREVIEW_SCHEMA_VERSION,
    load_self_improvement_patch_preview,
)
from app.atlas.verification_allowlist import classify_verification_command

SCHEMA_VERSION = "atlas.self_improvement_dry_run_verification.v1"
TRACK_PR = "PR-ATLAS-SCALE-143"
NEXT_REQUIRED_PR = "PR-ATLAS-SCALE-144"
_REQUIRED_PATCH_PREVIEW_TRACK = "PR-ATLAS-SCALE-142"
_MAX_COMMANDS = 5


def create_self_improvement_dry_run_verification(
    *,
    patch_preview_path: str | Path,
    proposed_commands: list[str],
    project_path: str | Path,
    data_root: str | Path | None = None,
    reviewer: str = "atlas",
    created_at: str | None = None,
) -> dict[str, Any]:
    created = created_at or _utc_now()
    preview = load_self_improvement_patch_preview(manifest_path=patch_preview_path, data_root=data_root)
    path = Path(patch_preview_path).expanduser().resolve()
    root = Path(data_root if data_root is not None else path.parent).expanduser().resolve()
    project_root = Path(project_path).expanduser().resolve()
    blocked: list[str] = []
    try:
        _ensure_under(root, path, "patch_preview_outside_data_root")
    except ValueError as exc:
        blocked.append(str(exc))

    blocked.extend(_validate_patch_preview(preview))
    commands = [command.strip() for command in proposed_commands if command.strip()]
    if not commands:
        blocked.append("verification_commands_required")
    if len(commands) > _MAX_COMMANDS:
        blocked.append("too_many_verification_commands")

    risk_level = _verification_risk_level(preview)
    command_results = [
        classify_verification_command(command=command, project_path=project_root, risk_level=risk_level)
        for command in commands[:_MAX_COMMANDS]
    ]
    if any(not result.get("allowed") for result in command_results):
        blocked.append("only_allowlisted_verification_commands_allowed")

    verification_authorized = not blocked
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "verification_id": _verification_id(created),
        "created_at": created,
        "track_pr": TRACK_PR,
        "next_required_pr": NEXT_REQUIRED_PR,
        "patch_preview_path": str(path),
        "data_root": str(root),
        "project_path": str(project_root),
        "reviewer": reviewer,
        "target_repo": preview.get("target_repo", ""),
        "target_area": preview.get("target_area", ""),
        "risk_classification": preview.get("risk_classification", ""),
        "strict_gate_required": preview.get("strict_gate_required") is True,
        "verification_risk_level": risk_level,
        "proposed_commands": commands,
        "command_results": command_results,
        "allowed_commands": [result["command"] for result in command_results if result.get("allowed")],
        "blocked_commands": [result["command"] for result in command_results if not result.get("allowed")],
        "dry_run_verification_authorized": verification_authorized,
        "dry_run_verification_blocked": not verification_authorized,
        "blocking_reasons": sorted(set(blocked)),
        "self_improvement_dry_run_verification_enabled": verification_authorized,
        "dry_run_only": True,
        "verification_plan_only": True,
        "backend_authoritative": True,
        "vue_authoritative": False,
        "vue_execution_controls_enabled": False,
        "self_modification_enabled": False,
        "self_apply_enabled": False,
        "automatic_patch_generation_enabled": False,
        "automatic_patch_apply_enabled": False,
        "automatic_verification_enabled": False,
        "autonomous_execution_enabled": False,
        "autonomous_loop_execution_enabled": False,
        "auto_continue_enabled": False,
        "execute_all_enabled": False,
        "direct_merge_enabled": False,
        "remote_git_push_enabled": False,
        "allowed_verification_actions": ["read_patch_preview", "classify_commands", "record_dry_run_plan", "request_human_review"],
        "forbidden_verification_actions": [
            "execute_command",
            "generate_patch",
            "apply_patch",
            "create_branch",
            "push_branch",
            "create_pr",
            "update_pr",
            "direct_merge",
            "self_apply",
            "self_modify",
            "auto_continue",
            "execute_all",
        ],
        "execution_performed": False,
        "mutation_performed": False,
        "patch_generated": False,
        "patch_applied": False,
        "verification_performed": False,
        "verification_result_fabricated": False,
        "branch_created": False,
        "draft_pr_created": False,
        "draft_pr_updated": False,
    }
    return validate_self_improvement_dry_run_verification(manifest)


def validate_self_improvement_dry_run_verification(manifest: dict[str, Any]) -> dict[str, Any]:
    required = [
        "schema_version",
        "track_pr",
        "next_required_pr",
        "proposed_commands",
        "command_results",
        "dry_run_verification_authorized",
        "dry_run_verification_blocked",
        "self_improvement_dry_run_verification_enabled",
        "dry_run_only",
        "verification_plan_only",
        "backend_authoritative",
        "vue_authoritative",
        "vue_execution_controls_enabled",
        "self_modification_enabled",
        "self_apply_enabled",
        "automatic_patch_generation_enabled",
        "automatic_patch_apply_enabled",
        "automatic_verification_enabled",
        "autonomous_execution_enabled",
        "autonomous_loop_execution_enabled",
        "auto_continue_enabled",
        "execute_all_enabled",
        "direct_merge_enabled",
        "remote_git_push_enabled",
        "execution_performed",
        "mutation_performed",
        "patch_generated",
        "patch_applied",
        "verification_performed",
        "verification_result_fabricated",
        "branch_created",
        "draft_pr_created",
        "draft_pr_updated",
    ]
    missing = [field for field in required if field not in manifest]
    if missing:
        raise ValueError(f"missing_required_fields:{','.join(missing)}")

    authorized = bool(manifest.get("dry_run_verification_authorized"))
    command_results = list(manifest.get("command_results", []))
    invariants = {
        "schema_version": manifest.get("schema_version") == SCHEMA_VERSION,
        "track_pr": manifest.get("track_pr") == TRACK_PR,
        "next_required_pr": manifest.get("next_required_pr") == NEXT_REQUIRED_PR,
        "dry_run_verification_blocked": manifest.get("dry_run_verification_blocked") is (not authorized),
        "self_improvement_dry_run_verification_enabled": manifest.get("self_improvement_dry_run_verification_enabled") is authorized,
        "dry_run_only": manifest.get("dry_run_only") is True,
        "verification_plan_only": manifest.get("verification_plan_only") is True,
        "command_results": (not authorized) or (0 < len(command_results) <= _MAX_COMMANDS and all(result.get("allowed") for result in command_results)),
        "backend_authoritative": manifest.get("backend_authoritative") is True,
        "vue_authoritative": manifest.get("vue_authoritative") is False,
        "vue_execution_controls_enabled": manifest.get("vue_execution_controls_enabled") is False,
        "self_modification_enabled": manifest.get("self_modification_enabled") is False,
        "self_apply_enabled": manifest.get("self_apply_enabled") is False,
        "automatic_patch_generation_enabled": manifest.get("automatic_patch_generation_enabled") is False,
        "automatic_patch_apply_enabled": manifest.get("automatic_patch_apply_enabled") is False,
        "automatic_verification_enabled": manifest.get("automatic_verification_enabled") is False,
        "autonomous_execution_enabled": manifest.get("autonomous_execution_enabled") is False,
        "autonomous_loop_execution_enabled": manifest.get("autonomous_loop_execution_enabled") is False,
        "auto_continue_enabled": manifest.get("auto_continue_enabled") is False,
        "execute_all_enabled": manifest.get("execute_all_enabled") is False,
        "direct_merge_enabled": manifest.get("direct_merge_enabled") is False,
        "remote_git_push_enabled": manifest.get("remote_git_push_enabled") is False,
        "execution_performed": manifest.get("execution_performed") is False,
        "mutation_performed": manifest.get("mutation_performed") is False,
        "patch_generated": manifest.get("patch_generated") is False,
        "patch_applied": manifest.get("patch_applied") is False,
        "verification_performed": manifest.get("verification_performed") is False,
        "verification_result_fabricated": manifest.get("verification_result_fabricated") is False,
        "branch_created": manifest.get("branch_created") is False,
        "draft_pr_created": manifest.get("draft_pr_created") is False,
        "draft_pr_updated": manifest.get("draft_pr_updated") is False,
    }
    violations = [key for key, ok in invariants.items() if not ok]
    if violations:
        raise ValueError(f"invariant_violation:{','.join(sorted(violations))}")
    return manifest


def write_self_improvement_dry_run_verification(*, data_root: str | Path, manifest: dict[str, Any]) -> Path:
    validated = validate_self_improvement_dry_run_verification(manifest)
    root = Path(data_root).expanduser().resolve()
    verification_id = str(validated["verification_id"])
    path = root / "atlas" / "self_improvement_dry_run_verifications" / verification_id / "manifest.json"
    _ensure_under(root, path, "manifest_outside_data_root")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(validated, indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_self_improvement_dry_run_verification(*, manifest_path: str | Path, data_root: str | Path | None = None) -> dict[str, Any]:
    path = Path(manifest_path).expanduser().resolve()
    if data_root is not None:
        _ensure_under(Path(data_root).expanduser().resolve(), path, "manifest_outside_data_root")
    return validate_self_improvement_dry_run_verification(json.loads(path.read_text(encoding="utf-8")))


def _validate_patch_preview(preview: dict[str, Any]) -> list[str]:
    blocked: list[str] = []
    if preview.get("schema_version") != PATCH_PREVIEW_SCHEMA_VERSION:
        blocked.append("unsupported_patch_preview_schema")
    if preview.get("track_pr") != _REQUIRED_PATCH_PREVIEW_TRACK:
        blocked.append("patch_preview_track_required")
    if preview.get("next_required_pr") != TRACK_PR:
        blocked.append("patch_preview_next_pr_required")
    if preview.get("preview_authorized") is not True:
        blocked.append("authorized_patch_preview_required")
    if preview.get("self_improvement_patch_preview_enabled") is not True:
        blocked.append("patch_preview_enabled_required")
    for key in (
        "self_modification_enabled",
        "self_apply_enabled",
        "automatic_patch_generation_enabled",
        "automatic_patch_apply_enabled",
        "automatic_verification_enabled",
        "autonomous_execution_enabled",
        "autonomous_loop_execution_enabled",
        "auto_continue_enabled",
        "execute_all_enabled",
        "direct_merge_enabled",
        "remote_git_push_enabled",
        "execution_performed",
        "mutation_performed",
        "patch_generated",
        "patch_applied",
        "verification_performed",
        "branch_created",
        "draft_pr_created",
        "draft_pr_updated",
    ):
        if preview.get(key) is not False:
            blocked.append(f"{key}_must_be_false")
    return blocked


def _verification_risk_level(preview: dict[str, Any]) -> str:
    if preview.get("strict_gate_required") is True or preview.get("risk_classification") == "strict":
        return "strict_gate"
    risk = str(preview.get("risk_classification", "") or "unknown")
    return risk if risk in {"low", "medium", "high"} else "unknown"


def _verification_id(created_at: str) -> str:
    created_norm = created_at.replace(":", "").replace("-", "").replace("+", "").replace(".", "")
    return f"self_improvement_dry_run_verification_{created_norm}_{uuid.uuid4().hex[:8]}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_under(root: Path, target: Path, code: str) -> Path:
    rr = root.resolve()
    tt = target.resolve()
    if os.path.commonpath([str(rr), str(tt)]) != str(rr):
        raise ValueError(code)
    return tt
