from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.atlas.self_improvement_proposal import (
    SCHEMA_VERSION as SELF_IMPROVEMENT_PROPOSAL_SCHEMA_VERSION,
    load_self_improvement_proposal,
)

SCHEMA_VERSION = "atlas.self_modification_risk_classification.v1"
TRACK_PR = "PR-ATLAS-SCALE-141"
NEXT_REQUIRED_PR = "PR-ATLAS-SCALE-142"
_STRICT_TARGET_AREAS = {"atlas_runtime", "atlas_ui", "atlas_safety"}
_ALLOWED_TARGET_AREAS = {"atlas_runtime", "atlas_ui", "atlas_tests", "atlas_docs", "atlas_safety"}
_ALLOWED_TARGET_REPOS = {"CodeAgentPersonal", "KasaneCore"}
_ALLOWED_CLASSIFICATIONS = {"medium", "high", "strict"}


def classify_self_modification_risk(
    *,
    proposal_path: str | Path,
    data_root: str | Path | None = None,
    reviewer: str = "atlas",
    created_at: str | None = None,
) -> dict[str, Any]:
    created = created_at or _utc_now()
    proposal = load_self_improvement_proposal(manifest_path=proposal_path, data_root=data_root)
    path = Path(proposal_path).expanduser().resolve()
    root = Path(data_root if data_root is not None else path.parent).expanduser().resolve()
    blocked: list[str] = []
    try:
        _ensure_under(root, path, "proposal_outside_data_root")
    except ValueError as exc:
        blocked.append(str(exc))

    blocked.extend(_validate_proposal(proposal))
    classification = _classify(proposal)
    classification_authorized = not blocked
    result = {
        "schema_version": SCHEMA_VERSION,
        "classification_id": _classification_id(created),
        "created_at": created,
        "track_pr": TRACK_PR,
        "next_required_pr": NEXT_REQUIRED_PR,
        "proposal_path": str(path),
        "data_root": str(root),
        "reviewer": reviewer,
        "target_repo": proposal.get("target_repo", ""),
        "target_area": proposal.get("target_area", ""),
        "proposal_risk_level": proposal.get("risk_level", ""),
        "classification": classification,
        "classification_authorized": classification_authorized,
        "classification_blocked": not classification_authorized,
        "blocking_reasons": sorted(set(blocked)),
        "strict_self_modification_risk_classifier_enabled": classification_authorized,
        "classification_only": True,
        "strict_gate_required": classification == "strict",
        "human_review_required": True,
        "backend_authoritative": True,
        "vue_authoritative": False,
        "vue_execution_controls_enabled": False,
        "self_modification_enabled": False,
        "self_apply_enabled": False,
        "patch_preview_enabled": False,
        "automatic_patch_generation_enabled": False,
        "automatic_patch_apply_enabled": False,
        "automatic_verification_enabled": False,
        "autonomous_execution_enabled": False,
        "autonomous_loop_execution_enabled": False,
        "auto_continue_enabled": False,
        "execute_all_enabled": False,
        "direct_merge_enabled": False,
        "remote_git_push_enabled": False,
        "allowed_classifier_actions": ["read_proposal", "classify_risk", "record_required_gates", "request_human_review"],
        "forbidden_classifier_actions": [
            "generate_patch",
            "preview_patch",
            "apply_patch",
            "run_verification",
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
        "required_next_gates": _required_next_gates(classification),
        "execution_performed": False,
        "mutation_performed": False,
        "patch_generated": False,
        "patch_previewed": False,
        "patch_applied": False,
        "verification_performed": False,
        "branch_created": False,
        "draft_pr_created": False,
        "draft_pr_updated": False,
    }
    return validate_self_modification_risk_classification(result)


def validate_self_modification_risk_classification(result: dict[str, Any]) -> dict[str, Any]:
    required = [
        "schema_version",
        "track_pr",
        "target_repo",
        "target_area",
        "classification",
        "classification_authorized",
        "classification_blocked",
        "strict_self_modification_risk_classifier_enabled",
        "classification_only",
        "strict_gate_required",
        "human_review_required",
        "backend_authoritative",
        "vue_authoritative",
        "vue_execution_controls_enabled",
        "self_modification_enabled",
        "self_apply_enabled",
        "patch_preview_enabled",
        "automatic_patch_generation_enabled",
        "automatic_patch_apply_enabled",
        "automatic_verification_enabled",
        "autonomous_execution_enabled",
        "autonomous_loop_execution_enabled",
        "auto_continue_enabled",
        "execute_all_enabled",
        "direct_merge_enabled",
        "remote_git_push_enabled",
        "required_next_gates",
        "execution_performed",
        "mutation_performed",
        "patch_generated",
        "patch_previewed",
        "patch_applied",
        "verification_performed",
        "branch_created",
        "draft_pr_created",
        "draft_pr_updated",
    ]
    missing = [field for field in required if field not in result]
    if missing:
        raise ValueError(f"missing_required_fields:{','.join(missing)}")

    authorized = bool(result.get("classification_authorized"))
    classification = result.get("classification")
    invariants = {
        "schema_version": result.get("schema_version") == SCHEMA_VERSION,
        "track_pr": result.get("track_pr") == TRACK_PR,
        "target_repo": (not authorized) or result.get("target_repo") in _ALLOWED_TARGET_REPOS,
        "target_area": (not authorized) or result.get("target_area") in _ALLOWED_TARGET_AREAS,
        "classification": (not authorized) or classification in _ALLOWED_CLASSIFICATIONS,
        "classification_blocked": result.get("classification_blocked") is (not authorized),
        "strict_self_modification_risk_classifier_enabled": result.get("strict_self_modification_risk_classifier_enabled") is authorized,
        "classification_only": result.get("classification_only") is True,
        "strict_gate_required": result.get("strict_gate_required") is (classification == "strict"),
        "human_review_required": result.get("human_review_required") is True,
        "backend_authoritative": result.get("backend_authoritative") is True,
        "vue_authoritative": result.get("vue_authoritative") is False,
        "vue_execution_controls_enabled": result.get("vue_execution_controls_enabled") is False,
        "self_modification_enabled": result.get("self_modification_enabled") is False,
        "self_apply_enabled": result.get("self_apply_enabled") is False,
        "patch_preview_enabled": result.get("patch_preview_enabled") is False,
        "automatic_patch_generation_enabled": result.get("automatic_patch_generation_enabled") is False,
        "automatic_patch_apply_enabled": result.get("automatic_patch_apply_enabled") is False,
        "automatic_verification_enabled": result.get("automatic_verification_enabled") is False,
        "autonomous_execution_enabled": result.get("autonomous_execution_enabled") is False,
        "autonomous_loop_execution_enabled": result.get("autonomous_loop_execution_enabled") is False,
        "auto_continue_enabled": result.get("auto_continue_enabled") is False,
        "execute_all_enabled": result.get("execute_all_enabled") is False,
        "direct_merge_enabled": result.get("direct_merge_enabled") is False,
        "remote_git_push_enabled": result.get("remote_git_push_enabled") is False,
        "required_next_gates": bool(result.get("required_next_gates")),
        "execution_performed": result.get("execution_performed") is False,
        "mutation_performed": result.get("mutation_performed") is False,
        "patch_generated": result.get("patch_generated") is False,
        "patch_previewed": result.get("patch_previewed") is False,
        "patch_applied": result.get("patch_applied") is False,
        "verification_performed": result.get("verification_performed") is False,
        "branch_created": result.get("branch_created") is False,
        "draft_pr_created": result.get("draft_pr_created") is False,
        "draft_pr_updated": result.get("draft_pr_updated") is False,
    }
    violations = [key for key, ok in invariants.items() if not ok]
    if violations:
        raise ValueError(f"invariant_violation:{','.join(sorted(violations))}")
    return result


def write_self_modification_risk_classification(*, data_root: str | Path, result: dict[str, Any]) -> Path:
    validated = validate_self_modification_risk_classification(result)
    root = Path(data_root).expanduser().resolve()
    classification_id = str(validated["classification_id"])
    path = root / "atlas" / "self_modification_risk_classifications" / classification_id / "manifest.json"
    _ensure_under(root, path, "manifest_outside_data_root")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(validated, indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_self_modification_risk_classification(*, manifest_path: str | Path, data_root: str | Path | None = None) -> dict[str, Any]:
    path = Path(manifest_path).expanduser().resolve()
    if data_root is not None:
        _ensure_under(Path(data_root).expanduser().resolve(), path, "manifest_outside_data_root")
    return validate_self_modification_risk_classification(json.loads(path.read_text(encoding="utf-8")))


def _validate_proposal(proposal: dict[str, Any]) -> list[str]:
    blocked: list[str] = []
    if proposal.get("schema_version") != SELF_IMPROVEMENT_PROPOSAL_SCHEMA_VERSION:
        blocked.append("unsupported_self_improvement_proposal_schema")
    if proposal.get("proposal_authorized") is not True:
        blocked.append("self_improvement_proposal_authorization_required")
    if proposal.get("proposal_only") is not True:
        blocked.append("proposal_only_required")
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
        if proposal.get(key) is not False:
            blocked.append(f"{key}_must_be_false")
    return blocked


def _classify(proposal: dict[str, Any]) -> str:
    if proposal.get("risk_level") == "strict" or proposal.get("target_area") in _STRICT_TARGET_AREAS:
        return "strict"
    if proposal.get("risk_level") == "high":
        return "high"
    return "medium"


def _required_next_gates(classification: str) -> list[str]:
    gates = ["human_review", "proposal_traceability", "no_self_apply"]
    if classification == "strict":
        gates.extend(["strict_gate", "snapshot_plan", "rollback_plan", "security_review"])
    elif classification == "high":
        gates.extend(["snapshot_plan", "rollback_plan"])
    else:
        gates.append("rollback_notes")
    return gates


def _classification_id(created_at: str) -> str:
    created_norm = created_at.replace(":", "").replace("-", "").replace("+", "").replace(".", "")
    return f"self_modification_risk_{created_norm}_{uuid.uuid4().hex[:8]}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_under(root: Path, target: Path, code: str) -> Path:
    rr = root.resolve()
    tt = target.resolve()
    if os.path.commonpath([str(rr), str(tt)]) != str(rr):
        raise ValueError(code)
    return tt
