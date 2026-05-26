from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.atlas.level3_autonomous_loop_candidate import (
    CANDIDATE_RUNTIME_LEVEL as LEVEL3_RUNTIME_LEVEL,
    SCHEMA_VERSION as LEVEL3_CANDIDATE_SCHEMA_VERSION,
    load_level3_autonomous_loop_candidate,
)
from app.atlas.self_improvement_draft_pr_creation import (
    SCHEMA_VERSION as DRAFT_PR_SCHEMA_VERSION,
    load_self_improvement_draft_pr_creation,
)

SCHEMA_VERSION = "atlas.level4_self_improvement_checkpoint.v1"
TRANSITION_PR = "PR-ATLAS-SCALE-146"
PREVIOUS_RUNTIME_LEVEL = "level_3_autonomous_implementation_loop_candidate"
RUNTIME_LEVEL = "level_4_self_improvement_platform"
NEXT_REQUIRED_PR = "PR-ATLAS-SCALE-147"
REQUIRED_CONFIRMATION_TEXT = "AUTHORIZE LEVEL 4 SELF IMPROVEMENT CHECKPOINT"
_REQUIRED_DRAFT_PR_TRACK = "PR-ATLAS-SCALE-145"


def create_level4_self_improvement_checkpoint(
    *,
    level3_candidate_path: str | Path,
    self_improvement_draft_pr_path: str | Path,
    data_root: str | Path,
    approval_status: str = "missing",
    explicit_decision: str = "unknown",
    confirmation_token_present: bool = False,
    confirmation_text: str = "",
    strict_self_improvement_gates_ready: bool = False,
    candidate_workspace_required: bool = True,
    draft_pr_only: bool = True,
    direct_merge_forbidden: bool = True,
    stable_runtime_mutation_forbidden: bool = True,
    created_at: str | None = None,
) -> dict[str, Any]:
    created = created_at or _utc_now()
    root = Path(data_root).expanduser().resolve()
    candidate_path = Path(level3_candidate_path).expanduser().resolve()
    draft_pr_path = Path(self_improvement_draft_pr_path).expanduser().resolve()
    blocked: list[str] = []
    try:
        _ensure_under(root, candidate_path, "level3_candidate_outside_data_root")
        _ensure_under(root, draft_pr_path, "self_improvement_draft_pr_outside_data_root")
    except ValueError as exc:
        blocked.append(str(exc))

    candidate = load_level3_autonomous_loop_candidate(manifest_path=candidate_path, data_root=root)
    draft_pr = load_self_improvement_draft_pr_creation(manifest_path=draft_pr_path, data_root=root)
    blocked.extend(_validate_level3_candidate(candidate))
    blocked.extend(_validate_self_improvement_draft_pr(draft_pr))
    if approval_status != "approved" or explicit_decision != "approve":
        blocked.append("explicit_human_approval_required")
    if not confirmation_token_present:
        blocked.append("confirmation_token_required")
    if confirmation_text != REQUIRED_CONFIRMATION_TEXT:
        blocked.append("confirmation_text_mismatch")
    if not strict_self_improvement_gates_ready:
        blocked.append("strict_self_improvement_gates_required")
    if candidate_workspace_required is not True:
        blocked.append("candidate_workspace_required")
    if draft_pr_only is not True:
        blocked.append("draft_pr_only_required")
    if direct_merge_forbidden is not True:
        blocked.append("direct_merge_must_remain_forbidden")
    if stable_runtime_mutation_forbidden is not True:
        blocked.append("stable_runtime_mutation_must_remain_forbidden")

    authorized = not blocked
    checkpoint = {
        "schema_version": SCHEMA_VERSION,
        "checkpoint_id": _checkpoint_id(created),
        "created_at": created,
        "transition_pr": TRANSITION_PR,
        "next_required_pr": NEXT_REQUIRED_PR,
        "previous_runtime_level": PREVIOUS_RUNTIME_LEVEL,
        "runtime_level": RUNTIME_LEVEL if authorized else PREVIOUS_RUNTIME_LEVEL,
        "target_runtime_level": RUNTIME_LEVEL,
        "transition_authorized": authorized,
        "transition_blocked": not authorized,
        "blocking_reasons": sorted(set(blocked)),
        "level3_candidate_path": str(candidate_path),
        "self_improvement_draft_pr_path": str(draft_pr_path),
        "data_root": str(root),
        "level4_self_improvement_checkpoint_enabled": authorized,
        "self_improvement_platform_enabled": authorized,
        "strict_self_improvement_gates_ready": strict_self_improvement_gates_ready,
        "candidate_workspace_required": True,
        "draft_pr_only": True,
        "direct_merge_forbidden": True,
        "stable_runtime_mutation_forbidden": True,
        "human_approval_required_for_self_improvement": True,
        "backend_authoritative": True,
        "vue_authoritative": False,
        "vue_execution_controls_enabled": False,
        "autonomous_execution_enabled": False,
        "autonomous_loop_execution_enabled": False,
        "automatic_patch_generation_enabled": False,
        "automatic_patch_apply_enabled": False,
        "automatic_verification_enabled": False,
        "auto_continue_enabled": False,
        "execute_all_enabled": False,
        "self_modification_enabled": False,
        "self_apply_enabled": False,
        "direct_merge_enabled": False,
        "remote_git_push_enabled": False,
        "stable_runtime_mutation_enabled": False,
        "execution_performed": False,
        "mutation_performed": False,
        "patch_generated": False,
        "patch_applied": False,
        "verification_performed": False,
        "verification_result_fabricated": False,
        "branch_created": False,
        "draft_pr_created": False,
        "draft_pr_updated": False,
        "direct_merge_performed": False,
        "remote_git_push_performed": False,
        "stable_runtime_mutation_performed": False,
        "evidence_chain": {
            "level3_candidate_id": str(candidate.get("candidate_id", "")),
            "self_improvement_draft_pr_creation_id": str(draft_pr.get("creation_id", "")),
            "draft_pr_number": draft_pr.get("draft_pr_number"),
            "changed_files": list(draft_pr.get("changed_files", [])),
        },
        "allowed_level4_actions": [
            "prepare_self_improvement_candidate_workspace",
            "request_human_review",
            "create_draft_pr_metadata",
            "record_recovery_evidence",
        ],
        "forbidden_level4_actions": [
            "execute_command",
            "run_verification",
            "auto_apply_patch",
            "self_apply_to_stable_runtime",
            "direct_merge",
            "remote_git_push",
            "vue_authoritative_execution",
        ],
    }
    return validate_level4_self_improvement_checkpoint(checkpoint)


