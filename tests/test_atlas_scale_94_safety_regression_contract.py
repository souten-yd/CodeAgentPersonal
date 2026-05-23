from pathlib import Path


def test_level1_skeleton_has_no_subprocess_or_safe_apply_or_git_calls() -> None:
    content = Path('app/atlas/level1_guarded_execution.py').read_text(encoding='utf-8')
    assert 'import subprocess' not in content
    assert 'subprocess.run' not in content
    assert 'safe_apply' not in content
    assert ' git' not in content
