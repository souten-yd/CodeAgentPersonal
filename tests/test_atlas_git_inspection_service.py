from pathlib import Path

from agent.atlas_git_inspection_service import AtlasGitInspectionService


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / 'repo'
    repo.mkdir()
    import subprocess
    subprocess.run(['git', 'init'], cwd=repo, check=True, capture_output=True)
    (repo/'a.txt').write_text('hello\n', encoding='utf-8')
    subprocess.run(['git', 'add', 'a.txt'], cwd=repo, check=True)
    subprocess.run(['git', 'commit', '-m', 'init'], cwd=repo, check=True, capture_output=True)
    return repo


def test_git_status_diff_ls_files_read_only(tmp_path: Path):
    repo = _repo(tmp_path)
    svc = AtlasGitInspectionService()
    (repo/'a.txt').write_text('changed\n', encoding='utf-8')
    (repo/'b.txt').write_text('new\n', encoding='utf-8')
    status = svc.git_status(str(repo))
    assert status.branch.startswith('##')
    diff = svc.git_diff(str(repo), 'a.txt')
    assert 'a.txt' in diff.diff
    ls = svc.git_ls_files(str(repo), include_untracked=True)
    assert 'a.txt' in ls.tracked_files
    assert 'b.txt' in ls.untracked_files
