from __future__ import annotations

from pathlib import Path

from agent.patch_schema import PatchProposal


class PatchSafetyChecker:
    BLOCKED_DIR_NAMES = {".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build"}
    RESTRICTED_FILES = {
        "requirements.txt", "package.json", "Dockerfile", "docker-compose.yml",
        "pyproject.toml", "poetry.lock", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
    }
    ALLOWED_EXTENSIONS = {".py", ".md", ".txt", ".rst", ".sh", ".bash", ".zsh", ".yaml", ".yml", ".html", ".css", ".js", ".ts", ".tsx", ".jsx"}
    DENIED_EXTENSIONS = {".json", ".toml", ".lock", ".env", ".ini", ".cfg", ".conf", ".db", ".sqlite", ".png", ".jpg", ".jpeg", ".gif", ".webp"}

    def __init__(self, max_file_bytes: int = 200 * 1024, max_patch_bytes: int = 20_000, max_changed_lines: int = 120) -> None:
        self.max_file_bytes = max_file_bytes
        self.max_patch_bytes = max_patch_bytes
        self.max_changed_lines = max_changed_lines

    def evaluate(self, proposal: PatchProposal, project_path: Path, step_risk_level: str) -> tuple[bool, list[str]]:
        warnings: list[str] = []
        target = Path(proposal.target_file)
        resolved = target.resolve()
        project = project_path.resolve()
        if step_risk_level.lower() == "high":
            return False, ["high risk step is blocked"]
        if ".." in target.parts or (project not in resolved.parents and resolved != project):
            return False, ["target file is outside project_path"]
        if any(part in self.BLOCKED_DIR_NAMES for part in resolved.parts) or "ca_data" in resolved.parts:
            return False, ["target file is under blocked directory"]
        if resolved.name in self.RESTRICTED_FILES:
            return False, [f"restricted dependency-related file: {resolved.name}"]
        suffix = resolved.suffix.lower()
        if suffix in self.DENIED_EXTENSIONS or suffix not in self.ALLOWED_EXTENSIONS:
            return False, [f"unsupported extension: {suffix or '(none)'}"]
        if not resolved.exists() or resolved.stat().st_size > self.max_file_bytes:
            return False, ["target file missing or too large"]
        data = resolved.read_bytes()
        if b"\x00" in data[:1024]:
            return False, ["binary file update is blocked"]
        text = data.decode("utf-8", errors="ignore")

        if proposal.patch_type == "append":
            patch_bytes = len(proposal.proposed_content.encode("utf-8")) + len(proposal.unified_diff.encode("utf-8"))
            if patch_bytes > self.max_patch_bytes or not proposal.proposed_content.strip():
                return False, ["append patch is empty or too large"]
            if "CodeAgent Phase 7 patch note" not in proposal.proposed_content:
                return False, ["required patch marker is missing"]
            changed_lines = sum(1 for line in proposal.unified_diff.splitlines() if line.startswith("+") and not line.startswith("+++"))
            if changed_lines > self.max_changed_lines:
                return False, ["changed lines exceeds limit"]
            if any(line.startswith("-") and not line.startswith("---") for line in proposal.unified_diff.splitlines()):
                return False, ["delete operation detected in diff"]
            lowered = proposal.proposed_content.lower()
        elif proposal.patch_type == "replace_block":
            if not proposal.original_block.strip() or not proposal.replacement_block.strip():
                return False, ["original/replacement block is empty"]
            match_count = text.count(proposal.original_block)
            if match_count != 1:
                return False, ["replace_block match_count must be exactly 1"]
            if len(proposal.replacement_block.encode("utf-8")) > 20_000:
                return False, ["replacement block too large"]
            changed_lines = max(len(proposal.original_block.splitlines()), len(proposal.replacement_block.splitlines()))
            if changed_lines > self.max_changed_lines:
                return False, ["changed lines exceeds limit"]
            if len(proposal.original_block.splitlines()) > max(1, len(text.splitlines()) * 0.5):
                return False, ["replacement scope too large"]
            lowered = proposal.replacement_block.lower()
            diff_lines = proposal.unified_diff.splitlines()
            if not proposal.unified_diff.strip():
                return False, ["replace_block unified_diff is required"]
            add_lines = sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++"))
            del_lines = sum(1 for line in diff_lines if line.startswith("-") and not line.startswith("---"))
            if add_lines + del_lines == 0:
                return False, ["replace_block diff has no changed lines"]
            if del_lines > 0 and add_lines == 0:
                return False, ["delete-only replace patch is blocked"]
            if del_lines > (add_lines * 4 + 20):
                return False, ["replace_block deletion volume too high"]
        else:
            return False, ["unsupported patch_type"]

        if any(x in lowered for x in ["password", "token", "secret", "api_key"]):
            return False, ["patch content may include sensitive tokens"]
        if any(x in lowered for x in ["rm -rf", "subprocess", "os.system", "eval(", "exec("]):
            return False, ["dangerous pattern detected"]
        return True, warnings
