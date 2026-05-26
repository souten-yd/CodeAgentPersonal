from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.atlas.patch_transaction import read_patch_transaction_manifest, validate_patch_transaction

CONFIRMATION_TEXT = "EXECUTE ONE ACTION"
_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _base_result(*, transaction_id: str = "", status: str = "blocked", blocked_reasons: list[str] | None = None) -> dict[str, Any]:
    return {
        "status": status,
        "transaction_id": transaction_id,
        "blocked_reasons": blocked_reasons or [],
        "changed_files": [],
        "actual_file_changed": False,
        "single_action": True,
        "manual_only": True,
        "approval_required": True,
        "confirmation_text_required": CONFIRMATION_TEXT,
        "automatic_apply_enabled": False,
        "automatic_rollback_enabled": False,
        "autonomous_execution_enabled": False,
    }


def _ensure_under(root: Path, target: Path, code: str) -> Path:
    rr = root.resolve()
    tt = target.resolve()
    if os.path.commonpath([str(rr), str(tt)]) != str(rr):
        raise ValueError(code)
    return tt


def _line_body(value: str) -> str:
    return value.rstrip("\r\n")


def _apply_unified_diff(original_text: str, diff_text: str) -> str | None:
    original = original_text.splitlines(keepends=True)
    result: list[str] = []
    cursor = 0
    saw_hunk = False
    lines = diff_text.splitlines()
    index = 0

    while index < len(lines):
        line = lines[index]
        match = _HUNK_RE.match(line)
        if not match:
            index += 1
            continue

        saw_hunk = True
        old_start = int(match.group(1))
        old_count = int(match.group(2) or "1")
        old_index = max(old_start - 1, 0)
        if old_start == 0 and old_count == 0:
            old_index = 0
        if old_index < cursor or old_index > len(original):
            return None
        result.extend(original[cursor:old_index])
        cursor = old_index
        index += 1

        while index < len(lines):
            hunk_line = lines[index]
            if _HUNK_RE.match(hunk_line):
                break
            if hunk_line.startswith(("diff --git ", "--- ", "+++ ", "index ")):
                break
            if hunk_line.startswith("\\"):
                index += 1
                continue
            if hunk_line.startswith(" "):
                if cursor >= len(original) or _line_body(original[cursor]) != hunk_line[1:]:
                    return None
                result.append(original[cursor])
                cursor += 1
            elif hunk_line.startswith("-"):
                if cursor >= len(original) or _line_body(original[cursor]) != hunk_line[1:]:
                    return None
                cursor += 1
            elif hunk_line.startswith("+"):
                result.append(hunk_line[1:] + "\n")
            elif not hunk_line.strip():
                return None
            else:
                return None
            index += 1

    if not saw_hunk:
        return None
    result.extend(original[cursor:])
    return "".join(result)


def _select_single_entry(entries: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, list[str]]:
    valid_entries = [entry for entry in entries if entry.get("path_valid")]
    by_path: dict[str, dict[str, Any]] = {}
    for entry in valid_entries:
        rel = str(entry.get("relative_path", ""))
        if not rel:
            continue
        existing = by_path.get(rel)
        if existing is None or existing.get("change_type") == "unknown":
            by_path[rel] = entry
    if len(by_path) != 1:
        return None, ["single_file_required"]
    return next(iter(by_path.values())), []


