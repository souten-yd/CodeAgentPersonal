from __future__ import annotations

import subprocess

from agent.atlas_dev_tool_path import resolve_project_root, validate_relative_path
from agent.atlas_dev_tool_schema import AtlasGitDiffResult, AtlasGitLsFilesResult, AtlasGitStatusResult


class AtlasGitInspectionService:
    timeout_seconds = 10

    def _run(self, project_path: str, args: list[str]) -> subprocess.CompletedProcess[str]:
        root = resolve_project_root(project_path)
        return subprocess.run(
            args,
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
            shell=False,
            check=False,
        )

    def git_status(self, project_path: str) -> AtlasGitStatusResult:
        proc = self._run(project_path, ["git", "status", "--short", "--branch"])
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        branch = lines[0] if lines else ""
        return AtlasGitStatusResult(branch=branch, entries=lines[1:] if len(lines) > 1 else [], metadata={"returncode": proc.returncode})

    def git_diff(self, project_path: str, relative_path: str = "", staged: bool = False, max_bytes: int = 200000) -> AtlasGitDiffResult:
        safe_path = validate_relative_path(relative_path)
        args = ["git", "diff"]
        if staged:
            args.append("--cached")
        args.extend(["--no-ext-diff", "--"])
        if safe_path:
            args.append(safe_path)
        proc = self._run(project_path, args)
        raw = proc.stdout
        encoded = raw.encode("utf-8", errors="ignore")
        truncated = len(encoded) > max_bytes
        diff = encoded[:max_bytes].decode("utf-8", errors="ignore") if truncated else raw
        warnings = ["diff truncated by max_bytes"] if truncated else []
        return AtlasGitDiffResult(relative_path=safe_path, staged=staged, diff=diff, truncated=truncated, warnings=warnings, metadata={"returncode": proc.returncode})

    def git_ls_files(self, project_path: str, max_files: int = 500, include_untracked: bool = True) -> AtlasGitLsFilesResult:
        tracked = self._run(project_path, ["git", "ls-files"]).stdout.splitlines()
        untracked: list[str] = []
        if include_untracked:
            untracked = self._run(project_path, ["git", "ls-files", "--others", "--exclude-standard"]).stdout.splitlines()
        return AtlasGitLsFilesResult(
            tracked_files=tracked[:max_files],
            untracked_files=untracked[:max_files],
            metadata={"tracked_total": len(tracked), "untracked_total": len(untracked)},
        )
