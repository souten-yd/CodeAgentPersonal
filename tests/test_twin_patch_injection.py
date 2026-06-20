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


def test_build_hints_never_raises_on_error(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("twin store unavailable")
    monkeypatch.setattr(pi, "resolve_pipeline_mode", lambda *a, **k: PipelineMode.ACTIVE)
    monkeypatch.setattr(pi, "build_twin_pipeline_evidence", boom)
    pool = SimpleNamespace(pool_id="p", project_path="/x", root_goal="g")
    item = SimpleNamespace(item_id="s", target_files=["a.py"], metadata={})
    assert build_twin_generation_hints(data_root="ca_data", pool=pool, item=item) == {}
