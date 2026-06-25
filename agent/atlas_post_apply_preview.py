from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from agent.atlas_action_type import normalize_action_type
from agent.atlas_file_safe_apply_executor import AtlasFileSafeApplyExecutor
from agent.atlas_plan_item_file_changes import (
    has_file_change_content,
    infer_content_mode,
    normalize_plan_item_file_changes,
)
from agent.atlas_plan_pool_schema import AtlasPlanItem


_SLICE_MARKERS = (
    "unrelated line(s) omitted",
    "full file is on disk",
    "rest of the file unchanged",
    "rest unchanged",
    "... omitted",
)


class AtlasPostApplyPreview:
    """Resolve Atlas file changes to post-apply file contents without writing files."""

    def __init__(self, *, workspace_root: str | Path = ".", allow_existing_full_content: bool = True):
        self.workspace_root = Path(workspace_root).resolve()
        self.allow_existing_full_content = bool(allow_existing_full_content)
        self._executor = AtlasFileSafeApplyExecutor(workspace_root=self.workspace_root)

    def preview_plan_item(self, *, item: AtlasPlanItem) -> dict[str, Any]:
        item_copy = deepcopy(item)
        normalize_plan_item_file_changes(item_copy)
        changes = self._changes_for_item(item_copy)
        post_apply_content_by_path: dict[str, str] = {}
        applied_changes: list[dict[str, Any]] = []
        blocked_changes: list[dict[str, Any]] = []
        warnings: list[str] = []
        reasons: list[str] = []

        for path in self._target_paths(item_copy, changes):
            current = self._read_current(path)
            if current["status"] == "ok":
                post_apply_content_by_path[path] = str(current["content"])

        duplicate_paths = {p for p in [str(c.get("path") or "").strip().replace("\\", "/") for c in changes] if p and [str(x.get("path") or "").strip().replace("\\", "/") for x in changes].count(p) > 1}
        for index, raw_change in enumerate(changes, start=1):
            change = dict(raw_change)
            path = str(change.get("path") or "").strip().replace("\\", "/")
            change_id = str(change.get("change_id") or f"fc_{index}").strip()
            action_type = normalize_action_type(change.get("action_type") or (item_copy.metadata or {}).get("action_type"))
            content_mode = str(change.get("content_mode") or infer_content_mode(change) or "").strip()
            base = {
                "change_id": change_id,
                "path": path,
                "action_type": action_type,
            }
            if content_mode:
                base["content_mode"] = content_mode

            if path in duplicate_paths:
                self._block(blocked_changes, reasons, base, "duplicate_file_change_path")
                continue
            target, path_reason = self._executor._safe_target_path(path)
            if target is None:
                self._block(blocked_changes, reasons, base, path_reason or "unsafe_target_path")
                continue
            existed = target.exists()
            current_text = ""
            if existed:
                try:
                    current_text = target.read_text(encoding="utf-8", errors="replace")
                    post_apply_content_by_path[path] = current_text
                except Exception:
                    self._block(blocked_changes, reasons, base, "target_unreadable")
                    continue

            policy_reason = self._full_content_policy_block(change, target_exists=existed)
            if policy_reason:
                self._block(blocked_changes, reasons, base, policy_reason)
                continue
            if action_type == "update" and not existed:
                self._block(blocked_changes, reasons, base, "update_target_missing")
                continue
            if not has_file_change_content(change):
                self._block(blocked_changes, reasons, base, "content_missing")
                continue

            resolved = self._executor._resolve_content_from_metadata(
                change,
                current_text=current_text,
                target_exists=existed,
            )
            if resolved["status"] != "ok":
                self._block(blocked_changes, reasons, base, str(resolved.get("reason") or "content_unresolved"))
                continue

            content = str(resolved.get("content") or "")
            mode = str(resolved.get("mode") or content_mode or "content")
            result = {**base, "content_mode": mode, "mode": mode}
            if existed and content == current_text:
                warnings.append("no_effective_change")
                applied_changes.append({**result, "status": "skipped", "reason": "no_effective_change"})
                post_apply_content_by_path[path] = current_text
                continue
            applied_changes.append({**result, "status": "previewed"})
            post_apply_content_by_path[path] = content

        unique_reasons = list(dict.fromkeys(reasons))
        return {
            "applied": bool(applied_changes) and not blocked_changes,
            "post_apply_content_by_path": post_apply_content_by_path,
            "applied_changes": applied_changes,
            "blocked_changes": blocked_changes,
            "warnings": list(dict.fromkeys(warnings)),
            "reasons": unique_reasons,
            "file_results": [*applied_changes, *blocked_changes],
        }

    def _changes_for_item(self, item: AtlasPlanItem) -> list[dict[str, Any]]:
        metadata = item.metadata if isinstance(item.metadata, dict) else {}
        file_changes = metadata.get("file_changes")
        if isinstance(file_changes, list) and file_changes:
            return [dict(change) for change in file_changes if isinstance(change, dict)]
        targets = [str(path).strip().replace("\\", "/") for path in (item.target_files or []) if str(path).strip()]
        if len(targets) != 1:
            return []
        action_type = normalize_action_type(metadata.get("action_type") or "update")
        change = dict(metadata)
        change.update({
            "path": targets[0],
            "action_type": action_type,
            "change_id": change.get("change_id") or f"fc_1_{targets[0].replace('/', '_')}",
        })
        if not str(change.get("content_mode") or "").strip():
            mode = infer_content_mode(change)
            if mode:
                change["content_mode"] = mode
        return [change]

    def _target_paths(self, item: AtlasPlanItem, changes: list[dict[str, Any]]) -> list[str]:
        paths = [str(path).strip().replace("\\", "/") for path in (item.target_files or []) if str(path).strip()]
        paths.extend(str(change.get("path") or "").strip().replace("\\", "/") for change in changes if str(change.get("path") or "").strip())
        return list(dict.fromkeys(paths))

    def _read_current(self, path: str) -> dict[str, Any]:
        target, reason = self._executor._safe_target_path(path)
        if target is None:
            return {"status": "blocked", "reason": reason or "unsafe_target_path"}
        if not target.exists():
            return {"status": "missing", "content": ""}
        try:
            return {"status": "ok", "content": target.read_text(encoding="utf-8", errors="replace")}
        except Exception:
            return {"status": "blocked", "reason": "target_unreadable"}

    def _full_content_policy_block(self, change: dict[str, Any], *, target_exists: bool) -> str:
        mode = str(change.get("content_mode") or infer_content_mode(change) or "").strip()
        proposed = change.get("proposed_content")
        patch_proposal = change.get("patch_proposal") if isinstance(change.get("patch_proposal"), dict) else {}
        proposal_content = patch_proposal.get("proposed_content") if isinstance(patch_proposal, dict) else None
        content = proposed if isinstance(proposed, str) else proposal_content
        is_full_content = mode in {"full_content", "content"} or isinstance(content, str)
        if not is_full_content:
            return ""
        if bool(change.get("current_file_content_sliced")):
            return "slice_full_content_forbidden"
        if isinstance(content, str) and self._contains_slice_marker(content):
            return "slice_marker_forbidden_in_full_content"
        if target_exists and not (self.allow_existing_full_content or bool(change.get("full_content_allowed"))):
            return "full_content_requires_policy"
        return ""

    @staticmethod
    def _contains_slice_marker(content: str) -> bool:
        lowered = str(content or "").lower()
        return any(marker in lowered for marker in _SLICE_MARKERS)

    @staticmethod
    def _block(blocked_changes: list[dict[str, Any]], reasons: list[str], base: dict[str, Any], reason: str) -> None:
        blocked_changes.append({**base, "status": "blocked", "reason": reason})
        reasons.append(reason)


def preview_plan_item_post_apply(
    *,
    item: AtlasPlanItem,
    workspace_root: str | Path = ".",
    allow_existing_full_content: bool = True,
) -> dict[str, Any]:
    return AtlasPostApplyPreview(
        workspace_root=workspace_root,
        allow_existing_full_content=allow_existing_full_content,
    ).preview_plan_item(item=item)

