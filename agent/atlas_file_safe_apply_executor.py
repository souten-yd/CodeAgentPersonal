from __future__ import annotations

from pathlib import Path

from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool

_MAX_CONTENT_BYTES = 1024 * 1024


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

        parse = self._resolve_content(item)
        if parse["status"] != "ok":
            return self._blocked(parse["reason"])
        content = parse["content"]
        if len(content.encode("utf-8")) > _MAX_CONTENT_BYTES:
            return self._blocked("content_too_large")

        existed = target.exists()
        if action_type == "update":
            if not existed:
                return self._blocked("update_target_missing")
        elif action_type == "create":
            if existed:
                return self._blocked("create_target_already_exists")

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return {
            "status": "applied",
            "actual_file_changed": True,
            "changed_files": [rel_target],
            "summary": f"{action_type} applied to {rel_target}",
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

    def _resolve_content(self, item: AtlasPlanItem) -> dict:
        metadata = item.metadata or {}
        patch = metadata.get("patch")
        proposed = metadata.get("proposed_content")
        if isinstance(proposed, str) and proposed:
            return {"status": "ok", "content": proposed}

        patch_proposal = metadata.get("patch_proposal") or {}
        proposal_content = patch_proposal.get("proposed_content") if isinstance(patch_proposal, dict) else None
        if isinstance(proposal_content, str) and proposal_content:
            return {"status": "ok", "content": proposal_content}

        if isinstance(patch, str) and patch:
            parsed = self._content_from_unified_diff(patch)
            if parsed is None:
                return {"status": "blocked", "reason": "unsupported_patch_format"}
            return {"status": "ok", "content": parsed}
        return {"status": "blocked", "reason": "content_missing"}

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
