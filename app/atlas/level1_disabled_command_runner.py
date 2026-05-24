from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.atlas.verification_allowlist import classify_verification_command

SCHEMA_VERSION = "atlas.level1_disabled_command_runner.v1"
RUNTIME_LEVEL = "level_0_manual_only"


def build_disabled_single_allowlisted_command_runner_contract(
    *,
    command: str,
    project_path: str | Path,
    workspace_id: str = "default",
    pool_id: str = "",
    item_id: str = "",
    run_id: str = "",
    action_id: str = "",
    allowlist_id: str = "",
    allowlist_manifest_path: str = "",
    risk_level: str = "unknown",
    reason: str = "",
) -> dict[str, Any]:
    project_root = Path(project_path).expanduser().resolve()
    classification = classify_verification_command(command=command, project_path=project_root, risk_level=risk_level)
    allowlisted = bool(classification.get("allowed"))
    missing_requirements: list[str] = []
    blocking_reasons = ["runner_disabled_until_level1_transition"]
    if not allowlisted:
        missing_requirements.append("allowlisted_command")
        blocking_reasons.append(str(classification.get("reason") or "command_not_allowlisted"))

    contract = {
        "schema_version": SCHEMA_VERSION,
        "runner_id": f"disabled_runner_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}",
        "created_at": _utc_now(),
        "status": "disabled_allowlisted_candidate" if allowlisted else "blocked",
        "workspace_id": _safe_text(workspace_id, "default"),
        "pool_id": _safe_text(pool_id),
        "item_id": _safe_text(item_id),
        "run_id": _safe_text(run_id),
        "action_id": _safe_text(action_id),
        "reason": _safe_text(reason),
        "project_path": str(project_root),
        "requested_command": _safe_text(command),
        "normalized_command": _safe_text(classification.get("normalized_command")),
        "command_id": _safe_text(classification.get("command_id")),
        "command_category": _safe_text(classification.get("category"), "blocked"),
        "allowlist_id": _safe_text(allowlist_id),
        "allowlist_manifest_path": _safe_text(allowlist_manifest_path),
        "allowlisted": allowlisted,
        "allowlist_reason": _safe_text(classification.get("reason"), "unknown"),
        "matched_rule": _safe_text(classification.get("matched_rule"), "none"),
        "risk_level": _safe_text(classification.get("risk_level"), "unknown"),
        "requires_human_approval": bool(classification.get("requires_human_approval", True)),
        "runtime_level": RUNTIME_LEVEL,
        "manual_only": True,
        "single_action_only": True,
        "dry_run_required": True,
        "explicit_approval_required": True,
        "runner_enabled": False,
        "default_disabled": True,
        "execution_supported": False,
        "execution_performed": False,
        "mutation_performed": False,
        "verification_performed": False,
        "level1_execution_enabled": False,
        "autonomous_execution_enabled": False,
        "missing_requirements": missing_requirements,
        "blocking_reasons": blocking_reasons,
        "policy_notes": [
            "scale_121_disabled_single_allowlisted_command_runner",
            "allowlisted_only_candidate",
            "default_disabled",
            "no_command_execution",
            "no_level1_runtime_transition",
        ],
        "next_required_pr": "PR-ATLAS-SCALE-122",
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "status": contract["status"],
        "contract": contract,
        "classification": classification,
        "runtime_level": RUNTIME_LEVEL,
        "manual_only": True,
        "runner_enabled": False,
        "execution_supported": False,
        "execution_performed": False,
        "mutation_performed": False,
        "level1_execution_enabled": False,
        "autonomous_execution_enabled": False,
    }


def write_disabled_single_allowlisted_command_runner_contract(
    *,
    data_root: str | Path,
    contract: dict[str, Any],
) -> dict[str, Any]:
    root = Path(data_root).expanduser().resolve()
    runner_id = _safe_text(contract.get("runner_id"), f"disabled_runner_{uuid.uuid4().hex[:8]}")
    contract_dir = root / "atlas" / "level1_disabled_command_runners" / runner_id
    manifest_path = contract_dir / "manifest.json"
    _ensure_under(root, manifest_path, "manifest_outside_data_root")
    contract_dir.mkdir(parents=True, exist_ok=True)
    manifest = dict(contract)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {
        "status": "written",
        "runner_id": runner_id,
        "manifest_path": str(manifest_path),
        "manifest": manifest,
        "runtime_level": RUNTIME_LEVEL,
        "manual_only": True,
        "runner_enabled": False,
        "execution_supported": False,
        "execution_performed": False,
        "mutation_performed": False,
        "level1_execution_enabled": False,
        "autonomous_execution_enabled": False,
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_text(value: Any, fallback: str = "") -> str:
    if isinstance(value, str):
        text = value.strip()
        if text:
            return text[:512]
    return fallback


def _ensure_under(root: Path, target: Path, code: str) -> Path:
    rr = root.resolve()
    tt = target.resolve()
    if os.path.commonpath([str(rr), str(tt)]) != str(rr):
        raise ValueError(code)
    return tt
