"""Compatibility adapter for Atlas read-only inspection services.

Project and git inspection remain retained legacy implementations, but production
callers should depend on this Project Intelligence adapter rather than importing the
legacy services directly.
"""

from __future__ import annotations

from agent.atlas_dev_tool_schema import (
    AtlasFileOutlineResult,
    AtlasGitDiffResult,
    AtlasGitLsFilesResult,
    AtlasGitStatusResult,
    AtlasListFilesResult,
    AtlasProjectTreeResult,
)
from agent.atlas_git_inspection_service import AtlasGitInspectionService
from agent.atlas_project_inspection_service import AtlasProjectInspectionService


class AtlasInspectionAdapter:
    """Thin read-only adapter over retained project/git inspection implementations."""

    def __init__(
        self,
        *,
        git: AtlasGitInspectionService | None = None,
        project: AtlasProjectInspectionService | None = None,
    ) -> None:
        self._git = git or AtlasGitInspectionService()
        self._project = project or AtlasProjectInspectionService()

    def git_status(self, project_path: str) -> AtlasGitStatusResult:
        return self._git.git_status(project_path)

    def git_diff(
        self,
        project_path: str,
        relative_path: str = "",
        *,
        staged: bool = False,
        max_bytes: int = 200000,
    ) -> AtlasGitDiffResult:
        return self._git.git_diff(project_path, relative_path, staged=staged, max_bytes=max_bytes)

    def git_ls_files(
        self,
        project_path: str,
        *,
        max_files: int = 500,
        include_untracked: bool = True,
    ) -> AtlasGitLsFilesResult:
        return self._git.git_ls_files(
            project_path,
            max_files=max_files,
            include_untracked=include_untracked,
        )

    def project_tree(
        self,
        project_path: str,
        *,
        max_depth: int = 4,
        max_files: int = 500,
    ) -> AtlasProjectTreeResult:
        return self._project.project_tree(project_path, max_depth=max_depth, max_files=max_files)

    def list_files(
        self,
        project_path: str,
        *,
        glob: str = "",
        max_files: int = 1000,
    ) -> AtlasListFilesResult:
        return self._project.list_files(project_path, glob=glob, max_files=max_files)

    def file_outline(
        self,
        project_path: str,
        relative_path: str,
        *,
        max_bytes: int = 200000,
    ) -> AtlasFileOutlineResult:
        return self._project.file_outline(project_path, relative_path, max_bytes=max_bytes)