def validate_level4_self_improvement_checkpoint(checkpoint: dict[str, Any]) -> dict[str, Any]:
    required = [
        "schema_version",
        "transition_pr",
        "next_required_pr",
        "previous_runtime_level",
        "runtime_level",
        "target_runtime_level",
        "transition_authorized",
        "transition_blocked",
        "level4_self_improvement_checkpoint_enabled",
        "self_improvement_platform_enabled",
        "strict_self_improvement_gates_ready",
        "candidate_workspace_required",
        "draft_pr_only",
        "direct_merge_forbidden",
        "stable_runtime_mutation_forbidden",
        "human_approval_required_for_self_improvement",
        "backend_authoritative",
        "vue_authoritative",
        "vue_execution_controls_enabled",
        "autonomous_execution_enabled",
        "autonomous_loop_execution_enabled",
        "automatic_patch_generation_enabled",
        "automatic_patch_apply_enabled",
        "automatic_verification_enabled",
        "auto_continue_enabled",
        "execute_all_enabled",
        "self_modification_enabled",
        "self_apply_enabled",
        "direct_merge_enabled",
        "remote_git_push_enabled",
        "stable_runtime_mutation_enabled",
        "execution_performed",
        "mutation_performed",
        "patch_generated",
        "patch_applied",
        "verification_performed",
        "verification_result_fabricated",
        "branch_created",
        "draft_pr_created",
        "draft_pr_updated",
        "direct_merge_performed",
        "remote_git_push_performed",
        "stable_runtime_mutation_performed",
        "evidence_chain",
    ]
    missing = [field for field in required if field not in checkpoint]
    if missing:
        raise ValueError(f"missing_required_fields:{','.join(missing)}")

    authorized = bool(checkpoint.get("transition_authorized"))
    false_required = [
        "vue_authoritative",
        "vue_execution_controls_enabled",
        "autonomous_execution_enabled",
        "autonomous_loop_execution_enabled",
        "automatic_patch_generation_enabled",
        "automatic_patch_apply_enabled",
        "automatic_verification_enabled",
        "auto_continue_enabled",
        "execute_all_enabled",
        "self_modification_enabled",
        "self_apply_enabled",
        "direct_merge_enabled",
        "remote_git_push_enabled",
        "stable_runtime_mutation_enabled",
        "execution_performed",
        "mutation_performed",
        "patch_generated",
        "patch_applied",
        "verification_performed",
        "verification_result_fabricated",
        "branch_created",
        "draft_pr_created",
        "draft_pr_updated",
        "direct_merge_performed",
        "remote_git_push_performed",
        "stable_runtime_mutation_performed",
    ]
    invariants = {
        "schema_version": checkpoint.get("schema_version") == SCHEMA_VERSION,
        "transition_pr": checkpoint.get("transition_pr") == TRANSITION_PR,
        "next_required_pr": checkpoint.get("next_required_pr") == NEXT_REQUIRED_PR,
        "previous_runtime_level": checkpoint.get("previous_runtime_level") == PREVIOUS_RUNTIME_LEVEL,
        "runtime_level": checkpoint.get("runtime_level") == (RUNTIME_LEVEL if authorized else PREVIOUS_RUNTIME_LEVEL),
        "target_runtime_level": checkpoint.get("target_runtime_level") == RUNTIME_LEVEL,
        "transition_blocked": checkpoint.get("transition_blocked") is (not authorized),
        "level4_self_improvement_checkpoint_enabled": checkpoint.get("level4_self_improvement_checkpoint_enabled") is authorized,
        "self_improvement_platform_enabled": checkpoint.get("self_improvement_platform_enabled") is authorized,
        "strict_self_improvement_gates_ready": (not authorized) or checkpoint.get("strict_self_improvement_gates_ready") is True,
        "candidate_workspace_required": checkpoint.get("candidate_workspace_required") is True,
        "draft_pr_only": checkpoint.get("draft_pr_only") is True,
        "direct_merge_forbidden": checkpoint.get("direct_merge_forbidden") is True,
        "stable_runtime_mutation_forbidden": checkpoint.get("stable_runtime_mutation_forbidden") is True,
        "human_approval_required_for_self_improvement": checkpoint.get("human_approval_required_for_self_improvement") is True,
        "backend_authoritative": checkpoint.get("backend_authoritative") is True,
        "blocked_reasons": authorized or bool(checkpoint.get("blocking_reasons")),
        "evidence_chain": isinstance(checkpoint.get("evidence_chain"), dict),
    }
    invariants.update({key: checkpoint.get(key) is False for key in false_required})
    violations = [key for key, ok in invariants.items() if not ok]
    if violations:
        raise ValueError(f"invariant_violation:{','.join(sorted(violations))}")
    return checkpoint


