from __future__ import annotations

import difflib
from pathlib import Path
from uuid import uuid4

from agent.patch_schema import PatchProposal


class PatchGenerator:
    HASH_COMMENT_EXTENSIONS = {".py", ".sh", ".bash", ".zsh", ".yaml", ".yml"}
    HTML_COMMENT_EXTENSIONS = {".md", ".txt", ".rst", ".html"}
    BLOCK_COMMENT_EXTENSIONS = {".css", ".js", ".ts", ".tsx", ".jsx"}
    ALLOWED_EXTENSIONS = HASH_COMMENT_EXTENSIONS | HTML_COMMENT_EXTENSIONS | BLOCK_COMMENT_EXTENSIONS

    def __init__(self, max_file_bytes: int = 200 * 1024) -> None:
        self.max_file_bytes = max_file_bytes

    def generate_append_patch(self, run_id: str, plan_id: str, step_id: str, step_title: str, step_description: str, risk_level: str, target_file: Path) -> PatchProposal:
        content = target_file.read_text(encoding="utf-8")
        if target_file.stat().st_size > self.max_file_bytes:
            raise ValueError("target file too large")
        suffix = target_file.suffix.lower()
        if suffix not in self.ALLOWED_EXTENSIONS:
            raise ValueError(f"unsupported file extension for append patch: {suffix or '(none)'}")

        append_block = "\n" + self._build_append_block(suffix, plan_id, step_id, step_title) + "\n"
        new_content = content + append_block
        diff = "\n".join(
            difflib.unified_diff(
                content.splitlines(),
                new_content.splitlines(),
                fromfile=str(target_file),
                tofile=str(target_file),
                lineterm="",
            )
        )
        return PatchProposal(
            patch_id=f"patch_{uuid4().hex[:12]}",
            run_id=run_id,
            plan_id=plan_id,
            step_id=step_id,
            target_file=str(target_file),
            status="proposed",
            patch_type="append",
            original_preview=content[-400:],
            proposed_content=append_block,
            unified_diff=diff,
            risk_level=risk_level,
            apply_allowed=False,
            metadata={"generator": "phase7_mvp_append"},
        )

    def _build_append_block(self, suffix: str, plan_id: str, step_id: str, step_title: str) -> str:
        if suffix in self.HASH_COMMENT_EXTENSIONS:
            return "\n".join([
                "# CodeAgent Phase 7 patch note",
                f"# plan_id: {plan_id}",
                f"# step_id: {step_id}",
                f"# task: {step_title}",
            ])
        if suffix in self.HTML_COMMENT_EXTENSIONS:
            return "\n".join([
                "<!-- CodeAgent Phase 7 patch note",
                f"plan_id: {plan_id}",
                f"step_id: {step_id}",
                f"task: {step_title}",
                "-->",
            ])
        return "\n".join([
            "/* CodeAgent Phase 7 patch note",
            f" * plan_id: {plan_id}",
            f" * step_id: {step_id}",
            f" * task: {step_title}",
            " */",
        ])
