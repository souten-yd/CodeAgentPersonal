from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "atlas.recovery_supervisor_manifest.v1"
TRACK_PR = "PR-ATLAS-SCALE-148"
NEXT_REQUIRED_PR = "PR-ATLAS-SCALE-149"

_ALLOWED_ACTIONS = {"inspect", "validate_pointer", "plan_pointer_switch", "record_report"}
_REQUIRED_FALSE_FLAGS = (
    "imports_target_runtime",
    "imports_web_runtime",
    "imports_model_provider",
    "command_execution_enabled",
    "restore_execution_enabled",
    "pointer_switch_execution_enabled",
    "file_copy_execution_enabled",
    "network_access_required",
    "execution_performed",
    "restore_performed",
    "pointer_switched",
    "file_copied",
    "mutation_performed",
)


def build_recovery_manifest(
    *,
    checkpoint_store: str | Path,
    release_pointer_path: str | Path,
    recovery_reports_dir: str | Path,
    stable_release_id: str = "",
    allowed_actions: list[str] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    created = created_at or _utc_now()
    store = Path(checkpoint_store).expanduser().resolve()
    pointer = Path(release_pointer_path).expanduser().resolve()
    reports = Path(recovery_reports_dir).expanduser().resolve()
    actions = list(dict.fromkeys(allowed_actions or ["inspect", "validate_pointer", "record_report"]))
    blocked: list[str] = []

    if not stable_release_id:
        blocked.append("stable_release_id_required")
    for action in actions:
        if action not in _ALLOWED_ACTIONS:
            blocked.append("recovery_action_not_allowed")
    if pointer.name != "current_release.json":
        blocked.append("release_pointer_filename_required")
    if pointer.parent != store:
        blocked.append("release_pointer_must_be_in_checkpoint_store")
    if not _is_relative_to(reports, store):
        blocked.append("reports_dir_must_be_under_checkpoint_store")

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "manifest_id": _manifest_id(created),
        "created_at": created,
        "track_pr": TRACK_PR,
        "next_required_pr": NEXT_REQUIRED_PR,
        "status": "ready" if not blocked else "blocked",
        "blocking_reasons": sorted(set(blocked)),
        "external_supervisor": True,
        "checkpoint_store": str(store),
        "release_pointer_path": str(pointer),
        "recovery_reports_dir": str(reports),
        "stable_release_id": stable_release_id,
        "allowed_actions": actions,
        "manual_operation_required": True,
        "application_runtime_independent": True,
        "target_runtime_imports_forbidden": True,
        "web_runtime_imports_forbidden": True,
        "model_provider_imports_forbidden": True,
        "read_json_manifests_allowed": True,
        "validate_hashes_allowed": True,
        "plan_release_pointer_switch_allowed": "plan_pointer_switch" in actions,
        "record_recovery_report_allowed": "record_report" in actions,
        "imports_target_runtime": False,
        "imports_web_runtime": False,
        "imports_model_provider": False,
        "command_execution_enabled": False,
        "restore_execution_enabled": False,
        "pointer_switch_execution_enabled": False,
        "file_copy_execution_enabled": False,
        "network_access_required": False,
        "execution_performed": False,
        "restore_performed": False,
        "pointer_switched": False,
        "file_copied": False,
        "mutation_performed": False,
    }
    return validate_recovery_manifest(manifest)


