from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.forge import router


def _client(tmp_path: Path) -> TestClient:
    app = FastAPI()
    app.state.atlas_ca_data_root = str(tmp_path)
    app.include_router(router)
    return TestClient(app)


def test_cases_lists_method_dimensions_and_can_filter(tmp_path):
    client = _client(tmp_path)
    body = client.get("/api/forge/evaluation/cases").json()
    assert "structured_output_fidelity" in body["dimensions"]
    filtered = client.get(
        "/api/forge/evaluation/cases", params={"dimension": "fallback_recovery"}
    ).json()
    assert filtered["dimensions"] == ["fallback_recovery"]
    assert filtered["packs"][0]["cases"]


def test_run_scores_persists_profile_and_reruns(tmp_path):
    client = _client(tmp_path)
    payload = {
        "provider_id": "local",
        "model_id": "model",
        "dimensions": ["structured_output_fidelity"],
        "results": [
            {
                "case_id": "sof_schema",
                "dimension": "structured_output_fidelity",
                "outcome": "passed",
                "evidence_refs": ["evidence/live-1"],
            },
            {
                "case_id": "sof_no_prose",
                "dimension": "structured_output_fidelity",
                "outcome": "failed",
                "evidence_refs": ["evidence/live-2"],
            },
        ],
    }
    run = client.post("/api/forge/evaluation/run", json=payload)
    assert run.status_code == 200
    record = run.json()
    assert record["scores"]["structured_output_fidelity"]["score"] == 0.3333
    profile = client.get(
        "/api/forge/evaluation/model-profile",
        params={"provider_id": "local", "model_id": "model"},
    ).json()
    assert profile["available"] is True
    assert profile["profile"]["dimension_scores"]["structured_output_fidelity"] == 0.3333

    rerun = client.post("/api/forge/evaluation/rerun", json={
        "run_id": record["run_id"],
        "dimensions": ["structured_output_fidelity"],
        "results": payload["results"],
    })
    assert rerun.status_code == 200
    assert rerun.json()["rerun_of"] == record["run_id"]


def test_unavailable_run_does_not_create_scored_profile(tmp_path):
    client = _client(tmp_path)
    response = client.post("/api/forge/evaluation/run", json={
        "provider_id": "local",
        "model_id": "unavailable",
        "dimensions": ["fallback_recovery"],
        "results": [{
            "case_id": "fb_recover",
            "dimension": "fallback_recovery",
            "outcome": "unavailable",
        }],
    })
    assert response.status_code == 200
    assert response.json()["scores"]["fallback_recovery"]["score"] is None
    profile = client.get(
        "/api/forge/evaluation/model-profile",
        params={"provider_id": "local", "model_id": "unavailable"},
    ).json()
    assert profile["available"] is False


def test_optimize_is_preview_only_and_strict_requests_reject_extras(tmp_path):
    client = _client(tmp_path)
    preview = client.post("/api/forge/evaluation/optimize", json={
        "provider_id": "local", "model_id": "model"
    })
    assert preview.status_code == 200
    assert preview.json()["status"] == "preview_not_applied"
    assert client.post("/api/forge/evaluation/optimize", json={
        "provider_id": "local", "model_id": "model", "apply": True
    }).status_code == 422


def test_unknown_dimension_and_missing_rerun_are_errors(tmp_path):
    client = _client(tmp_path)
    bad = client.post("/api/forge/evaluation/run", json={
        "provider_id": "local", "model_id": "model", "dimensions": ["unknown"]
    })
    assert bad.status_code == 400
    missing = client.post("/api/forge/evaluation/rerun", json={
        "run_id": "forge_eval_missing", "results": []
    })
    assert missing.status_code == 404
