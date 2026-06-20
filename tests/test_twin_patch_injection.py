"""Twin injection for the general/manual patch path (weak-model strengthening).

build_twin_generation_hints mirrors the autonomous orchestrator's pre-generation Twin consultation
so the per-item patch endpoint also injects the compiled Twin instruction (contracts + dependency
impact + Safe-Edit Briefing). The patch service consumes request.metadata["twin_generation_hints"].
"""
from types import SimpleNamespace

import agent.twin_control_plane.patch_injection as pi
from agent.twin_control_plane.patch_injection import build_twin_generation_hints, hints_from_evidence
from agent.twin_control_plane.pipeline_integration import PipelineMode


def _evidence(**over):
    base = {
        "available": True, "mode": "active", "route": "sliced_impact",
        "instruction_style": "concise", "twin_injection_level": 3, "policy_id": "p1",
        "compiled_instruction": "CONTRACTS: keep add(a,b) signature; IMPACT: test_calc.py depends on it",
        "instruction_id": "i1", "safe_edit_briefing": {"dependent_files": ["test_calc.py"]},
    }
    base.update(over)
    return base


def test_hints_from_evidence_maps_compiled_instruction():
    h = hints_from_evidence(_evidence())["twin_generation_hints"]
    assert h["twin_instruction"].startswith("CONTRACTS")
    assert h["twin_injection_level"] == 3
    assert h["impacted_dependent_files"] == ["test_calc.py"]
    assert h["twin_route"] == "sliced_impact"


def test_hints_from_evidence_empty_when_unavailable():
    assert hints_from_evidence({"available": False}) == {}
    assert hints_from_evidence({"available": True, "mode": "off", "compiled_instruction": "x"}) == {}


def test_hints_from_evidence_empty_without_compiled_instruction():
    assert hints_from_evidence(_evidence(compiled_instruction="")) == {}


def test_build_hints_returns_empty_when_pipeline_off(monkeypatch):
    monkeypatch.setattr(pi, "resolve_pipeline_mode", lambda *a, **k: PipelineMode.OFF)
    pool = SimpleNamespace(pool_id="pool1", project_path="", root_goal="g")
    item = SimpleNamespace(item_id="step_1", target_files=["calc.py"], metadata={})
    assert build_twin_generation_hints(data_root="ca_data", pool=pool, item=item) == {}


def test_build_hints_consults_twin_and_returns_hints(monkeypatch):
    captured = {}

    def fake_evidence(**kwargs):
        captured.update(kwargs)
        return _evidence()

    monkeypatch.setattr(pi, "resolve_pipeline_mode", lambda *a, **k: PipelineMode.ACTIVE)
    monkeypatch.setattr(pi, "resolve_twin_autobuild", lambda *a, **k: False)  # skip real build
    monkeypatch.setattr(pi, "resolve_build_project_twin", lambda *a, **k: False)
    monkeypatch.setattr(pi, "expand_changed_refs_to_symbols", lambda *a, **k: ["calc.add"])
    monkeypatch.setattr(pi, "try_project_twin_impact", lambda **k: {"callers": ["test_calc.py"]})
    monkeypatch.setattr(pi, "build_twin_pipeline_evidence", fake_evidence)

    pool = SimpleNamespace(pool_id="pool1", project_path="/proj", root_goal="add subtract")
    item = SimpleNamespace(item_id="step_1", target_files=["calc.py"], metadata={})
    out = build_twin_generation_hints(data_root="ca_data", pool=pool, item=item,
                                      request_metadata={"model_id": "qwen", "provider_id": "local"})
    hints = out["twin_generation_hints"]
    assert hints["twin_instruction"].startswith("CONTRACTS")
    # The item's target file flowed into the evidence consultation (impact-driven context).
    assert "calc.py" in list(captured.get("changed_refs") or [])
    assert captured.get("model_id") == "qwen"


def test_fresh_project_twin_builds_when_absent_and_refreshes_when_stale(tmp_path, monkeypatch):
    """fresh_project_twin builds on first encounter and refreshes when the project changed since the
    cached Twin was built — the staleness fix for greenfield-then-revise / existing-project revise."""
    import os
    import agent.twin_control_plane.patch_injection as mod

    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "a.py").write_text("x = 1\n", encoding="utf-8")
    db = tmp_path / "twin.sqlite3"
    refreshed = {"n": 0}
    loaded = {"n": 0}

    monkeypatch.setattr(mod, "_project_twin_db_path", lambda data_root, project_id: db)
    monkeypatch.setattr(mod, "refresh_project_twin",
                        lambda **k: (db.write_text("built", encoding="utf-8"), refreshed.__setitem__("n", refreshed["n"] + 1), "STORE")[-1])
    monkeypatch.setattr(mod, "load_project_twin_store",
                        lambda **k: (loaded.__setitem__("n", loaded["n"] + 1), "STORE")[-1])

    # 1) No DB yet -> build (refresh).
    assert mod.fresh_project_twin(data_root=str(tmp_path), project_id="p", project_path=str(proj)) == "STORE"
    assert refreshed["n"] == 1 and loaded["n"] == 0

    # 2) DB now older than a newly written source file -> refresh again.
    os.utime(db, (1, 1))  # make the twin DB ancient
    (proj / "b.py").write_text("y = 2\n", encoding="utf-8")
    mod.fresh_project_twin(data_root=str(tmp_path), project_id="p", project_path=str(proj))
    assert refreshed["n"] == 2

    # 3) DB newer than all sources -> reuse cached (load, no refresh).
    os.utime(db, None)  # bump twin DB mtime to now
    mod.fresh_project_twin(data_root=str(tmp_path), project_id="p", project_path=str(proj))
    assert refreshed["n"] == 2 and loaded["n"] == 1


def test_fresh_project_twin_none_for_missing_dir():
    from agent.twin_control_plane.patch_injection import fresh_project_twin
    assert fresh_project_twin(data_root="x", project_id="p", project_path="/no/such/dir") is None


def test_build_hints_never_raises_on_error(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("twin store unavailable")
    monkeypatch.setattr(pi, "resolve_pipeline_mode", lambda *a, **k: PipelineMode.ACTIVE)
    monkeypatch.setattr(pi, "build_twin_pipeline_evidence", boom)
    pool = SimpleNamespace(pool_id="p", project_path="/x", root_goal="g")
    item = SimpleNamespace(item_id="s", target_files=["a.py"], metadata={})
    assert build_twin_generation_hints(data_root="ca_data", pool=pool, item=item) == {}