def validate_recovery_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    required = [
        "schema_version",
        "track_pr",
        "next_required_pr",
        "status",
        "external_supervisor",
        "checkpoint_store",
        "release_pointer_path",
        "recovery_reports_dir",
        "stable_release_id",
        "allowed_actions",
        "manual_operation_required",
        "application_runtime_independent",
        "target_runtime_imports_forbidden",
        "web_runtime_imports_forbidden",
        "model_provider_imports_forbidden",
        "read_json_manifests_allowed",
        "validate_hashes_allowed",
        "plan_release_pointer_switch_allowed",
        "record_recovery_report_allowed",
        *_REQUIRED_FALSE_FLAGS,
    ]
    missing = [field for field in required if field not in manifest]
    if missing:
        raise ValueError(f"missing_required_fields:{','.join(missing)}")

    actions = list(manifest.get("allowed_actions", []))
    invariants = {
        "schema_version": manifest.get("schema_version") == SCHEMA_VERSION,
        "track_pr": manifest.get("track_pr") == TRACK_PR,
        "next_required_pr": manifest.get("next_required_pr") == NEXT_REQUIRED_PR,
        "status": manifest.get("status") in {"ready", "blocked"},
        "blocked_reasons": manifest.get("status") != "blocked" or bool(manifest.get("blocking_reasons")),
        "external_supervisor": manifest.get("external_supervisor") is True,
        "stable_release_id": bool(manifest.get("stable_release_id")),
        "manual_operation_required": manifest.get("manual_operation_required") is True,
        "application_runtime_independent": manifest.get("application_runtime_independent") is True,
        "target_runtime_imports_forbidden": manifest.get("target_runtime_imports_forbidden") is True,
        "web_runtime_imports_forbidden": manifest.get("web_runtime_imports_forbidden") is True,
        "model_provider_imports_forbidden": manifest.get("model_provider_imports_forbidden") is True,
        "read_json_manifests_allowed": manifest.get("read_json_manifests_allowed") is True,
        "validate_hashes_allowed": manifest.get("validate_hashes_allowed") is True,
        "allowed_actions": bool(actions) and all(action in _ALLOWED_ACTIONS for action in actions),
        "plan_release_pointer_switch_allowed": manifest.get("plan_release_pointer_switch_allowed") is ("plan_pointer_switch" in actions),
        "record_recovery_report_allowed": manifest.get("record_recovery_report_allowed") is ("record_report" in actions),
    }
    invariants.update({key: manifest.get(key) is False for key in _REQUIRED_FALSE_FLAGS})
    violations = [key for key, ok in invariants.items() if not ok]
    if violations:
        raise ValueError(f"invariant_violation:{','.join(sorted(violations))}")
    return manifest


def write_recovery_manifest(*, manifest: dict[str, Any], destination: str | Path) -> Path:
    validated = validate_recovery_manifest(manifest)
    path = Path(destination).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(validated, indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_recovery_manifest(*, manifest_path: str | Path) -> dict[str, Any]:
    path = Path(manifest_path).expanduser().resolve()
    return validate_recovery_manifest(json.loads(path.read_text(encoding="utf-8")))


def read_release_pointer(*, pointer_path: str | Path) -> dict[str, Any]:
    path = Path(pointer_path).expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("release_pointer_must_be_object")
    if not payload.get("release_id"):
        raise ValueError("release_id_required")
    return payload


def hash_file_sha256(path: str | Path) -> str:
    target = Path(path).expanduser().resolve()
    digest = hashlib.sha256()
    with target.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def plan_release_pointer_switch(*, manifest: dict[str, Any], target_release_id: str) -> dict[str, Any]:
    validated = validate_recovery_manifest(manifest)
    blocked: list[str] = []
    if not validated.get("plan_release_pointer_switch_allowed"):
        blocked.append("plan_pointer_switch_not_allowed")
    if not target_release_id:
        blocked.append("target_release_id_required")
    return {
        "schema_version": "atlas.recovery_supervisor_plan.v1",
        "track_pr": TRACK_PR,
        "status": "planned" if not blocked else "blocked",
        "blocking_reasons": blocked,
        "current_release_id": validated.get("stable_release_id"),
        "target_release_id": target_release_id,
        "release_pointer_path": validated.get("release_pointer_path"),
        "manual_operation_required": True,
        "execution_performed": False,
        "pointer_switched": False,
        "mutation_performed": False,
    }


def _manifest_id(created_at: str) -> str:
    created_norm = created_at.replace(":", "").replace("-", "").replace("+", "").replace(".", "")
    return f"recovery_supervisor_{created_norm}_{uuid.uuid4().hex[:8]}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_relative_to(child: Path, parent: Path) -> bool:
    try:
        os.path.commonpath([str(parent.resolve()), str(child.resolve())]) == str(parent.resolve())
        return os.path.commonpath([str(parent.resolve()), str(child.resolve())]) == str(parent.resolve())
    except ValueError:
        return False
