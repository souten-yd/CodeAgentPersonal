from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "atlas.boot_self_diagnosis_checkpoint.v1"
TRACK_PR = "PR-ATLAS-SCALE-150"
NEXT_REQUIRED_PR = "PR-ATLAS-SCALE-151"
CURRENT_RUNTIME_LEVEL = "level_4_self_improvement_platform"

CHECK_PYTHON_IMPORT_SMOKE = "python_import_smoke"
CHECK_FASTAPI_ROUTER_INCLUDE_SMOKE = "fastapi_router_include_smoke"
CHECK_HEALTH_PROBE = "health_probe"
CHECK_ATLAS_CONTRACT_SMOKE = "atlas_contract_smoke"
CHECK_UI_ASSET_EXISTENCE = "ui_asset_existence"
CHECK_ATLAS_NEXT_MOUNT_DISPLAY_ONLY = "atlas_next_mount_display_only"
CHECK_RECOVERY_SUPERVISOR_AVAILABILITY = "recovery_supervisor_availability"

REQUIRED_CHECKS = {
    CHECK_PYTHON_IMPORT_SMOKE,
    CHECK_FASTAPI_ROUTER_INCLUDE_SMOKE,
    CHECK_HEALTH_PROBE,
    CHECK_ATLAS_CONTRACT_SMOKE,
    CHECK_UI_ASSET_EXISTENCE,
    CHECK_ATLAS_NEXT_MOUNT_DISPLAY_ONLY,
    CHECK_RECOVERY_SUPERVISOR_AVAILABILITY,
}
CHECK_STATUSES = {"pass", "fail", "unknown", "not_run"}
_HASH_RE = re.compile(r"^[a-fA-F0-9]{64}$")
_REQUIRED_FALSE_FLAGS = (
    "boot_check_execution_enabled",
    "boot_check_execution_performed",
    "command_execution_enabled",
    "command_execution_performed",
    "network_access_required",
    "health_probe_performed",
    "import_smoke_performed",
    "router_include_smoke_performed",
    "atlas_contract_smoke_performed",
    "ui_asset_probe_performed",
    "atlas_next_probe_performed",
    "recovery_supervisor_probe_performed",
    "stable_runtime_mutation_enabled",
    "stable_runtime_mutation_performed",
    "candidate_workspace_created",
    "candidate_apply_performed",
    "promotion_enabled",
    "promotion_performed",
    "direct_merge_enabled",
    "remote_git_push_enabled",
    "self_apply_enabled",
    "self_modification_enabled",
    "vue_authoritative",
)


