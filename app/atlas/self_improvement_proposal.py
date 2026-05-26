from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.atlas.level3_autonomous_loop_candidate import (
    CANDIDATE_RUNTIME_LEVEL as LEVEL3_CANDIDATE_RUNTIME_LEVEL,
    SCHEMA_VERSION as LEVEL3_CANDIDATE_SCHEMA_VERSION,
    load_level3_autonomous_loop_candidate,
)

SCHEMA_VERSION = "atlas.self_improvement_proposal.v1"
TRACK_PR = "PR-ATLAS-SCALE-140"
NEXT_REQUIRED_PR = "PR-ATLAS-SCALE-141"
_ALLOWED_TARGET_REPOS = {"CodeAgentPersonal", "KasaneCore"}
_ALLOWED_TARGET_AREAS = {"atlas_runtime", "atlas_ui", "atlas_tests", "atlas_docs", "atlas_safety"}
_ALLOWED_RISK_LEVELS = {"low", "medium", "high", "strict"}
_MAX_ACCEPTANCE_CRITERIA = 8


def create_self_improvement_proposal(
    *,
    level3_candidate_path: str | Path,
    target_repo: str,
    target_area: str,
    problem_statement: str,
    proposed_direction: str,
    acceptance_criteria: list[str],
    data_root: str | Path | None = None,
    risk_level: str = "strict",
    approval_status: str = "missing",
    explicit_decision: str = "unknown",
    created_at: str | None = None,
) -> dict[str, Any]:
    created = created_at or _utc_now()
    candidate = load_level3_autonomous_loop_candidate(manifest_path=level3_candidate_path, data_root=data_root)
    candidate_path = Path(level3_candidate_path).expanduser().resolve()
    root = Path(data_root if data_root is not None else candidate_path.parent).expanduser().resolve()
    criteria = [item.strip() for item in acceptance_criteria if item.strip()]
    blocked: list[str] = []
    try:
        _ensure_under(root, candidate_path, "level3_candidate_outside_data_root")
    except ValueError as exc:
        blocked.append(str(exc))

    blocked.extend(_validate_level3_candidate(candidate))
    if approval_status != "approved" or explicit_decision != "approve":
        blocked.append("explicit_human_approval_required")
    if target_repo not in _ALLOWED_TARGET_REPOS:
        blocked.append("target_repo_not_allowed")
    if target_area not in _ALLOWED_TARGET_AREAS:
        blocked.append("target_area_not_allowed")
    if risk_level not in _ALLOWED_RISK_LEVELS:
        blocked.append("risk_level_not_allowed")
    if not problem_statement.strip():
        blocked.append("problem_statement_required")
    if not proposed_direction.strip():
        blocked.append("proposed_direction_required")
    if not criteria:
        blocked.append("acceptance_criteria_required")
    if len(criteria) > _MAX_ACCEPTANCE_CRITERIA:
        blocked.append("too_many_acceptance_criteria")

    proposal_authorized = not blocked
    proposal = {
        "schema_version": SCHEMA_VERSION,
        "proposal_id": _proposal_id(created),
        "created_at": created,
        "track_pr": TRACK_PR,
        "next_required_pr": NEXT_REQUIRED_PR,
        "source_level3_candidate_path": str(candidate_path),
        "source_runtime_level": candidate.get("runtime_level", ""),
        "data_root": str(root),
        "target_repo": target_repo,
        "target_area": target_area,
        "problem_statement": problem_statement.strip(),
        "proposed_direction": proposed_direction.strip(),
        "acceptance_criteria": criteria,
        "risk_level": risk_level,
        "proposal_authorized": proposal_authorized,
        "proposal_blocked": not proposal_authorized,
        "blocking_reasons": sorted(set(blocked)),
        "self_improvement_proposal_mode_enabled": proposal_authorized,
        "proposal_only": True,
        "backend_authoritative": True,
        "vue_authoritative": False,
        "vue_execution_controls_enabled": False,
        "autonomous_execution_enabled": False,
        "autonomous_loop_execution_enabled": False,
        "self_modification_enabled": False,
        "self_apply_enabled": False,
        "automatic_patch_generation_enabled": False,
        "automatic_patch_apply_enabled": False,
        "automatic_verification_enabled": False,
        "auto_continue_enabled": False,
        "execute_all_enabled": False,
        "direct_merge_enabled": False,
        "remote_git_push_enabled": False,
        "draft_pr_only": True,
        "strict_self_modification_gate_required": True,
        "risk_classifier_required_before_patch_preview": True,
        "allowed_proposal_actions": ["record_problem", "record_direction", "record_acceptance_criteria", "request_human_review"],
        "forbidden_proposal_actions": [
            "generate_patch",
            "apply_patch",
            "run_verification",
            "create_branch",
            "push_branch",
            "create_pr",
            "update_pr",
            "direct_merge",
            "self_apply",
            "auto_continue",
            "execute_all",
            "vue_authoritative_execution",
        ],
        "execution_performed": False,
        "mutation_performed": False,
        "patch_generated": False,
        "patch_applied": False,
        "verification_performed": False,
        "branch_created": False,
        "draft_pr_created": False,
        "draft_pr_updated": False,
    }
    return validate_self_improvement_proposal(proposal)


