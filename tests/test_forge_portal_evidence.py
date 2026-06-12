"""PFG-28 — Portal evidence to Candidate Evaluator / profile updater.

Proves: a measured runtime failure lowers the model's score, while a user discard alone
(no runtime evidence) is weak feedback that does not move the score.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.model_forge import (
    PortalRunEvidence,
    ProfileStore,
    ingest_portal_evidence,
)
from app.api.forge import router as forge_router


def _store(tmp_path):
    return ProfileStore(tmp_path / "profiles")


def test_runtime_failure_lowers_candidate_result(tmp_path):
    store = _store(tmp_path)
    # A prior success put web_app at 1.0.
    store.record_observation(model_id="m1", provider_id="local",
                             dimensions={"web_app": 1.0, "overall": 1.0}, source="portal_run")
    before = store.load_profile("local", "m1").dimension_scores["web_app"]
    # A measured runtime failure is strong and lowers the score.
    res = ingest_portal_evidence(store, PortalRunEvidence(
        installation_id="inst1", provider_id="local", model_id="m1",
        dimension="web_app", runtime_passed=False, user_decision="discard_and_exit",
    ))
    assert res.strength == "strong_runtime" and res.moved_score is True
    after = store.load_profile("local", "m1").dimension_scores["web_app"]
    assert after < before  # mean of 1.0 and 0.0 = 0.5


def test_user_discard_alone_does_not_prove_model_failure(tmp_path):
    store = _store(tmp_path)
    store.record_observation(model_id="m1", provider_id="local",
                             dimensions={"web_app": 0.9, "overall": 0.9}, source="portal_run")
    before = store.load_profile("local", "m1").dimension_scores["web_app"]
    # Discard with NO runtime evidence -> weak feedback only, score unchanged.
    res = ingest_portal_evidence(store, PortalRunEvidence(
        installation_id="inst1", provider_id="local", model_id="m1",
        dimension="web_app", runtime_passed=None, user_decision="discard_and_exit",
    ))
    assert res.strength == "weak_feedback" and res.moved_score is False
    after = store.load_profile("local", "m1").dimension_scores["web_app"]
    assert after == before == 0.9


def test_runtime_success_raises_score(tmp_path):
    store = _store(tmp_path)
    store.record_observation(model_id="m1", provider_id="local",
                             dimensions={"web_app": 0.0, "overall": 0.0}, source="portal_run")
    ingest_portal_evidence(store, PortalRunEvidence(
        installation_id="inst1", provider_id="local", model_id="m1",
        dimension="web_app", runtime_passed=True, user_decision="save_and_exit",
    ))
    assert store.load_profile("local", "m1").dimension_scores["web_app"] == 0.5


def _client(tmp_path):
    app = FastAPI()
    app.state.atlas_ca_data_root = str(tmp_path)
    app.include_router(forge_router)
    return TestClient(app)


def test_portal_evidence_endpoint(tmp_path):
    c = _client(tmp_path)
    r = c.post("/api/forge/portal-evidence", json={
        "installation_id": "inst1", "provider_id": "local", "model_id": "m1",
        "dimension": "web_app", "runtime_passed": False,
    })
    assert r.status_code == 200
    assert r.json()["strength"] == "strong_runtime"
    # Profile now exists with the lowered (0.0) score.
    profiles = c.get("/api/forge/profiles").json()["profiles"]
    assert profiles and profiles[0]["dimension_scores"]["web_app"] == 0.0
