from __future__ import annotations

from pathlib import Path
from typing import Any

from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool

_MAX_CONTENT_BYTES = 1024 * 1024
_FORBIDDEN_ACTION_TYPES = {
    "delete",
    "run_command",
    "execute",
    "shell",
    "arbitrary command",
    "external fetch",
    "raw source serving",
}
_SUPPORTED_ACTION_TYPES = {"create", "update"}
_PROTECTED_PATH_PREFIXES = {".git", ".github/workflows", "ca_data"}


class AtlasFileSafeApplyExecutor:
    def __init__(self, *, workspace_root: str | Path = "."):
        self.workspace_root = Path(workspace_root).resolve()

    def apply_plan_item_safe(self, *, item: AtlasPlanItem, pool: AtlasPlanPool) -> dict:
        file_changes = (item.metadata or {}).get("file_changes")
        if isinstance(file_changes, list) and file_changes:
            return self._apply_multi_file_plan_item_safe(item=item, file_changes=file_changes)
        if len(item.target_files or []) > 1:
            return self._blocked("multi_file_item_requires_file_changes")
        action_type = str((item.metadata or {}).get("action_type") or "").strip().lower()
        if action_type in _FORBIDDEN_ACTION_TYPES:
            return self._blocked("forbidden_action_type")
        if action_type not in _SUPPORTED_ACTION_TYPES:
            return self._blocked("unsupported_action_type")
        if len(item.target_files or []) != 1:
            return self._blocked("single_target_file_required")

        rel_target = str(item.target_files[0] or "").strip()
        target = self._safe_target_path(rel_target)
        if target is None:
            return self._blocked("unsafe_target_path")
        if self._is_protected_path(rel_target):
            return self._blocked("protected_path")

        file_result = self._preflight_file_change({"path": rel_target, **(item.metadata or {}), "action_type": action_type})
        if file_result["status"] != "ready":
            return self._blocked(str(file_result.get("reason") or "preflight_failed"))

        content = str(file_result["content"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return {
            "status": "applied",
            "actual_file_changed": True,
            "changed_files": [rel_target],
            "summary": f"{action_type} applied to {rel_target}",
            "file_results": [
                {
                    "path": rel_target,
                    "status": "applied",
                    "action_type": action_type,
                    "mode": str(file_result.get("mode") or "full_content"),
                }
            ],
            "reasons": [],
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

    def _apply_multi_file_plan_item_safe(self, *, item: AtlasPlanItem, file_changes: list[Any]) -> dict:
        preflight_results = []
        ready_results = []
        for raw_change in file_changes:
            if not isinstance(raw_change, dict):
                result = {"path": "", "status": "blocked", "reason": "invalid_file_change"}
            else:
                result = self._preflight_file_change(raw_change)
            public_result = {k: v for k, v in result.items() if k != "content" and k != "target"}
            preflight_results.append(public_result)
            if result.get("status") == "ready":
                ready_results.append(result)

        if len(ready_results) != len(file_changes):
            return {
                "status": "blocked",
                "actual_file_changed": False,
                "changed_files": [],
                "summary": "multi-file preflight failed",
                "reasons": ["multi_file_preflight_failed"],
                "file_results": preflight_results,
            }

        changed_files: list[str] = []
        file_results: list[dict] = []
        for result in ready_results:
            target = result["target"]
            content = str(result["content"])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            rel_path = str(result["path"])
            changed_files.append(rel_path)
            file_results.append(
                {
                    "path": rel_path,
                    "status": "applied",
                    "action_type": str(result.get("action_type") or ""),
                    "mode": str(result.get("mode") or "full_content"),
                }
            )
        return {
            "status": "applied",
            "actual_file_changed": bool(changed_files),
            "changed_files": changed_files,
            "summary": "multi-file apply completed",
            "file_results": file_results,
            "reasons": [],
        }

    def _preflight_file_change(self, change: dict) -> dict:
        rel_target = str(change.get("path") or "").strip()
        action_type = str(change.get("action_type") or "").strip().lower()
        base = {"path": rel_target, "status": "blocked", "action_type": action_type}
        if not rel_target:
            return {**base, "reason": "target_file_missing"}
        target = self._safe_target_path(rel_target)
        if target is None:
            return {**base, "reason": "unsafe_target_path"}
        if self._is_protected_path(rel_target):
            return {**base, "reason": "protected_path"}
        if action_type in _FORBIDDEN_ACTION_TYPES:
            return {**base, "reason": "forbidden_action_type"}
        if action_type not in _SUPPORTED_ACTION_TYPES:
            return {**base, "reason": "unsupported_action_type"}

        existed = target.exists()
        if action_type == "update" and not existed:
            return {**base, "reason": "update_target_missing"}
        if action_type == "create" and existed:
            return {**base, "reason": "create_target_already_exists"}

        parse = self._resolve_change_content(change, target=target)
        if parse["status"] != "ok":
            return {**base, "reason": parse["reason"]}
        content = str(parse["content"])
        if len(content.encode("utf-8")) > _MAX_CONTENT_BYTES:
            return {**base, "reason": "content_too_large"}
        if existed and target.read_text(encoding="utf-8") == content:
            return {**base, "reason": "no_effective_change", "mode": parse.get("mode", "full_content")}
        return {
            "path": rel_target,
            "status": "ready",
            "action_type": action_type,
            "mode": parse.get("mode", "full_content"),
            "target": target,
            "content": content,
        }

    def _resolve_content(self, item: AtlasPlanItem) -> dict:
        metadata = item.metadata or {}
        return self._resolve_change_content(metadata, target=None)

    def _resolve_change_content(self, metadata: dict, *, target: Path | None) -> dict:
        patch = metadata.get("patch")
        proposed = metadata.get("proposed_content")
        if isinstance(proposed, str) and proposed:
            return {"status": "ok", "content": proposed, "mode": "full_content"}

        edits = metadata.get("edits")
        if isinstance(edits, list) and edits:
            if target is None or not target.exists():
                return {"status": "blocked", "reason": "update_target_missing"}
            return self._content_from_edits(target.read_text(encoding="utf-8"), edits)

        append_content = metadata.get("append_content")
        if isinstance(append_content, str) and append_content:
            base = target.read_text(encoding="utf-8") if target is not None and target.exists() else ""
            return {"status": "ok", "content": base + append_content, "mode": "append_content"}

        patch_proposal = metadata.get("patch_proposal") or {}
        proposal_content = patch_proposal.get("proposed_content") if isinstance(patch_proposal, dict) else None
        if isinstance(proposal_content, str) and proposal_content:
            return {"status": "ok", "content": proposal_content, "mode": "full_content"}

        if isinstance(patch, str) and patch:
            parsed = self._content_from_unified_diff(patch)
            if parsed is None:
                return {"status": "blocked", "reason": "unsupported_patch_format"}
            return {"status": "ok", "content": parsed, "mode": "patch"}

        unified_diff_preview = metadata.get("unified_diff_preview")
        if isinstance(unified_diff_preview, str) and unified_diff_preview:
            parsed = self._content_from_unified_diff(unified_diff_preview)
            if parsed is None:
                return {"status": "blocked", "reason": "unsupported_patch_format"}
            return {"status": "ok", "content": parsed, "mode": "patch"}

        proposal_diff = patch_proposal.get("unified_diff_preview") if isinstance(patch_proposal, dict) else None
        if isinstance(proposal_diff, str) and proposal_diff:
            parsed = self._content_from_unified_diff(proposal_diff)
            if parsed is None:
                return {"status": "blocked", "reason": "unsupported_patch_format"}
            return {"status": "ok", "content": parsed, "mode": "patch"}

        return {"status": "blocked", "reason": "content_missing"}

    def _content_from_edits(self, current: str, edits: list) -> dict:
        content = current
        for edit in edits:
            if not isinstance(edit, dict):
                return {"status": "blocked", "reason": "unsupported_edits_format"}
            old = edit.get("old_string")
            new = edit.get("new_string")
            if not isinstance(old, str) or old == "" or not isinstance(new, str):
                return {"status": "blocked", "reason": "unsupported_edits_format"}
            if content.count(old) != 1:
                return {"status": "blocked", "reason": "edit_old_string_not_unique"}
            content = content.replace(old, new, 1)
        return {"status": "ok", "content": content, "mode": "edits"}

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

    def _is_protected_path(self, rel_path: str) -> bool:
        normalized = rel_path.replace("\\", "/").strip("/")
        return any(normalized == prefix or normalized.startswith(f"{prefix}/") for prefix in _PROTECTED_PATH_PREFIXES)

    @staticmethod
    def _blocked(reason: str) -> dict:
        return {"status": "blocked", "actual_file_changed": False, "changed_files": [], "reasons": [reason], "file_results": []}