def write_level4_self_improvement_checkpoint(*, data_root: str | Path, checkpoint: dict[str, Any]) -> Path:
    validated = validate_level4_self_improvement_checkpoint(checkpoint)
    root = Path(data_root).expanduser().resolve()
    checkpoint_id = str(validated["checkpoint_id"])
    path = root / "atlas" / "level4_self_improvement_checkpoints" / checkpoint_id / "manifest.json"
    _ensure_under(root, path, "manifest_outside_data_root")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(validated, indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_level4_self_improvement_checkpoint(*, manifest_path: str | Path, data_root: str | Path | None = None) -> dict[str, Any]:
    path = Path(manifest_path).expanduser().resolve()
    if data_root is not None:
        _ensure_under(Path(data_root).expanduser().resolve(), path, "manifest_outside_data_root")
    return validate_level4_self_improvement_checkpoint(json.loads(path.read_text(encoding="utf-8")))


def _validate_level3_candidate(candidate: dict[str, Any]) -> list[str]:
    blocked: list[str] = []
    if candidate.get("schema_version") != LEVEL3_CANDIDATE_SCHEMA_VERSION:
        blocked.append("unsupported_level3_candidate_schema")
    if candidate.get("candidate_authorized") is not True:
        blocked.append("level3_candidate_authorization_required")
    if candidate.get("runtime_level") != LEVEL3_RUNTIME_LEVEL:
        blocked.append("level3_runtime_level_required")
    if candidate.get("level3_autonomous_loop_candidate_enabled") is not True:
        blocked.append("level3_candidate_enabled_required")
    for key in (
        "autonomous_loop_execution_enabled",
        "autonomous_execution_enabled",
        "automatic_patch_generation_enabled",
        "automatic_patch_apply_enabled",
        "automatic_verification_enabled",
        "auto_continue_enabled",
        "execute_all_enabled",
        "self_modification_enabled",
        "direct_merge_enabled",
        "remote_git_push_enabled",
        "vue_authoritative",
        "vue_execution_controls_enabled",
        "execution_performed",
        "mutation_performed",
        "verification_performed",
        "retry_performed",
        "rollback_performed",
        "restore_performed",
        "draft_pr_created",
        "draft_pr_updated",
    ):
        if candidate.get(key) is not False:
            blocked.append(f"{key}_must_be_false")
    if candidate.get("draft_pr_only") is not True:
        blocked.append("draft_pr_only_required")
    return blocked


def _validate_self_improvement_draft_pr(draft_pr: dict[str, Any]) -> list[str]:
    blocked: list[str] = []
    if draft_pr.get("schema_version") != DRAFT_PR_SCHEMA_VERSION:
        blocked.append("unsupported_self_improvement_draft_pr_schema")
    if draft_pr.get("track_pr") != _REQUIRED_DRAFT_PR_TRACK:
        blocked.append("self_improvement_draft_pr_track_required")
    if draft_pr.get("next_required_pr") != TRANSITION_PR:
        blocked.append("self_improvement_draft_pr_next_pr_required")
    if draft_pr.get("status") != "created" or draft_pr.get("draft_pr_created") is not True:
        blocked.append("created_self_improvement_draft_pr_required")
    if draft_pr.get("draft") is not True:
        blocked.append("draft_pr_must_remain_draft")
    if len(draft_pr.get("changed_files", [])) != 1:
        blocked.append("single_changed_file_required")
    for key in (
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
        "patch_generated",
        "automatic_pr_creation_enabled",
        "draft_pr_updated",
        "verification_result_fabricated",
        "branch_created",
    ):
        if draft_pr.get(key) is not False:
            blocked.append(f"{key}_must_be_false")
    return blocked


def _checkpoint_id(created_at: str) -> str:
    created_norm = created_at.replace(":", "").replace("-", "").replace("+", "").replace(".", "")
    return f"level4_self_improvement_{created_norm}_{uuid.uuid4().hex[:8]}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_under(root: Path, target: Path, code: str) -> Path:
    rr = root.resolve()
    tt = target.resolve()
    if os.path.commonpath([str(rr), str(tt)]) != str(rr):
        raise ValueError(code)
    return tt
