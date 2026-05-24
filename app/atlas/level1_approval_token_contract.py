from __future__ import annotations

import hashlib
import json
import os
import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "atlas.level1_approval_token_contract.v1"
RUNTIME_LEVEL = "level_0_manual_only"
REQUIRED_CONFIRMATION_TEXT = "EXECUTE ONE ACTION"


def create_level1_approval_token_contract(
    *,
    workspace_id: str = "default",
    pool_id: str = "",
    item_id: str = "",
    run_id: str = "",
    action_id: str = "",
    dry_run_artifact_id: str = "",
    dry_run_manifest_path: str = "",
    risk_level: str = "unknown",
    expires_at: str = "",
    token: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Create a digest-only approval token contract without enabling execution."""

    raw_token = token if isinstance(token, str) and token.strip() else secrets.token_urlsafe(32)
    token_id = f"approval_token_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    token_digest = _digest(raw_token)
    contract = {
        "schema_version": SCHEMA_VERSION,
        "token_id": token_id,
        "token_digest": token_digest,
        "token_digest_preview": f"{token_digest[:12]}...",
        "created_at": created_at or _utc_now(),
        "expires_at": _safe_text(expires_at),
        "workspace_id": _safe_text(workspace_id, "default"),
        "pool_id": _safe_text(pool_id),
        "item_id": _safe_text(item_id),
        "run_id": _safe_text(run_id),
        "action_id": _safe_text(action_id),
        "dry_run_artifact_id": _safe_text(dry_run_artifact_id),
        "dry_run_manifest_path": _safe_text(dry_run_manifest_path),
        "risk_level": _safe_text(risk_level, "unknown").lower(),
        "runtime_level": RUNTIME_LEVEL,
        "manual_only": True,
        "requires_dry_run_artifact": True,
        "requires_confirmation_text": REQUIRED_CONFIRMATION_TEXT,
        "token_authorizes_execution": False,
        "token_authorizes_autonomous_loop": False,
        "token_authorizes_mutation": False,
        "execution_performed": False,
        "mutation_performed": False,
        "level1_execution_enabled": False,
        "autonomous_execution_enabled": False,
        "policy_notes": [
            "scale_119_approval_token_backend_contract",
            "digest_only_contract",
            "token_does_not_authorize_execution",
            "token_does_not_authorize_autonomous_loop",
        ],
        "next_required_pr": "PR-ATLAS-SCALE-120",
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "created",
        "approval_token": raw_token,
        "contract": contract,
        "runtime_level": RUNTIME_LEVEL,
        "manual_only": True,
        "level1_execution_enabled": False,
        "autonomous_execution_enabled": False,
        "execution_authorized": False,
        "autonomous_loop_authorized": False,
    }


def validate_level1_approval_token_contract(
    *,
    contract: dict[str, Any],
    provided_token: str = "",
    confirmation_text: str = "",
) -> dict[str, Any]:
    token_matches = bool(provided_token) and _digest(provided_token) == contract.get("token_digest")
    confirmation_text_satisfied = confirmation_text == REQUIRED_CONFIRMATION_TEXT
    dry_run_artifact_present = bool(contract.get("dry_run_artifact_id") or contract.get("dry_run_manifest_path"))
    runtime_level_ok = contract.get("runtime_level") == RUNTIME_LEVEL
    no_execution_authority = all(
        contract.get(key) is False
        for key in [
            "token_authorizes_execution",
            "token_authorizes_autonomous_loop",
            "token_authorizes_mutation",
            "level1_execution_enabled",
            "autonomous_execution_enabled",
        ]
    )

    missing_requirements: list[str] = []
    if not token_matches:
        missing_requirements.append("matching_approval_token")
    if not confirmation_text_satisfied:
        missing_requirements.append("confirmation_text")
    if not dry_run_artifact_present:
        missing_requirements.append("dry_run_artifact_reference")
    if not runtime_level_ok:
        missing_requirements.append("level_0_runtime_boundary")
    if not no_execution_authority:
        missing_requirements.append("no_execution_authority")

    approval_token_valid = not missing_requirements
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "valid_for_manual_gate_review" if approval_token_valid else "blocked",
        "approval_token_valid": approval_token_valid,
        "token_digest_matches": token_matches,
        "confirmation_text_satisfied": confirmation_text_satisfied,
        "dry_run_artifact_present": dry_run_artifact_present,
        "runtime_level_ok": runtime_level_ok,
        "no_execution_authority": no_execution_authority,
        "missing_requirements": missing_requirements,
        "runtime_level": RUNTIME_LEVEL,
        "manual_only": True,
        "execution_authorized": False,
        "autonomous_loop_authorized": False,
        "mutation_authorized": False,
        "level1_execution_enabled": False,
        "autonomous_execution_enabled": False,
        "next_required_pr": "PR-ATLAS-SCALE-120",
    }


def write_level1_approval_token_contract(*, data_root: str | Path, contract: dict[str, Any]) -> dict[str, Any]:
    root = Path(data_root).expanduser().resolve()
    token_id = _safe_text(contract.get("token_id"), f"approval_token_{uuid.uuid4().hex[:8]}")
    contract_dir = root / "atlas" / "level1_approval_token_contracts" / token_id
    manifest_path = contract_dir / "manifest.json"
    _ensure_under(root, manifest_path, "manifest_outside_data_root")
    contract_dir.mkdir(parents=True, exist_ok=True)
    manifest = dict(contract)
    manifest.pop("approval_token", None)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {
        "status": "written",
        "token_id": token_id,
        "manifest_path": str(manifest_path),
        "manifest": manifest,
        "runtime_level": RUNTIME_LEVEL,
        "manual_only": True,
        "execution_authorized": False,
        "autonomous_loop_authorized": False,
        "level1_execution_enabled": False,
        "autonomous_execution_enabled": False,
    }


def read_level1_approval_token_contract(*, manifest_path: str | Path, data_root: str | Path) -> dict[str, Any]:
    root = Path(data_root).expanduser().resolve()
    path = Path(manifest_path).expanduser().resolve()
    _ensure_under(root, path, "manifest_outside_data_root")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported_schema_version")
    return {"manifest": manifest, "warnings": []}


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


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