def validate_self_improvement_proposal(proposal: dict[str, Any]) -> dict[str, Any]:
    required = [
        "schema_version",
        "track_pr",
        "target_repo",
        "target_area",
        "problem_statement",
        "proposed_direction",
        "acceptance_criteria",
        "risk_level",
        "proposal_authorized",
        "proposal_blocked",
        "self_improvement_proposal_mode_enabled",
        "proposal_only",
        "backend_authoritative",
        "vue_authoritative",
        "vue_execution_controls_enabled",
        "autonomous_execution_enabled",
        "autonomous_loop_execution_enabled",
        "self_modification_enabled",
        "self_apply_enabled",
        "automatic_patch_generation_enabled",
        "automatic_patch_apply_enabled",
        "automatic_verification_enabled",
        "auto_continue_enabled",
        "execute_all_enabled",
        "direct_merge_enabled",
        "remote_git_push_enabled",
        "draft_pr_only",
        "strict_self_modification_gate_required",
        "risk_classifier_required_before_patch_preview",
        "execution_performed",
        "mutation_performed",
        "patch_generated",
        "patch_applied",
        "verification_performed",
        "branch_created",
        "draft_pr_created",
        "draft_pr_updated",
    ]
    missing = [field for field in required if field not in proposal]
    if missing:
        raise ValueError(f"missing_required_fields:{','.join(missing)}")

    authorized = bool(proposal.get("proposal_authorized"))
    criteria = list(proposal.get("acceptance_criteria", []))
    invariants = {
        "schema_version": proposal.get("schema_version") == SCHEMA_VERSION,
        "track_pr": proposal.get("track_pr") == TRACK_PR,
        "target_repo": (not authorized) or proposal.get("target_repo") in _ALLOWED_TARGET_REPOS,
        "target_area": (not authorized) or proposal.get("target_area") in _ALLOWED_TARGET_AREAS,
        "risk_level": (not authorized) or proposal.get("risk_level") in _ALLOWED_RISK_LEVELS,
        "acceptance_criteria": (not authorized) or (0 < len(criteria) <= _MAX_ACCEPTANCE_CRITERIA),
        "proposal_blocked": proposal.get("proposal_blocked") is (not authorized),
        "self_improvement_proposal_mode_enabled": proposal.get("self_improvement_proposal_mode_enabled") is authorized,
        "proposal_only": proposal.get("proposal_only") is True,
        "backend_authoritative": proposal.get("backend_authoritative") is True,
        "vue_authoritative": proposal.get("vue_authoritative") is False,
        "vue_execution_controls_enabled": proposal.get("vue_execution_controls_enabled") is False,
        "autonomous_execution_enabled": proposal.get("autonomous_execution_enabled") is False,
        "autonomous_loop_execution_enabled": proposal.get("autonomous_loop_execution_enabled") is False,
        "self_modification_enabled": proposal.get("self_modification_enabled") is False,
        "self_apply_enabled": proposal.get("self_apply_enabled") is False,
        "automatic_patch_generation_enabled": proposal.get("automatic_patch_generation_enabled") is False,
        "automatic_patch_apply_enabled": proposal.get("automatic_patch_apply_enabled") is False,
        "automatic_verification_enabled": proposal.get("automatic_verification_enabled") is False,
        "auto_continue_enabled": proposal.get("auto_continue_enabled") is False,
        "execute_all_enabled": proposal.get("execute_all_enabled") is False,
        "direct_merge_enabled": proposal.get("direct_merge_enabled") is False,
        "remote_git_push_enabled": proposal.get("remote_git_push_enabled") is False,
        "draft_pr_only": proposal.get("draft_pr_only") is True,
        "strict_self_modification_gate_required": proposal.get("strict_self_modification_gate_required") is True,
        "risk_classifier_required_before_patch_preview": proposal.get("risk_classifier_required_before_patch_preview") is True,
        "execution_performed": proposal.get("execution_performed") is False,
        "mutation_performed": proposal.get("mutation_performed") is False,
        "patch_generated": proposal.get("patch_generated") is False,
        "patch_applied": proposal.get("patch_applied") is False,
        "verification_performed": proposal.get("verification_performed") is False,
        "branch_created": proposal.get("branch_created") is False,
        "draft_pr_created": proposal.get("draft_pr_created") is False,
        "draft_pr_updated": proposal.get("draft_pr_updated") is False,
    }
    violations = [key for key, ok in invariants.items() if not ok]
    if violations:
        raise ValueError(f"invariant_violation:{','.join(sorted(violations))}")
    return proposal


