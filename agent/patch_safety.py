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

    def __init__(self, max_file_bytes: int = 200 * 1024, max_patch_bytes: int = 20_000, max_changed_lines: int = 80) -> None:
        self.max_file_bytes = max_file_bytes
        self.max_patch_bytes = max_patch_bytes
        self.max_changed_lines = max_changed_lines

    def evaluate(self, proposal: PatchProposal, project_path: Path, step_risk_level: str) -> tuple[bool, list[str]]:
        warnings: list[str] = []
        target = Path(proposal.target_file)
        resolved = target.resolve()
        project = project_path.resolve()

        if step_risk_level.lower() == "high":
            warnings.append("high risk step is not applicable in Phase 7")
            return False, warnings

        if ".." in target.parts:
            warnings.append("target_file contains '..'")
            return False, warnings
        if project not in resolved.parents and resolved != project:
            warnings.append("target file is outside project_path")
            return False, warnings
        if any(part in self.BLOCKED_DIR_NAMES for part in resolved.parts):
            warnings.append("target file is under blocked directory")
            return False, warnings
        if "ca_data" in resolved.parts:
            warnings.append("ca_data path is blocked")
            return False, warnings
        if resolved.name in self.RESTRICTED_FILES:
            warnings.append(f"restricted dependency-related file in Phase 7: {resolved.name}")
            return False, warnings
        suffix = resolved.suffix.lower()
        if suffix in self.DENIED_EXTENSIONS:
            warnings.append(f"denied extension in Phase 7.5: {suffix}")
            return False, warnings
        if suffix not in self.ALLOWED_EXTENSIONS:
            warnings.append(f"unsupported extension for append patch MVP: {suffix or '(none)'}")
            return False, warnings
        if not resolved.exists():
            warnings.append("target file does not exist")
            return False, warnings
        if resolved.stat().st_size > self.max_file_bytes:
            warnings.append(f"target file is too large (> {self.max_file_bytes} bytes)")
            return False, warnings

        data = resolved.read_bytes()[:1024]
        if b"\x00" in data:
            warnings.append("binary file update is blocked")
            return False, warnings

        patch_bytes = len(proposal.proposed_content.encode("utf-8")) + len(proposal.unified_diff.encode("utf-8"))
        if patch_bytes > self.max_patch_bytes:
            warnings.append(f"patch size exceeds limit ({self.max_patch_bytes} bytes)")
            return False, warnings
        if not proposal.proposed_content.strip():
            warnings.append("proposed_content is empty")
            return False, warnings
        if proposal.patch_type != "append":
            warnings.append("only append patch_type is allowed in Phase 7.5")
            return False, warnings
        if "CodeAgent Phase 7 patch note" not in proposal.proposed_content:
            warnings.append("required patch marker is missing")
            return False, warnings

        changed_lines = sum(1 for line in proposal.unified_diff.splitlines() if line.startswith("+") and not line.startswith("+++"))
        if changed_lines > self.max_changed_lines:
            warnings.append(f"changed lines exceeds limit ({self.max_changed_lines})")
            return False, warnings

        lowered = proposal.proposed_content.lower()
        if any(x in lowered for x in ["password", "token", "secret", "api_key"]):
            warnings.append("patch content may include sensitive tokens")
            return False, warnings

        if any(line.startswith("-") and not line.startswith("---") for line in proposal.unified_diff.splitlines()):
            warnings.append("delete operation detected in diff")
            return False, warnings

        return True, warnings
