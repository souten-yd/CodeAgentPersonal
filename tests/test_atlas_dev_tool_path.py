from pathlib import Path

import pytest

from agent.atlas_dev_tool_path import ensure_under_project, resolve_project_root, validate_relative_path


def test_project_path_required():
    with pytest.raises(ValueError):
        resolve_project_root("")


def test_absolute_and_parent_rejected():
    with pytest.raises(ValueError):
        validate_relative_path('/etc/passwd')
    with pytest.raises(ValueError):
        validate_relative_path('../x')


def test_symlink_escape_rejected(tmp_path: Path):
    root = tmp_path / 'repo'
    root.mkdir()
    outside = tmp_path / 'outside.txt'
    outside.write_text('x', encoding='utf-8')
    link = root / 'link.txt'
    link.symlink_to(outside)
    with pytest.raises(ValueError):
        ensure_under_project(root, link)
