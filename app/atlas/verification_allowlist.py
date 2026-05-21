from __future__ import annotations

import json
import os
import shlex
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "atlas.verification_allowlist.v1"
ALLOWLIST_VERSION = "v1"
BLOCKED_PREFIXES = {"rm", "del", "rmdir", "mv", "cp", "chmod", "chown", "sudo", "powershell", "curl", "wget", "ssh", "scp", "bash", "sh", "cmd"}
BLOCKED_PHRASES = [("git", "push"), ("git", "pull"), ("git", "clone"), ("git", "fetch"), ("git", "remote"), ("pip", "install"), ("npm", "install"), ("apt",), ("apt-get",), ("conda", "install")]
SHELL_METACHARS = (";", "&&", "||", "|", ">", ">>", "<", "$(", "`")
KNOWN_RISKS = {"low", "medium", "high", "strict_gate"}

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _ensure_under(root: Path, target: Path, code: str) -> Path:
    if os.path.commonpath([str(root.resolve()), str(target.resolve())]) != str(root.resolve()):
        raise ValueError(code)
    return target.resolve()

def _safe_relpath(v: str) -> str:
    p = Path(v)
    if p.is_absolute():
        raise ValueError("absolute_paths_forbidden")
    if any(part in ("", ".", "..") for part in p.parts):
        raise ValueError("path_traversal_forbidden")
    return p.as_posix()

def get_verification_allowlist_policy(*, risk_level: str = "unknown") -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "allowlist_version": ALLOWLIST_VERSION, "risk_level": risk_level or "unknown", "automatic_execution_enabled": False, "automatic_verification_enabled": False, "manual_only": True, "execution_supported": False}

def classify_verification_command(*, command: str, project_path: str | Path | None = None, risk_level: str = "unknown") -> dict[str, Any]:
    warnings: list[str] = []
    result = {"command_id": f"vacmd_{uuid.uuid4().hex[:12]}", "command": command, "normalized_command": "", "allowed": False, "category": "blocked", "reason": "unknown_command", "matched_rule": "none", "risk_level": risk_level or "unknown", "requires_human_approval": True, "execution_supported": False, "automatic_execution_enabled": False, "warnings": warnings}
    if any(x in command for x in SHELL_METACHARS):
        result.update(reason="shell_metacharacter_forbidden", matched_rule="block_shell_metacharacters")
        return result
    try:
        parts = shlex.split(command, posix=False)
    except ValueError:
        result.update(reason="command_parse_failed", matched_rule="parse")
        return result
    if not parts:
        result.update(reason="empty_command", matched_rule="parse")
        return result
    lower = [p.lower() for p in parts]
    if lower[0] in BLOCKED_PREFIXES:
        result.update(reason="blocked_destructive_or_shell_command", matched_rule="blocked_prefix")
        return result
    for phrase in BLOCKED_PHRASES:
        if tuple(lower[: len(phrase)]) == phrase:
            result.update(reason="blocked_remote_or_mutating_command", matched_rule="blocked_phrase")
            return result

    def validate_target(tok: str, prefix: str) -> tuple[bool, str]:
        target = tok.split("::", 1)[0]
        try:
            rel = _safe_relpath(target)
        except ValueError as exc:
            return False, str(exc)
        if prefix and not rel.startswith(prefix):
            return False, "target_path_prefix_forbidden"
        if project_path:
            _ensure_under(Path(project_path).resolve(), Path(project_path).resolve() / rel, "project_escape")
        return True, rel

    for tok in parts[1:]:
        if "/" in tok or "\\" in tok:
            if Path(tok.split("::", 1)[0]).is_absolute():
                result.update(reason="absolute_paths_forbidden", matched_rule="path_safety")
                return result

    if lower[:2] == ["pytest", "-q"] and len(parts) == 3:
        ok, rel = validate_target(parts[2], "tests/")
        if ok:
            result.update(allowed=True, category="pytest_targeted", reason="allowlisted_targeted_pytest", matched_rule="pytest_q_tests_target", normalized_command=f"pytest -q {parts[2]}")
        else:
            result.update(reason=rel, matched_rule="pytest_target_validation")
    elif lower[:3] == ["python", "-m", "py_compile"] and len(parts) == 4:
        ok, rel = validate_target(parts[3], "")
        if ok:
            result.update(allowed=True, category="python_syntax_check", reason="allowlisted_py_compile", matched_rule="python_m_py_compile", normalized_command=f"python -m py_compile {rel}")
        else:
            result.update(reason=rel, matched_rule="py_compile_target_validation")
    elif lower[:2] == ["node", "--check"] and len(parts) == 3:
        ok, rel = validate_target(parts[2], "web/js/")
        if ok:
            result.update(allowed=True, category="node_syntax_check", reason="allowlisted_node_check", matched_rule="node_check_web_js_target", normalized_command=f"node --check {rel}")
        else:
            result.update(reason=rel, matched_rule="node_check_target_validation")
    elif lower and lower[0] == "pytest":
        result.update(reason="broad_pytest_forbidden", matched_rule="pytest_requires_target")

    rl = (risk_level or "unknown").lower()
    if rl not in KNOWN_RISKS:
        result.update(allowed=False, reason="unknown_risk_level_blocked", matched_rule="risk_policy_unknown", requires_human_approval=True)
    elif rl == "low":
        result["requires_human_approval"] = False
    else:
        result["requires_human_approval"] = True
    return result