def apply_patch_transaction_one_action(
    *,
    manifest_path: str | Path | None = None,
    transaction_id: str = "",
    data_root: str | Path | None = None,
    project_path: str | Path | None = None,
    dry_run_gate_ready: bool = False,
    rollback_ready: bool = False,
    confirmation_token_present: bool = False,
    confirmation_text: str = "",
    approval_status: str = "missing",
    explicit_decision: str = "unknown",
    dry_run: bool = False,
) -> dict[str, Any]:
    parsed = read_patch_transaction_manifest(manifest_path=manifest_path, transaction_id=transaction_id, data_root=data_root)
    manifest = parsed["manifest"]
    txn_id = str(manifest.get("transaction_id", ""))
    blocked: list[str] = []

    root = Path(data_root if data_root is not None else manifest.get("data_root", "")).expanduser().resolve()
    if manifest_path is None:
        if not txn_id:
            blocked.append("transaction_id_missing")
            transaction_dir = root / "atlas" / "patch_transactions" / "missing"
        else:
            transaction_dir = root / "atlas" / "patch_transactions" / txn_id
    else:
        transaction_dir = Path(manifest_path).expanduser().resolve().parent
    try:
        _ensure_under(root, transaction_dir, "transaction_dir_outside_data_root")
    except ValueError as exc:
        blocked.append(str(exc))

    validation = validate_patch_transaction(
        manifest_path=manifest_path,
        transaction_id=transaction_id,
        data_root=root,
        project_path=project_path,
    )
    if not validation.get("valid"):
        blocked.append("transaction_validation_failed")
    if not validation.get("snapshot_reference_valid"):
        blocked.append("snapshot_reference_required")
    if not validation.get("path_safety_valid"):
        blocked.append("path_safety_invalid")
    if not validation.get("rollback_ready") or not rollback_ready:
        blocked.append("rollback_ready_required")
    if not dry_run_gate_ready:
        blocked.append("dry_run_gate_ready_required")
    if not confirmation_token_present:
        blocked.append("confirmation_token_required")
    if confirmation_text != CONFIRMATION_TEXT:
        blocked.append("confirmation_text_mismatch")
    if approval_status != "approved" or explicit_decision != "approve":
        blocked.append("explicit_human_approval_required")
    if manifest.get("risk_class") != "low":
        blocked.append("low_risk_required")

    entry, entry_errors = _select_single_entry(list(manifest.get("proposed_files", [])))
    blocked.extend(entry_errors)
    if entry is not None and entry.get("change_type") not in {"create", "modify"}:
        blocked.append("create_or_modify_change_required")

    diff_path_value = manifest.get("diff_text_path")
    diff_text = ""
    if not diff_path_value:
        blocked.append("diff_text_required")
    else:
        try:
            diff_path = _ensure_under(transaction_dir, Path(diff_path_value), "diff_path_outside_transaction_dir")
            if not diff_path.exists():
                blocked.append("diff_text_missing")
            else:
                diff_text = diff_path.read_text(encoding="utf-8")
        except ValueError as exc:
            blocked.append(str(exc))

    project_root = Path(project_path if project_path is not None else manifest.get("project_path", "")).expanduser().resolve()
    target: Path | None = None
    if entry is not None:
        try:
            target = _ensure_under(project_root, project_root / str(entry.get("relative_path", "")), "target_outside_project")
            if target.exists() and target.is_symlink():
                blocked.append("target_symlink_forbidden")
            if entry.get("change_type") == "modify" and not target.exists():
                blocked.append("modify_target_missing")
            if entry.get("change_type") == "create" and target.exists():
                blocked.append("create_target_exists")
        except ValueError as exc:
            blocked.append(str(exc))

    before = ""
    final_content: str | None = None
    if not blocked and target is not None:
        before = target.read_text(encoding="utf-8") if target.exists() else ""
        final_content = _apply_unified_diff(before, diff_text)
        if final_content is None:
            blocked.append("diff_parse_failed")

    if blocked:
        return _base_result(transaction_id=txn_id, blocked_reasons=list(dict.fromkeys(blocked)))

    changed_file = str(entry["relative_path"]) if entry is not None else ""
    if dry_run:
        result = _base_result(transaction_id=txn_id, status="planned")
        result["changed_files"] = [changed_file]
        result["dry_run"] = True
        return result

    assert target is not None
    assert final_content is not None
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(final_content, encoding="utf-8")
    actual_changed = before != final_content
    result = _base_result(transaction_id=txn_id, status="applied")
    result.update({
        "changed_files": [changed_file],
        "actual_file_changed": actual_changed,
        "applied_at": _utc_now(),
    })
    apply_result_path = transaction_dir / "apply_result.json"
    _ensure_under(transaction_dir, apply_result_path, "apply_result_outside_transaction_dir")
    apply_result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    result["apply_result_path"] = str(apply_result_path)
    return result