def create_boot_self_diagnosis_checkpoint(
    *,
    stable_release_id: str,
    source_commit: str,
    release_pointer_path: str | Path,
    checkpoint_store: str | Path,
    boot_checks: list[dict[str, Any]],
    artifact_hashes: dict[str, str] | None = None,
    recovery_manifest_path: str | Path | None = None,
    candidate_workspace_plan_path: str | Path | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    created = created_at or _utc_now()
    store = Path(checkpoint_store).expanduser().resolve()
    pointer = Path(release_pointer_path).expanduser().resolve()
    recovery_path = str(Path(recovery_manifest_path).expanduser().resolve()) if recovery_manifest_path else ""
    candidate_path = str(Path(candidate_workspace_plan_path).expanduser().resolve()) if candidate_workspace_plan_path else ""
    hashes = dict(artifact_hashes or {})
    checks = [_normalize_check(check) for check in boot_checks]
    blocked: list[str] = []

    if not stable_release_id:
        blocked.append("stable_release_id_required")
    if not source_commit:
        blocked.append("source_commit_required")
    if pointer.name != "current_release.json":
        blocked.append("release_pointer_filename_required")
    if not _is_relative_to(pointer, store):
        blocked.append("release_pointer_must_be_under_checkpoint_store")
    check_names = {str(check.get("name", "")) for check in checks}
    missing_checks = sorted(REQUIRED_CHECKS - check_names)
    if missing_checks:
        blocked.append("required_boot_checks_missing")
    for check in checks:
        if check.get("name") not in REQUIRED_CHECKS:
            blocked.append("boot_check_not_allowed")
        if check.get("status") not in CHECK_STATUSES:
            blocked.append("boot_check_status_not_allowed")
        if check.get("status") in {"pass", "fail"} and not check.get("evidence_ref"):
            blocked.append("boot_check_evidence_required")
    for path, digest in hashes.items():
        if not _is_repo_relative(path):
            blocked.append("artifact_hash_path_must_be_repo_relative")
        if not _HASH_RE.match(str(digest)):
            blocked.append("artifact_hash_sha256_required")

    status = "ready" if not blocked else "blocked"
    checkpoint = {
        "schema_version": SCHEMA_VERSION,
        "checkpoint_id": _checkpoint_id(created),
        "created_at": created,
        "track_pr": TRACK_PR,
        "next_required_pr": NEXT_REQUIRED_PR,
        "status": status,
        "blocking_reasons": sorted(set(blocked)),
        "runtime_level": CURRENT_RUNTIME_LEVEL,
        "boot_self_diagnosis_checkpoint_enabled": status == "ready",
        "backend_authoritative": True,
        "stable_release_id": stable_release_id,
        "source_commit": source_commit,
        "checkpoint_store": str(store),
        "release_pointer_path": str(pointer),
        "recovery_manifest_path": recovery_path,
        "candidate_workspace_plan_path": candidate_path,
        "stable_checkpoint_artifact_only": True,
        "boot_health_artifact_only": True,
        "required_checks": sorted(REQUIRED_CHECKS),
        "boot_checks": checks,
        "artifact_hashes": dict(sorted(hashes.items())),
        "manual_operation_required": True,
        "boot_check_execution_enabled": False,
        "boot_check_execution_performed": False,
        "command_execution_enabled": False,
        "command_execution_performed": False,
        "network_access_required": False,
        "health_probe_performed": False,
        "import_smoke_performed": False,
        "router_include_smoke_performed": False,
        "atlas_contract_smoke_performed": False,
        "ui_asset_probe_performed": False,
        "atlas_next_probe_performed": False,
        "recovery_supervisor_probe_performed": False,
        "stable_runtime_mutation_enabled": False,
        "stable_runtime_mutation_performed": False,
        "candidate_workspace_created": False,
        "candidate_apply_performed": False,
        "promotion_enabled": False,
        "promotion_performed": False,
        "direct_merge_enabled": False,
        "remote_git_push_enabled": False,
        "self_apply_enabled": False,
        "self_modification_enabled": False,
        "vue_authoritative": False,
        "allowed_next_actions": [
            "review_boot_self_diagnosis_checkpoint",
            "record_stable_checkpoint_artifact",
            "record_boot_health_artifact",
        ],
        "forbidden_actions": [
            "run_boot_checks",
            "run_health_probe",
            "import_application_runtime",
            "create_candidate_workspace",
            "apply_candidate_patch",
            "promote_candidate",
            "mutate_stable_runtime",
            "direct_merge",
            "remote_git_push",
        ],
    }
    return validate_boot_self_diagnosis_checkpoint(checkpoint)


def validate_boot_self_diagnosis_checkpoint(checkpoint: dict[str, Any]) -> dict[str, Any]:
    required = [
        "schema_version",
        "track_pr",
        "next_required_pr",
        "status",
        "runtime_level",
        "boot_self_diagnosis_checkpoint_enabled",
        "backend_authoritative",
        "stable_release_id",
        "source_commit",
        "checkpoint_store",
        "release_pointer_path",
        "stable_checkpoint_artifact_only",
        "boot_health_artifact_only",
        "required_checks",
        "boot_checks",
        "artifact_hashes",
        "manual_operation_required",
        *_REQUIRED_FALSE_FLAGS,
    ]
    missing = [field for field in required if field not in checkpoint]
    if missing:
        raise ValueError(f"missing_required_fields:{','.join(missing)}")

    is_blocked = checkpoint.get("status") == "blocked"
    checks = list(checkpoint.get("boot_checks", []))
    check_names = {str(check.get("name", "")) for check in checks}
    hashes = dict(checkpoint.get("artifact_hashes", {}))
    pointer = Path(str(checkpoint.get("release_pointer_path", ""))).expanduser().resolve()
    store = Path(str(checkpoint.get("checkpoint_store", ""))).expanduser().resolve()
    invariants = {
        "schema_version": checkpoint.get("schema_version") == SCHEMA_VERSION,
        "track_pr": checkpoint.get("track_pr") == TRACK_PR,
        "next_required_pr": checkpoint.get("next_required_pr") == NEXT_REQUIRED_PR,
        "status": checkpoint.get("status") in {"ready", "blocked"},
        "blocked_reasons": not is_blocked or bool(checkpoint.get("blocking_reasons")),
        "runtime_level": checkpoint.get("runtime_level") == CURRENT_RUNTIME_LEVEL,
        "boot_self_diagnosis_checkpoint_enabled": checkpoint.get("boot_self_diagnosis_checkpoint_enabled") is (checkpoint.get("status") == "ready"),
        "backend_authoritative": checkpoint.get("backend_authoritative") is True,
        "stable_release_id": is_blocked or bool(checkpoint.get("stable_release_id")),
        "source_commit": is_blocked or bool(checkpoint.get("source_commit")),
        "stable_checkpoint_artifact_only": checkpoint.get("stable_checkpoint_artifact_only") is True,
        "boot_health_artifact_only": checkpoint.get("boot_health_artifact_only") is True,
        "manual_operation_required": checkpoint.get("manual_operation_required") is True,
        "required_checks": set(checkpoint.get("required_checks", [])) == REQUIRED_CHECKS,
        "boot_checks": is_blocked or (REQUIRED_CHECKS <= check_names and _checks_are_valid(checks)),
        "artifact_hashes": is_blocked or _hashes_are_valid(hashes),
        "release_pointer_path": is_blocked or (pointer.name == "current_release.json" and _is_relative_to(pointer, store)),
    }
    invariants.update({key: checkpoint.get(key) is False for key in _REQUIRED_FALSE_FLAGS})
    violations = [key for key, ok in invariants.items() if not ok]
    if violations:
        raise ValueError(f"invariant_violation:{','.join(sorted(violations))}")
    return checkpoint


def write_boot_self_diagnosis_checkpoint(*, checkpoint: dict[str, Any], destination: str | Path) -> Path:
    validated = validate_boot_self_diagnosis_checkpoint(checkpoint)
    path = Path(destination).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(validated, indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_boot_self_diagnosis_checkpoint(*, manifest_path: str | Path) -> dict[str, Any]:
    path = Path(manifest_path).expanduser().resolve()
    return validate_boot_self_diagnosis_checkpoint(json.loads(path.read_text(encoding="utf-8")))


def _normalize_check(check: dict[str, Any]) -> dict[str, str]:
    return {
        "name": str(check.get("name", "")),
        "status": str(check.get("status", "unknown")),
        "evidence_ref": str(check.get("evidence_ref", "")),
        "summary": str(check.get("summary", "")),
    }


def _checks_are_valid(checks: list[dict[str, Any]]) -> bool:
    for check in checks:
        if check.get("name") not in REQUIRED_CHECKS:
            return False
        if check.get("status") not in CHECK_STATUSES:
            return False
        if check.get("status") in {"pass", "fail"} and not check.get("evidence_ref"):
            return False
    return True


def _hashes_are_valid(hashes: dict[str, str]) -> bool:
    return all(_is_repo_relative(path) and _HASH_RE.match(str(digest)) for path, digest in hashes.items())


def _is_repo_relative(path: str) -> bool:
    normalized = str(path).strip().replace("\\", "/").strip("/")
    if not normalized:
        return False
    parts = normalized.split("/")
    return ":" not in parts[0] and all(part not in {"", ".", ".."} for part in parts)


def _checkpoint_id(created_at: str) -> str:
    created_norm = created_at.replace(":", "").replace("-", "").replace("+", "").replace(".", "")
    return f"boot_self_diagnosis_{created_norm}_{uuid.uuid4().hex[:8]}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_relative_to(child: Path, parent: Path) -> bool:
    try:
        resolved_parent = str(parent.resolve())
        return os.path.commonpath([resolved_parent, str(child.resolve())]) == resolved_parent
    except ValueError:
        return False