"""Part A3 — opt-in in-run Project Twin build (re-run Twin effect), with negative control."""
from __future__ import annotations

from agent.twin_control_plane.pipeline_integration import (
    load_project_twin_store, refresh_project_twin, resolve_build_project_twin,
    try_project_twin_impact,
)


def test_build_flag_defaults_off_and_reversible(monkeypatch):
    monkeypatch.delenv("ATLAS_TWIN_BUILD_PROJECT", raising=False)
    assert resolve_build_project_twin() is False
    for on in ("1", "on", "true", "yes"):
        monkeypatch.setenv("ATLAS_TWIN_BUILD_PROJECT", on)
        assert resolve_build_project_twin() is True


def test_no_persistent_twin_before_first_build(tmp_path):
    # Negative control: with no prior build, the persistent store does not exist.
    assert load_project_twin_store(data_root=str(tmp_path), project_id="proj") is None


def test_refresh_builds_queryable_twin_with_real_impact(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    (project / "mod.py").write_text(
        "def helper():\n    return 1\n\n"
        "def feature():\n    return helper()\n", encoding="utf-8")
    store = refresh_project_twin(data_root=str(tmp_path), project_id="proj", project_path=str(project))
    assert store is not None
    # The persistent store is now loadable by a later run and yields real impact evidence.
    reloaded = load_project_twin_store(data_root=str(tmp_path), project_id="proj")
    assert reloaded is not None
    impact = try_project_twin_impact(project_id="proj",
                                     changed_refs=["py://mod.helper"], store=reloaded)
    assert impact is not None  # real Project Twin impact available on the re-run


def test_refresh_missing_path_returns_none(tmp_path):
    assert refresh_project_twin(data_root=str(tmp_path), project_id="p", project_path=str(tmp_path / "nope")) is None