def write_self_improvement_proposal(*, data_root: str | Path, proposal: dict[str, Any]) -> Path:
    validated = validate_self_improvement_proposal(proposal)
    root = Path(data_root).expanduser().resolve()
    proposal_id = str(validated["proposal_id"])
    path = root / "atlas" / "self_improvement_proposals" / proposal_id / "manifest.json"
    _ensure_under(root, path, "manifest_outside_data_root")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(validated, indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_self_improvement_proposal(*, manifest_path: str | Path, data_root: str | Path | None = None) -> dict[str, Any]:
    path = Path(manifest_path).expanduser().resolve()
    if data_root is not None:
        _ensure_under(Path(data_root).expanduser().resolve(), path, "manifest_outside_data_root")
    return validate_self_improvement_proposal(json.loads(path.read_text(encoding="utf-8")))


def _validate_level3_candidate(candidate: dict[str, Any]) -> list[str]:
    blocked: list[str] = []
    if candidate.get("schema_version") != LEVEL3_CANDIDATE_SCHEMA_VERSION:
        blocked.append("unsupported_level3_candidate_schema")
    if candidate.get("candidate_authorized") is not True:
        blocked.append("level3_candidate_authorization_required")
    if candidate.get("runtime_level") != LEVEL3_CANDIDATE_RUNTIME_LEVEL:
        blocked.append("level3_candidate_runtime_required")
    if candidate.get("level3_autonomous_loop_candidate_enabled") is not True:
        blocked.append("level3_candidate_required")
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
    return blocked


def _proposal_id(created_at: str) -> str:
    created_norm = created_at.replace(":", "").replace("-", "").replace("+", "").replace(".", "")
    return f"self_improvement_proposal_{created_norm}_{uuid.uuid4().hex[:8]}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_under(root: Path, target: Path, code: str) -> Path:
    rr = root.resolve()
    tt = target.resolve()
    if os.path.commonpath([str(rr), str(tt)]) != str(rr):
        raise ValueError(code)
    return tt
