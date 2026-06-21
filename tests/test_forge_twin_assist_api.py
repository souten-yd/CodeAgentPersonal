from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.model_forge.twin_assist_contracts import TwinAssistEvaluationReport
from app.api.forge import router


def _client(tmp_path: Path):
    app = FastAPI()
    app.state.atlas_ca_data_root = str(tmp_path)
    app.include_router(router)
    return TestClient(app)


def _write_report(root: Path):
    report = TwinAssistEvaluationReport(run_id="twin_assist_abc123", provider_id="local", model_id="weak", status="passed", aggregate_scores={"mean_lift": 0.4}, recommended_twin_injection_level=4, evidence_refs=["proof.json"])
    path = root / "model_forge" / "twin_assist_runs" / report.run_id / "report.json"
    path.parent.mkdir(parents=True)
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return report


def test_cases_endpoint_lists_selectable_packs(tmp_path):
    response = _client(tmp_path).get("/api/forge/twin-assist/cases", params={"pack_id": "quick"})
    assert response.status_code == 200
    assert response.json()["pack_id"] == "quick"
    assert len(response.json()["cases"]) == 2
    assert _client(tmp_path).get("/api/forge/twin-assist/cases", params={"pack_id": "missing"}).status_code == 404


def test_run_read_and_record_profile_are_strictly_observational(tmp_path, monkeypatch):
    report = _write_report(tmp_path)
    client = _client(tmp_path)
    read = client.get(f"/api/forge/twin-assist/runs/{report.run_id}")
    assert read.status_code == 200
    recorded = client.post(f"/api/forge/twin-assist/runs/{report.run_id}/record-profile")
    assert recorded.status_code == 200
    assert recorded.json()["production_routing_changed"] is False
    assert recorded.json()["profile"]["recommended_twin_injection_level"] == 4
    assert client.get("/api/forge/twin-assist/runs/../secret").status_code in {404, 422}


def test_missing_and_invalid_run_ids_are_truthful(tmp_path):
    client = _client(tmp_path)
    assert client.get("/api/forge/twin-assist/runs/twin_assist_missing").status_code == 404
    assert client.get("/api/forge/twin-assist/runs/bad-id").status_code == 400
