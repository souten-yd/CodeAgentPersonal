from __future__ import annotations

import fnmatch
import re
from pathlib import Path

from agent.atlas_dev_tool_path import ensure_under_project, resolve_project_root, validate_relative_path
from agent.atlas_dev_tool_schema import AtlasFileOutlineResult, AtlasListFilesResult, AtlasProjectTreeResult

_EXCLUDED_DIRS = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', 'dist', 'build', '.next', '.cache', 'target', '.pytest_cache', 'ca_data'}


class AtlasProjectInspectionService:
    def _iter_files(self, root: Path):
        for path in root.rglob('*'):
            if any(part in _EXCLUDED_DIRS for part in path.parts):
                continue
            if path.is_file():
                yield path

    def project_tree(self, project_path: str, max_depth: int = 4, max_files: int = 500) -> AtlasProjectTreeResult:
        root = resolve_project_root(project_path)
        lines = []
        for path in self._iter_files(root):
            rel = path.relative_to(root)
            if len(rel.parts) > max_depth:
                continue
            lines.append(rel.as_posix())
            if len(lines) >= max_files:
                break
        return AtlasProjectTreeResult(tree=lines, metadata={"max_depth": max_depth})

    def list_files(self, project_path: str, glob: str = "", max_files: int = 1000) -> AtlasListFilesResult:
        root = resolve_project_root(project_path)
        out = []
        for path in self._iter_files(root):
            rel = path.relative_to(root).as_posix()
            if glob and not fnmatch.fnmatch(rel, glob):
                continue
            out.append(rel)
            if len(out) >= max_files:
                break
        return AtlasListFilesResult(files=out)

    def file_outline(self, project_path: str, relative_path: str, max_bytes: int = 200000) -> AtlasFileOutlineResult:
        root = resolve_project_root(project_path)
        safe_rel = validate_relative_path(relative_path)
        target = ensure_under_project(root, root / safe_rel)
        data = target.read_bytes()
        if b"\x00" in data:
            return AtlasFileOutlineResult(relative_path=safe_rel, warnings=["binary file skipped"])
        if len(data) > max_bytes:
            return AtlasFileOutlineResult(relative_path=safe_rel, warnings=["large file skipped"])
        text = data.decode('utf-8', errors='ignore')
        ext = target.suffix.lower()
        outline = []
        if ext == '.py':
            pattern = r'^(?:from\s+\S+\s+import\s+.+|import\s+.+|class\s+\w+|async\s+def\s+\w+|def\s+\w+)'
        elif ext in {'.js', '.ts', '.jsx', '.tsx'}:
            pattern = r'^(?:import\s+.+|export\s+.+|class\s+\w+|function\s+\w+)'
        elif ext == '.html':
            pattern = r'(<section[^>]*>|<script[^>]*>|<link[^>]*>|id="[^"]+")'
        elif ext == '.css':
            pattern = r'^\s*[^@\n][^{]+\{'
        elif ext == '.md':
            pattern = r'^#{1,6}\s.+'
        else:
            pattern = r'^$a'
        for line in text.splitlines():
            if re.search(pattern, line.strip() if ext != '.html' else line):
                outline.append(line.strip())
        return AtlasFileOutlineResult(relative_path=safe_rel, language=ext.lstrip('.'), outline=outline[:200])
