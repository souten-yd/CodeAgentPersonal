import os
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.model_forge.twin_readiness import TwinReadinessEvaluator
from agent.model_forge.twin_readiness_contracts import TwinReadinessRequest
from app.api.forge import router


def test_missing_snapshot_is_unavailable_and_caps_slot(tmp_path):
    report = TwinReadinessEvaluator().evaluate(TwinReadinessRequest(project_id="p", project_path=str(tmp_path), changed_refs=["a.py"], metadata={"resolved_refs": ["a.py"]}))
    assert report.readiness_level == "unavailable"
    assert report.overall_score is None
    assert report.recommended_max_assist_mode == "constraints_and_refs"
    assert "twin_snapshot_unavailable" in report.blocked_reasons


def test_stale_snapshot_and_impact_budget_are_warnings(tmp_path):
    source = tmp_path / "a.py"; source.write_text("x=1", encoding="utf-8")
    snapshot = tmp_path / "twin.db"; snapshot.write_text("db", encoding="utf-8")
    os.utime(snapshot, (1, 1))
    report = TwinReadinessEvaluator().evaluate(TwinReadinessRequest(project_id="p", project_path=str(tmp_path), changed_refs=["a.py"], budget=1, metadata={"snapshot_path": str(snapshot), "source_files": ["a.py"], "resolved_refs": ["a.py"], "impacted_refs": ["b.py", "c.py"], "expected_dependent_refs": ["b.py"], "safe_edit_briefing": {"targets": ["a.py"]}, "prompt_delivery": {"instruction_id": "i", "brief_id": "b", "policy_id": "p", "prompt_section_hash": "h"}, "harm_rate": 0.25}))
    by_name = {signal.name: signal for signal in report.signals}
    assert by_name["twin_snapshot_freshness"].status == "warning"
    assert by_name["impact_budget_fit"].status == "warning"
    assert by_name["impact_precision"].score == 0.5
    assert report.readiness_level != "trusted"


def test_complete_fresh_evidence_can_be_trusted(tmp_path):
    source = tmp_path / "a.py"; source.write_text("x=1", encoding="utf-8")
    snapshot = tmp_path / "twin.db"; snapshot.write_text("db", encoding="utf-8")
    os.utime(snapshot, None)
    report = TwinReadinessEvaluator().evaluate(TwinReadinessRequest(project_id="p", project_path=str(tmp_path), changed_refs=["a.py"], metadata={"snapshot_path": str(snapshot), "source_files": ["a.py"], "resolved_refs": ["a.py"], "impacted_refs": ["b.py"], "expected_dependent_refs": ["b.py"], "safe_edit_briefing": {"targets": ["a.py"]}, "prompt_delivery": {"instruction_id": "i", "brief_id": "b", "policy_id": "p", "prompt_section_hash": "h"}, "harm_rate": 0.0}))
    assert report.readiness_level == "trusted"
    assert report.recommended_max_assist_mode == "twin_deterministic_anchor"


def test_readiness_api_persists_truthful_report(tmp_path):
    app = FastAPI(); app.state.atlas_ca_data_root = str(tmp_path / "ca"); app.include_router(router)
    response = TestClient(app).post("/api/forge/twin-assist/readiness", json={"project_id": "p", "project_path": str(tmp_path)})
    assert response.status_code == 200
    assert response.json()["readiness_level"] == "unavailable"
    report_id = response.json()["report_id"]
    assert (tmp_path / "ca" / "model_forge" / "twin_assist_runs" / "readiness" / f"{report_id}.json").is_file()
