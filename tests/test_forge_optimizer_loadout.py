from __future__ import annotations

from agent.model_forge.loadouts import LoadoutStore
from agent.model_forge.method_taxonomy import MethodVariant
from agent.model_forge.optimizer import ForgeOptimizer
from agent.model_forge.schema import ModelProfile


def test_optimizer_generates_role_assignments_and_method_loadout():
    profile = ModelProfile(
        model_id="weak",
        provider_id="local",
        sample_count=2,
        dimension_scores={"structured_output_fidelity": 0.2, "edit_intent_quality": 0.8},
        evidence_refs=["evidence/run"],
    )
    result = ForgeOptimizer().optimize(profile, provider_id="local", model_id="weak")
    assert result.status == "preview_not_applied"
    assert result.role_assignments[0].role == "coder"
    assert result.role_assignments[0].method_variant == MethodVariant.EDIT_INTENT_LIST
    assert result.role_assignments[1].method_variant == MethodVariant.REVIEW_ONLY
    assert result.loadout.method_preferences["coder"] == [MethodVariant.EDIT_INTENT_LIST]
    assert result.loadout.risky is False


def test_generated_loadout_roundtrips_store_without_applying(tmp_path):
    result = ForgeOptimizer().optimize(None, provider_id="local", model_id="new")
    store = LoadoutStore(tmp_path / "loadouts.json")
    saved = store.upsert(result.loadout.model_dump(mode="json"))
    loaded = store.get(saved.loadout_id)
    assert loaded == saved
    assert loaded.role_assignments[0].model_id == "new"
    assert not (tmp_path / "active_loadout.json").exists()
