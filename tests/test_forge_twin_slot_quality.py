from agent.model_forge.execution_policy import ModelCapabilityProfile
from agent.model_forge.method_router import MethodRouter
from agent.model_forge.method_taxonomy import MethodVariant
from agent.model_forge.route_matrix import ChangeClass
from agent.model_forge.route_taxonomy import ForgeRoute
from agent.model_forge.twin_edit_slots import TwinEditSlot, TwinEditSlotResolver
from agent.model_forge.twin_slot_quality import TwinSlotQualityGate
from agent.twin_control_plane.contracts import ModelCapabilityMode
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.forge import router


def _slot(**updates):
    values = dict(slot_id="s", file="a.py", symbol_ref="one", operation="replace_range", start_line=1, end_line=2, anchor_text="def one():", anchor_occurrences=1, confidence=0.9)
    values.update(updates); return TwinEditSlot(**values)


def test_safe_slot_passes_and_ambiguous_out_of_range_broad_forbidden_low_confidence_block(tmp_path):
    (tmp_path / "a.py").write_text("def one():\n    return 1\n\ndef two():\n    return 2\n", encoding="utf-8")
    gate = TwinSlotQualityGate(max_range_lines=3)
    assert gate.evaluate(slot=_slot(), project_root=tmp_path).accepted
    assert "anchor_not_unique" in gate.evaluate(slot=_slot(anchor_occurrences=2), project_root=tmp_path).blocked_reasons
    assert "slot_range_out_of_bounds" in gate.evaluate(slot=_slot(end_line=99), project_root=tmp_path).blocked_reasons
    assert "slot_range_too_broad" in gate.evaluate(slot=_slot(end_line=4), project_root=tmp_path).blocked_reasons
    assert "forbidden_ref_overlap" in gate.evaluate(slot=_slot(), project_root=tmp_path, forbidden_refs=["a.py:one"]).blocked_reasons
    assert "slot_confidence_below_threshold" in gate.evaluate(slot=_slot(confidence=0.2), project_root=tmp_path).blocked_reasons


def test_resolver_drops_rejected_slot(tmp_path):
    (tmp_path / "a.py").write_text("def one():\n    return 1\n", encoding="utf-8")
    assert TwinEditSlotResolver().resolve(project_root=tmp_path, target_file="a.py", goal="change one", expected_symbols=["one"], forbidden_refs=["a.py:one"]) is None


def test_router_falls_back_when_slot_quality_rejected():
    profile = ModelCapabilityProfile(model_id="m", capability_scores={"large_file_editing": 0.2}, known_weaknesses=["large_file_editing"], mode=ModelCapabilityMode.WEAK_LOCAL, recommended_twin_assist_mode="twin_localized_slot", slot_quality_accepted=False)
    decision = MethodRouter().select(route=ForgeRoute.SLICED_IMPACT, change_class=ChangeClass.LARGE, profile=profile)
    assert decision.chain.primary == MethodVariant.ANCHORED_EDIT_BLOCK
    assert "slot_quality_blocked_uses_anchors" in decision.reasons


def test_slot_quality_api_returns_blocked_reasons(tmp_path):
    (tmp_path / "a.py").write_text("def one():\n    return 1\n", encoding="utf-8")
    app = FastAPI(); app.include_router(router)
    response = TestClient(app).post("/api/forge/twin-assist/slots/evaluate", json={"project_root": str(tmp_path), "slot": _slot(anchor_occurrences=2).model_dump(), "forbidden_refs": []})
    assert response.status_code == 200
    assert response.json()["accepted"] is False
    assert "anchor_not_unique" in response.json()["blocked_reasons"]
