"""The Twin build must exclude .claude/worktrees (full repo copies) and virtualenvs.

The repo-scale evaluation found these duplicated every symbol/test and over-connected impact (a leaf
module reached ~900/1027 tests via worktree copies). This pins the exclusion.
"""
from __future__ import annotations

from agent.project_twin.module import DigitalTwinModuleImpl
from agent.project_twin.facade import ProjectIdentity, RefreshTwinRequest


def test_claude_worktrees_and_venv_are_excluded_from_build(tmp_path):
    proj = tmp_path / "proj"
    (proj).mkdir()
    (proj / "real.py").write_text("def real_fn():\n    return 1\n", encoding="utf-8")
    # A worktree copy and a virtualenv that must NOT be indexed.
    wt = proj / ".claude" / "worktrees" / "copy"
    wt.mkdir(parents=True)
    (wt / "real.py").write_text("def copied_fn():\n    return 2\n", encoding="utf-8")
    venv = proj / ".venv" / "lib"
    venv.mkdir(parents=True)
    (venv / "dep.py").write_text("def vendored_fn():\n    return 3\n", encoding="utf-8")

    mod = DigitalTwinModuleImpl(db_path=str(tmp_path / "twin.sqlite"))
    mod.refresh(RefreshTwinRequest(
        project=ProjectIdentity(project_id="p", workspace_id="default", project_path=str(proj)),
        full_rebuild=True))
    refs = {n.canonical_ref for n in mod._store.get_snapshot("p\x1fdefault").nodes}
    assert any("real_fn" in r for r in refs)  # the real symbol is indexed
    assert not any(".claude" in r or "copied_fn" in r for r in refs)  # worktree copy excluded
    assert not any(".venv" in r or "vendored_fn" in r for r in refs)  # virtualenv excluded
