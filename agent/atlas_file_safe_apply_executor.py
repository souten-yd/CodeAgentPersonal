from __future__ import annotations

import re
from pathlib import Path

from agent.atlas_action_type import normalize_action_type
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool

_MAX_CONTENT_BYTES = 1024 * 1024

# Back-compat alias retained for callers that import the original name.
normalize_safe_apply_action_type = normalize_action_type


class AtlasFileSafeApplyExecutor:
    def __init__(self, *, workspace_root: str | Path = "."):
        self.workspace_root = Path(workspace_root).resolve()

    def apply_plan_item_safe(self, *, item: AtlasPlanItem, pool: AtlasPlanPool) -> dict:
        action_type = str((item.metadata or {}).get("action_type") or "").strip().lower()
        if action_type in {"delete", "run_command"}:
            return self._blocked("forbidden_action_type")
        if action_type not in {"update", "create"}:
            return self._blocked("unsupported_action_type")
        if len(item.target_files or []) != 1:
            return self._blocked("single_target_file_required")

        rel_target = str(item.target_files[0] or "").strip()
        target = self._safe_target_path(rel_target)
        if target is None:
            return self._blocked("unsafe_target_path")

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

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return {
            "status": "applied",
            "actual_file_changed": True,
            "changed_files": [rel_target],
            "summary": f"{effective_action} ({parse.get('mode', 'content')}) applied to {rel_target}",
        }

    def _safe_target_path(self, rel_path: str) -> Path | None:
        if not rel_path:
            return None
        p = Path(rel_path)
        if p.is_absolute() or ".." in p.parts:
            return None
        resolved = (self.workspace_root / p).resolve()
        try:
            resolved.relative_to(self.workspace_root)
        except ValueError:
            return None
        return resolved

    def _resolve_content(self, item: AtlasPlanItem, *, current_text: str = "", target_exists: bool = False) -> dict:
        metadata = item.metadata or {}
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
            if count != 1:
                return None
            result = result.replace(old, new, 1)
        return result

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
