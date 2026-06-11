from __future__ import annotations

import re
from pathlib import Path

from agent.atlas_action_type import normalize_action_type
from agent.atlas_plan_item_file_changes import (
    ALLOWED_FILE_CHANGE_ACTIONS,
    FORBIDDEN_FILE_CHANGE_ACTIONS,
    has_file_change_content,
    infer_content_mode,
    normalize_plan_item_file_changes,
    validate_protected_relative_path,
)
from agent.atlas_placeholder_detector import has_blocking_placeholder_content, is_placeholder_only_content
from agent.atlas_patch_generation_state import is_patch_generation_success
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool

_MAX_CONTENT_BYTES = 1024 * 1024


def _quality_block_enforced(pool: AtlasPlanPool) -> bool:
    """True when generation quality is enforced before disk writes.

    Full-autopilot pools always enforce; legacy non-autonomous pools keep their
    prior warn/default behavior unless the Features switch explicitly requests block.
    """
    features = (getattr(pool, "metadata", {}) or {}).get("automation_features") or {}
    return (
        str(features.get("quality_gate_enforcement") or "warn").lower() == "block"
        or str(getattr(pool, "automation_level", "") or "").lower() == "full_autopilot"
    )

# Back-compat alias retained for callers that import the original name.
normalize_safe_apply_action_type = normalize_action_type


