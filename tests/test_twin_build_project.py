"""Part A3 — opt-in in-run Project Twin build (re-run Twin effect), with negative control."""
from __future__ import annotations

from agent.twin_control_plane.pipeline_integration import (
    ensure_project_twin, expand_changed_refs_to_symbols, load_project_twin_store,
    refresh_project_twin, resolve_build_project_twin, resolve_twin_autobuild,
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


def test_autobuild_defaults_on_and_reversible(monkeypatch):
    # Auto-build is the default (so the dependency-awareness works without extra config), and is
    # reversible via ATLAS_TWIN_AUTOBUILD.
    monkeypatch.delenv("ATLAS_TWIN_AUTOBUILD", raising=False)
    assert resolve_twin_autobuild() is True
    for off in ("0", "off", "false", "no"):
        monkeypatch.setenv("ATLAS_TWIN_AUTOBUILD", off)
        assert resolve_twin_autobuild() is False
    for on in ("1", "on", "true", "yes", ""):
        monkeypatch.setenv("ATLAS_TWIN_AUTOBUILD", on)
        assert resolve_twin_autobuild() is True


def test_ensure_builds_when_absent_then_loads(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    (project / "mod.py").write_text(
        "def helper():\n    return 1\n\ndef feature():\n    return helper()\n", encoding="utf-8")
    # Absent -> builds from source (impact available THIS run, not only a later one).
    store = ensure_project_twin(data_root=str(tmp_path), project_id="proj", project_path=str(project))
    assert store is not None
    impact = try_project_twin_impact(project_id="proj", changed_refs=["py://mod.helper"], store=store)
    assert impact is not None
    # Present -> loads the existing store without rebuilding.
    again = ensure_project_twin(data_root=str(tmp_path), project_id="proj", project_path=str(project))
    assert again is not None


def test_ensure_missing_path_returns_none(tmp_path):
    assert ensure_project_twin(data_root=str(tmp_path), project_id="p", project_path=str(tmp_path / "nope")) is None


def test_changed_file_expands_to_symbols_and_finds_cross_file_callers(tmp_path):
    # The loop knows changed FILES, but Twin impact seeds on SYMBOLS — a bare file ref yields no
    # callers. Expansion maps the file to its symbols so cross-file dependents are found.
    project = tmp_path / "proj"
    project.mkdir()
    (project / "core.py").write_text("def target():\n    return 1\n", encoding="utf-8")
    (project / "caller_a.py").write_text("from core import target\ndef use_a():\n    return target() + 1\n", encoding="utf-8")
    (project / "caller_b.py").write_text("import core\ndef use_b():\n    return core.target() * 2\n", encoding="utf-8")
    store = ensure_project_twin(data_root=str(tmp_path), project_id="proj", project_path=str(project))

    # Bare file ref alone -> no callers (the motivating bug).
    bare = try_project_twin_impact(project_id="proj", changed_refs=["core.py"], store=store)
    assert not (bare.direct_impacts + bare.transitive_impacts)

    # Expanded -> the symbol ref is added and cross-file callers are found.
    expanded = expand_changed_refs_to_symbols(store, "proj", ["core.py"])
    assert "py://core.py#target" in expanded
    impact = try_project_twin_impact(project_id="proj", changed_refs=expanded, store=store)
    callers = {i.canonical_ref for i in (impact.direct_impacts + impact.transitive_impacts)}
    assert "py://caller_a.py#use_a" in callers
    assert "py://caller_b.py#use_b" in callers


def test_expand_passes_through_symbol_refs_and_is_safe_without_store():
    # Symbol-level refs are unchanged; no store -> returns the originals (never raises).
    assert expand_changed_refs_to_symbols(None, "p", ["py://a.py#f"]) == ["py://a.py#f"]
    assert expand_changed_refs_to_symbols(None, "", ["x.py"]) == ["x.py"]
