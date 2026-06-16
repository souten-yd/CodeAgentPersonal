"""R3 — durable golden-patch store + advisory retrieval across runs."""
from __future__ import annotations

from agent.model_forge.golden_patch_retrieval import (
    GoldenPatch, GoldenPatchStore, RetrievalQuery,
)
from agent.model_forge.route_taxonomy import ForgeRoute


def _patch(pid="p1", outcome="accepted"):
    return GoldenPatch(patch_id=pid, task_category="autonomous_codegen",
                       route=ForgeRoute.DIRECT_PATCH, model_id="m1", affected_refs=["a.py"],
                       proof_outcome=outcome, summary="s", evidence_refs=["ledger:1"])


def test_accepted_patch_persists_and_reloads_as_index(tmp_path):
    store = GoldenPatchStore(tmp_path / "gp")
    assert store.add(_patch()) is True
    index = GoldenPatchStore(tmp_path / "gp").load_index()
    out = index.retrieve(RetrievalQuery(task_category="autonomous_codegen",
                                        route=ForgeRoute.DIRECT_PATCH, model_id="m1",
                                        affected_refs=["a.py"]))
    assert out and out[0].patch.patch_id == "p1"
    assert out[0].advisory is True


def test_non_accepted_patch_is_not_stored(tmp_path):
    store = GoldenPatchStore(tmp_path / "gp")
    assert store.add(_patch(outcome="needs_repair")) is False
    assert len(GoldenPatchStore(tmp_path / "gp").load_index()) == 0


def test_store_is_idempotent_by_patch_id(tmp_path):
    store = GoldenPatchStore(tmp_path / "gp")
    store.add(_patch("p1"))
    store.add(_patch("p1"))
    assert len(GoldenPatchStore(tmp_path / "gp").load_index()) == 1


def test_missing_store_loads_empty_index(tmp_path):
    assert len(GoldenPatchStore(tmp_path / "gp").load_index()) == 0