def validate_verification_command(**kwargs: Any) -> dict[str, Any]:
    r = classify_verification_command(**kwargs)
    return {"valid": bool(r.get("allowed")), "result": r, "manual_only": True, "automatic_execution_enabled": False, "automatic_verification_enabled": False}

def summarize_verification_allowlist_record(payload: dict[str, Any]) -> dict[str, Any]:
    rs = payload.get("command_results", [])
    return {"allowed_count": sum(1 for r in rs if r.get("allowed")), "blocked_count": sum(1 for r in rs if not r.get("allowed")), "human_approval_required": any(r.get("requires_human_approval") for r in rs), "automatic_execution_enabled": False}

def create_verification_allowlist_record(*, project_path: str | Path, data_root: str | Path, proposed_commands: list[str], workspace_id: str = "", pool_id: str = "", item_id: str = "", run_id: str = "", reason: str = "", transaction_id: str = "", risk_id: str = "", risk_level: str = "unknown", dry_run: bool = False) -> dict[str, Any]:
    root = Path(data_root).resolve(); proj = Path(project_path).resolve(); aid = f"allow_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"; adir = root / "atlas" / "verification_allowlists" / aid
    results = [classify_verification_command(command=c, project_path=proj, risk_level=risk_level) for c in (proposed_commands or [])]
    manifest = {"schema_version": SCHEMA_VERSION, "allowlist_id": aid, "created_at": _utc_now(), "project_path": str(proj), "data_root": str(root), "workspace_id": workspace_id, "pool_id": pool_id, "item_id": item_id, "run_id": run_id, "reason": reason, "transaction_id": transaction_id, "risk_id": risk_id, "risk_level": risk_level or "unknown", "proposed_commands": proposed_commands or [], "command_results": results, "allowed_commands": [r["command"] for r in results if r.get("allowed")], "blocked_commands": [r["command"] for r in results if not r.get("allowed")], "policy": "metadata_only_manual_foundation", "allowlist_version": ALLOWLIST_VERSION, "automatic_execution_enabled": False, "automatic_verification_enabled": False, "manual_only": True, "warnings": [], "summary": {}}
    manifest["summary"] = summarize_verification_allowlist_record(manifest)
    if not dry_run:
        adir.mkdir(parents=True, exist_ok=True)
        (adir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"status": "planned" if dry_run else "created", "allowlist_id": aid, "allowlist_dir": str(adir), "manifest_path": str(adir / "manifest.json"), "manifest": manifest, "dry_run": dry_run}

def read_verification_allowlist_record(*, manifest_path: str | Path | None = None, allowlist_id: str = "", data_root: str | Path | None = None) -> dict[str, Any]:
    manifest = Path(manifest_path).resolve() if manifest_path else Path(data_root).resolve() / "atlas" / "verification_allowlists" / allowlist_id / "manifest.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported_schema_version")
    root = Path(data_root if data_root is not None else payload.get("data_root", "")).resolve(); _ensure_under(root, manifest, "manifest_outside_data_root")
    return {"manifest": payload, "warnings": []}