class AtlasFileSafeApplyExecutor:
    def __init__(self, *, workspace_root: str | Path = "."):
        self.workspace_root = Path(workspace_root).resolve()

    def apply_plan_item_safe(self, *, item: AtlasPlanItem, pool: AtlasPlanPool) -> dict:
        normalize_plan_item_file_changes(item)
        if str(item.risk_level or "").strip().lower() == "critical":
            return self._blocked("critical_risk_not_allowed")
        review_block = self._review_precondition_block_reason(item)
        if review_block:
            return self._blocked(review_block)
        file_changes = (item.metadata or {}).get("file_changes")
        if isinstance(file_changes, list) and file_changes:
            return self._apply_file_changes_safe(item=item, pool=pool, file_changes=file_changes)
        action_type = str((item.metadata or {}).get("action_type") or "").strip().lower()
        if action_type in FORBIDDEN_FILE_CHANGE_ACTIONS:
            return self._blocked("forbidden_action_type")
        if action_type not in ALLOWED_FILE_CHANGE_ACTIONS:
            return self._blocked("unsupported_action_type")
        if len(item.target_files or []) != 1:
            return self._blocked("multi_file_item_requires_file_changes")

        rel_target = str(item.target_files[0] or "").strip()
        target, path_reason = self._safe_target_path(rel_target)
        if target is None:
            return self._blocked(path_reason or "unsafe_target_path")

        existed = target.exists()
        current_text = ""
        if existed:
            try:
                current_text = target.read_text(encoding="utf-8", errors="replace")
            except Exception:
                return self._blocked("target_unreadable")

        # Resolve the final file content. Supports full-file (proposed_content), surgical string
        # replacements (edits: old->new), append, and hunk-aware unified-diff — all computed against
        # the file's CURRENT content so a patch connects to existing code instead of overwriting it.
        parse = self._resolve_content(item, current_text=current_text, target_exists=existed)
        if parse["status"] != "ok":
            return self._blocked(parse["reason"])
        content = parse["content"]
        if len(content.encode("utf-8")) > _MAX_CONTENT_BYTES:
            return self._blocked("content_too_large")
        # Pre-apply quality gate: refuse to write placeholder-only "implementations" when the
        # Features set quality_gate_enforcement="block" (stops empty deliverables before disk I/O).
        if _quality_block_enforced(pool) and self._quality_block_reason(content, file_path=rel_target):
            return self._blocked(self._quality_block_reason(content, file_path=rel_target))

        effective_action = action_type
        if action_type == "update":
            if not existed:
                return self._blocked("update_target_missing")
        elif action_type == "create":
            # A planner/weak model often labels an edit of an existing file as "create". With
            # read-before-edit the generated content is the FULL updated file, so apply it as an
            # update rather than hard-blocking with create_target_already_exists.
            if existed:
                effective_action = "update"

        if existed and content == current_text:
            return self._blocked("no_effective_change")

        change_id = "fc_" + rel_target.replace("/", "_").replace("\\", "_")
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            target.write_text(content, encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            # The write may have partially modified/created the file, so the failed target is
            # always a rollback target: delete it if it is new, restore original content if it
            # existed. Reuse the multi-file rollback helper with a single entry.
            rb = self._rollback_written_files([
                {"path": rel_target, "target": target, "existed": existed, "original_text": current_text}
            ])
            return {
                "status": "failed",
                "actual_file_changed": not rb["succeeded"],
                "changed_files": rb["unrestored_files"] if not rb["succeeded"] else [],
                "reasons": ["write_failed"],
                "errors": [str(exc) or exc.__class__.__name__],
                "partial_write_possible": not rb["succeeded"],
                "rollback_attempted": True,
                "rollback_succeeded": rb["succeeded"],
                "restored_files": rb["restored_files"],
                "unrestored_files": rb["unrestored_files"],
                "file_results": [{
                    "change_id": change_id,
                    "path": rel_target,
                    "status": "failed",
                    "reason": "write_failed",
                    "action_type": action_type,
                    "content_mode": parse.get("mode", "content"),
                    "mode": parse.get("mode", "content"),
                }],
                "summary": f"single-file apply failed during write to {rel_target}",
            }
        return {
            "status": "applied",
            "actual_file_changed": True,
            "changed_files": [rel_target],
            "file_results": [{
                "change_id": change_id,
                "path": rel_target,
                "status": "applied",
                "action_type": action_type,
                "content_mode": parse.get("mode", "content"),
                "mode": parse.get("mode", "content"),
            }],
            "summary": f"{effective_action} ({parse.get('mode', 'content')}) applied to {rel_target}",
        }

    def _apply_file_changes_safe(self, *, item: AtlasPlanItem, pool: AtlasPlanPool, file_changes: list) -> dict:
        preflight = self._preflight_file_changes(item=item, file_changes=file_changes)
        ready_results = preflight["file_results"]
        reasons = list(preflight["reasons"])
        if reasons:
            return {
                "status": "blocked",
                "actual_file_changed": False,
                "changed_files": [],
                "reasons": list(dict.fromkeys(["multi_file_preflight_failed", *reasons])),
                "file_results": [self._public_file_result(result) for result in ready_results],
                "summary": "multi-file preflight failed",
            }

        # Pre-apply quality gate (block/autonomous mode): reject the whole batch if any file is incomplete.
        if _quality_block_enforced(pool):
            quality_blocks = [
                (str(r.get("path") or ""), self._quality_block_reason(str(r.get("_content") or ""), file_path=str(r.get("path") or "")))
                for r in ready_results
            ]
            quality_blocks = [(path, reason) for path, reason in quality_blocks if reason]
            if quality_blocks:
                paths = [path for path, _reason in quality_blocks]
                reasons = list(dict.fromkeys(reason for _path, reason in quality_blocks))
                return {
                    "status": "blocked",
                    "actual_file_changed": False,
                    "changed_files": [],
                    "reasons": reasons,
                    "file_results": [self._public_file_result(result) for result in ready_results],
                    "summary": "blocked: incomplete generated content (" + ", ".join(paths) + ")",
                }

        changed_files: list[str] = []
        applied_results: list[dict] = []
        # Tracks written files with original state for rollback: {path, target, existed, original_text}
        written_entries: list[dict] = []

        for ready in ready_results:
            path = str(ready.get("path") or "")
            target = ready.get("_target")
            content = str(ready.get("_content") or "")
            existed = bool(ready.get("_existed"))
            original_text = str(ready.get("_original_text") or "")
            result = self._public_file_result(ready)
            # Register before the write so any partial write is included in rollback tracking.
            written_entries.append({"path": path, "target": target, "existed": existed, "original_text": original_text})
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
            except Exception as exc:  # noqa: BLE001
                result.update({"status": "failed", "reason": "write_failed", "error": str(exc) or exc.__class__.__name__})
                applied_results.append(result)
                rb = self._rollback_written_files(written_entries)
                return {
                    "status": "failed",
                    "actual_file_changed": not rb["succeeded"],
                    "changed_files": rb["unrestored_files"] if not rb["succeeded"] else [],
                    "reasons": ["write_failed"],
                    "errors": [str(exc) or exc.__class__.__name__],
                    "partial_write_possible": not rb["succeeded"],
                    "rollback_attempted": True,
                    "rollback_succeeded": rb["succeeded"],
                    "restored_files": rb["restored_files"],
                    "unrestored_files": rb["unrestored_files"],
                    "file_results": applied_results + [
                        self._public_file_result(rest)
                        for rest in ready_results[len(applied_results):]
                    ],
                    "summary": "multi-file apply failed during write",
                }
            result["status"] = "applied"
            applied_results.append(result)
            changed_files.append(path)

        return {
            "status": "applied",
            "actual_file_changed": bool(changed_files),
            "changed_files": changed_files,
            "file_results": applied_results,
            "summary": "multi-file apply completed",
        }

    def _rollback_written_files(self, written_entries: list[dict]) -> dict:
        """Attempt to undo writes in reverse order. New files are deleted; updated files are restored."""
        restored: list[str] = []
        unrestored: list[str] = []
        for entry in reversed(written_entries):
            path = entry["path"]
            target: Path = entry["target"]
            existed: bool = entry["existed"]
            original_text: str = entry["original_text"]
            try:
                if not existed:
                    target.unlink(missing_ok=True)
                else:
                    target.write_text(original_text, encoding="utf-8")
                restored.append(path)
            except Exception:  # noqa: BLE001
                unrestored.append(path)
        return {"succeeded": len(unrestored) == 0, "restored_files": restored, "unrestored_files": unrestored}

    def _preflight_file_changes(self, *, item: AtlasPlanItem, file_changes: list) -> dict:
        file_results: list[dict] = []
        reasons: list[str] = []
        raw_paths = [str(fc.get("path") or "").strip().replace("\\", "/") if isinstance(fc, dict) else "" for fc in file_changes]
        duplicate_paths = {p for p in raw_paths if p and raw_paths.count(p) > 1}

        for index, raw in enumerate(file_changes, start=1):
            if not isinstance(raw, dict):
                file_results.append({"change_id": f"fc_{index}", "path": "", "status": "blocked", "reason": "invalid_file_change"})
                reasons.append("invalid_file_change")
                continue
            change = dict(raw)
            path = str(change.get("path") or "").strip().replace("\\", "/")
            action_type = normalize_action_type(change.get("action_type") or (item.metadata or {}).get("action_type"))
            change_id = str(change.get("change_id") or f"fc_{index}").strip()
            content_mode = str(change.get("content_mode") or infer_content_mode(change) or "").strip()
            base_result = {"change_id": change_id, "path": path, "status": "ready", "action_type": action_type}
            if content_mode:
                base_result.update({"content_mode": content_mode, "mode": content_mode})

            if path in duplicate_paths:
                self._mark_blocked_file(file_results, reasons, base_result, "duplicate_file_change_path")
                continue
            target, path_reason = self._safe_target_path(path)
            if target is None:
                self._mark_blocked_file(file_results, reasons, base_result, path_reason or "unsafe_target_path")
                continue
            if action_type in FORBIDDEN_FILE_CHANGE_ACTIONS:
                self._mark_blocked_file(file_results, reasons, base_result, "forbidden_action_type")
                continue
            if action_type not in ALLOWED_FILE_CHANGE_ACTIONS:
                self._mark_blocked_file(file_results, reasons, base_result, "unsupported_action_type")
                continue
            existed = target.exists()
            current_text = ""
            if existed:
                try:
                    current_text = target.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    self._mark_blocked_file(file_results, reasons, base_result, "target_unreadable")
                    continue
            if action_type == "update" and not existed:
                self._mark_blocked_file(file_results, reasons, base_result, "update_target_missing")
                continue
            if not has_file_change_content(change):
                self._mark_blocked_file(file_results, reasons, base_result, "content_missing")
                continue

            parse = self._resolve_content_from_metadata(change, current_text=current_text, target_exists=existed)
            if parse["status"] != "ok":
                self._mark_blocked_file(file_results, reasons, base_result, parse["reason"])
                continue
            content = parse["content"]
            mode = str(parse.get("mode") or content_mode or "content")
            if len(content.encode("utf-8")) > _MAX_CONTENT_BYTES:
                self._mark_blocked_file(file_results, reasons, {**base_result, "content_mode": mode, "mode": mode}, "content_too_large")
                continue
            if existed and content == current_text:
                self._mark_blocked_file(file_results, reasons, {**base_result, "content_mode": mode, "mode": mode}, "no_effective_change")
                continue
            file_results.append({
                **base_result,
                "content_mode": mode,
                "mode": mode,
                "_target": target,
                "_content": content,
                "_existed": existed,
                "_original_text": current_text,
            })
        return {"file_results": file_results, "reasons": list(dict.fromkeys(reasons))}

    def _safe_target_path(self, rel_path: str) -> tuple[Path | None, str]:
        ok, reason, resolved = validate_protected_relative_path(rel_path, workspace_root=self.workspace_root)
        if not ok:
            return None, reason
        return resolved, ""

    def _resolve_content(self, item: AtlasPlanItem, *, current_text: str = "", target_exists: bool = False) -> dict:
        metadata = item.metadata or {}
        return self._resolve_content_from_metadata(metadata, current_text=current_text, target_exists=target_exists)

    def _resolve_content_from_metadata(self, metadata: dict, *, current_text: str = "", target_exists: bool = False) -> dict:
        patch_proposal = metadata.get("patch_proposal") if isinstance(metadata.get("patch_proposal"), dict) else {}

        # 1. Surgical string-replacement edits (old -> new), like Claude Code's Edit. Applied against
        #    the CURRENT file content; each old_string must appear exactly once. Preferred for existing
        #    files because it cannot clobber unrelated code.
        edits = metadata.get("edits") or patch_proposal.get("edits")
        if isinstance(edits, list) and edits:
            if not target_exists:
                return {"status": "blocked", "reason": "edits_require_existing_file"}
            applied = self._apply_string_edits(current_text, edits)
            if applied is None:
                return {"status": "blocked", "reason": "edit_not_applicable"}
            return {"status": "ok", "content": applied, "mode": "edits"}

        # 2. Append a block to the end of an existing file.
        append_text = metadata.get("append_content") or patch_proposal.get("append_content")
        if isinstance(append_text, str) and append_text:
            if not target_exists:
                return {"status": "blocked", "reason": "append_requires_existing_file"}
            sep = "" if current_text.endswith("\n") or not current_text else "\n"
            return {"status": "ok", "content": current_text + sep + append_text, "mode": "append"}

        # 3. Full-file content (greenfield write or full overwrite).
        proposed = metadata.get("proposed_content")
        if isinstance(proposed, str) and proposed:
            return {"status": "ok", "content": proposed, "mode": "full_content"}
        proposal_content = patch_proposal.get("proposed_content") if isinstance(patch_proposal, dict) else None
        if isinstance(proposal_content, str) and proposal_content:
            return {"status": "ok", "content": proposal_content, "mode": "full_content"}

        # 4. Unified diff — applied hunk-by-hunk against the current content when the file exists
        #    (precise, preserves unrelated lines); falls back to full-content extraction otherwise.
        for diff in (metadata.get("patch"), metadata.get("unified_diff_preview"),
                     patch_proposal.get("unified_diff_preview") if isinstance(patch_proposal, dict) else None):
            if isinstance(diff, str) and diff:
                if target_exists:
                    applied = self._apply_unified_diff_to_text(current_text, diff)
                    if applied is not None:
                        return {"status": "ok", "content": applied, "mode": "unified_diff"}
                parsed = self._content_from_unified_diff(diff)
                if parsed is None:
                    return {"status": "blocked", "reason": "unsupported_patch_format"}
                return {"status": "ok", "content": parsed, "mode": "diff_extract"}

        return {"status": "blocked", "reason": "content_missing"}

    @staticmethod
    def _review_precondition_block_reason(item: AtlasPlanItem) -> str:
        metadata = item.metadata if isinstance(item.metadata, dict) else {}
        patch_proposal = metadata.get("patch_proposal") if isinstance(metadata.get("patch_proposal"), dict) else {}
        proposal_metadata = patch_proposal.get("metadata") if isinstance(patch_proposal.get("metadata"), dict) else {}
        for key in ("self_review", "semantic_validation"):
            value = proposal_metadata.get(key)
            if isinstance(value, dict) and value and str(value.get("status") or "").lower() != "passed":
                return "proposal_review_not_passed"
        warnings = list(proposal_metadata.get("warnings") or patch_proposal.get("warnings") or [])
        if any(str(w) == "self_review_findings_unresolved" for w in warnings):
            return "proposal_review_not_passed"
        if proposal_metadata.get("patch_content_available") is False and patch_proposal:
            return "proposal_content_unavailable"
        if metadata.get("patch_proposal") and not is_patch_generation_success(metadata.get("patch_generation")):
            return "patch_generation_not_successful"
        return ""

    @staticmethod
    def _quality_block_reason(content: str, *, file_path: str = "") -> str:
        if is_placeholder_only_content(content, file_path=file_path):
            return "placeholder_only_content"
        if has_blocking_placeholder_content(content, file_path=file_path):
            return "placeholder_content_detected"
        return ""

    def _apply_string_edits(self, text: str, edits: list) -> str | None:
        """Apply a list of {old_string, new_string} replacements. Each old_string must match exactly
        once (uniqueness guard, like Claude Code's Edit). Returns None if any edit is not applicable."""
        result = text
        for edit in edits:
            if not isinstance(edit, dict):
                return None
            old = str(edit.get("old_string", ""))
            new = str(edit.get("new_string", ""))
            if old == "":
                return None
            count = result.count(old)
            if count == 1:
                result = result.replace(old, new, 1)
                continue
            flexible = self._replace_html_tag_gap_whitespace_once(result, old, new)
            if flexible is None:
                return None
            result = flexible
        return result

    @staticmethod
    def _replace_html_tag_gap_whitespace_once(text: str, old: str, new: str) -> str | None:
        if "<" not in old or ">" not in old or "<" not in new or ">" not in new:
            return None
        pattern = re.escape(old)
        # LLMs often insert or omit whitespace between adjacent HTML tags. Permit only that bounded
        # difference; all tag/text tokens must still match exactly and the match must remain unique.
        pattern = re.sub(r"(?<=>)\\\s+(?=<)", r"\\s*", pattern)
        matches = list(re.finditer(pattern, text))
        if len(matches) != 1:
            return None
        match = matches[0]
        return text[:match.start()] + new + text[match.end():]

    def _apply_unified_diff_to_text(self, original_text: str, diff_text: str) -> str | None:
        """Hunk-aware unified-diff application that PRESERVES lines outside the hunks. Validates context
        and deletion lines against the original; returns None on any mismatch (caller falls back)."""
        original = original_text.splitlines(keepends=True)
        result: list[str] = []
        cursor = 0
        saw_hunk = False
        lines = diff_text.splitlines()
        i = 0
        hunk_re = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
        while i < len(lines):
            m = hunk_re.match(lines[i])
            if not m:
                i += 1
                continue
            saw_hunk = True
            old_start = int(m.group(1))
            old_count = int(m.group(2) or "1")
            old_index = max(old_start - 1, 0)
            if old_start == 0 and old_count == 0:
                old_index = 0
            if old_index < cursor or old_index > len(original):
                return None
            result.extend(original[cursor:old_index])
            cursor = old_index
            i += 1
            while i < len(lines):
                hl = lines[i]
                if hunk_re.match(hl) or hl.startswith(("diff --git ", "--- ", "+++ ", "index ")):
                    break
                if hl.startswith("\\"):
                    i += 1
                    continue
                if hl.startswith(" "):
                    if cursor >= len(original) or original[cursor].rstrip("\r\n") != hl[1:]:
                        return None
                    result.append(original[cursor]); cursor += 1
                elif hl.startswith("-"):
                    if cursor >= len(original) or original[cursor].rstrip("\r\n") != hl[1:]:
                        return None
                    cursor += 1
                elif hl.startswith("+"):
                    result.append(hl[1:] + "\n")
                elif not hl.strip():
                    return None
                else:
                    return None
                i += 1
        if not saw_hunk:
            return None
        result.extend(original[cursor:])
        return "".join(result)

    def _content_from_unified_diff(self, patch: str) -> str | None:
        lines = patch.splitlines()
        content_lines: list[str] = []
        in_hunk = False
        for line in lines:
            if line.startswith("@@"):
                in_hunk = True
                continue
            if not in_hunk:
                continue
            if line.startswith("+") and not line.startswith("+++"):
                content_lines.append(line[1:])
            elif line.startswith(" "):
                content_lines.append(line[1:])
            elif line.startswith("-"):
                continue
            else:
                return None
        if not in_hunk:
            return None
        return "\n".join(content_lines) + ("\n" if content_lines else "")

    @staticmethod
    def _blocked(reason: str) -> dict:
        return {"status": "blocked", "actual_file_changed": False, "changed_files": [], "reasons": [reason]}

    @staticmethod
    def _mark_blocked_file(file_results: list[dict], reasons: list[str], base_result: dict, reason: str) -> None:
        blocked = dict(base_result)
        blocked.update({"status": "blocked", "reason": reason})
        file_results.append(blocked)
        if reason:
            reasons.append(reason)

    @staticmethod
    def _public_file_result(result: dict) -> dict:
        return {k: v for k, v in result.items() if not str(k).startswith("_")}
