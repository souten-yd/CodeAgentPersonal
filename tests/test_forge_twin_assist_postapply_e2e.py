import json

import pytest

from agent.model_forge.twin_assist_contracts import TwinAssistAttemptResult, TwinAssistCaseComparison, TwinAssistEvaluationReport
from agent.model_forge.twin_assist_postapply import PostApplyE2ERequest, PostApplyE2ERunner
from agent.model_forge.twin_assist_taxonomy import TwinAssistMode


def _source_report(tmp_path, *, contract=True):
    proposal = tmp_path / "proposal.json"
    proposal.write_text(json.dumps({"metadata": {"file_changes": [{"path": "contract.py", "proposed_content": "__all__ = ['parse_token']\n\ndef parse_token(value: str) -> str:\n    return value.strip()\n"}], "change_set": ({"apply_strategy": "preflight_all_then_apply_all", "partial_apply_allowed": False} if contract else {})}}), encoding="utf-8")
    baseline = TwinAssistAttemptResult(case_id="public_contract_preservation", assist_mode=TwinAssistMode.NONE, provider_id="local", model_id="m", status="passed", score=0.8, proposal_ref=str(proposal))
    assisted = baseline.model_copy(update={"assist_mode": TwinAssistMode.STRICT_TWIN_BRIEF})
    report = TwinAssistEvaluationReport(run_id="run", provider_id="local", model_id="m", status="passed", comparisons=[TwinAssistCaseComparison(case_id="public_contract_preservation", baseline=baseline, assisted=[assisted], best_assist_mode=TwinAssistMode.STRICT_TWIN_BRIEF, best_score=0.8, lift=0.0)])
    path = tmp_path / "source.json"; path.write_text(report.model_dump_json(), encoding="utf-8"); return path


def test_isolated_apply_runs_tests_gate_ledger_and_rollback(tmp_path):
    report = PostApplyE2ERunner(tmp_path / "evidence").run(PostApplyE2ERequest(provider_id="local", model_id="m", twin_assist_report_path=str(_source_report(tmp_path)), project_fixture_root="tests/fixtures/twin_assist", case_ids=["public_contract_preservation"]))
    assert len(report.attempts) == 2
    assert all(item.status == "failed" for item in report.attempts)
    assert all(item.apply_status == "isolated_applied" for item in report.attempts)
    assert all(item.test_status == "passed" for item in report.attempts)
    assert all(item.post_apply_twin_status == "needs_repair" for item in report.attempts)
    assert all(item.proof_ledger_ref for item in report.attempts)
    assert all(item.rollback_available for item in report.attempts)
    assert report.aggregate_scores == {"e2e_mean_lift": 0.0, "e2e_harm_rate": 0.0, "attempt_count": 2.0}


def test_direct_apply_and_safe_apply_bypass_are_rejected(tmp_path):
    runner = PostApplyE2ERunner(tmp_path / "evidence")
    with pytest.raises(ValueError, match="direct_workspace_apply_forbidden"):
        runner.run(PostApplyE2ERequest(provider_id="local", model_id="m", twin_assist_report_path=str(_source_report(tmp_path)), apply_mode="direct"))
    report = runner.run(PostApplyE2ERequest(provider_id="local", model_id="m", twin_assist_report_path=str(_source_report(tmp_path, contract=False)), project_fixture_root="tests/fixtures/twin_assist", case_ids=["public_contract_preservation"]))
    assert all(item.status == "blocked" for item in report.attempts)
    assert all("safe_apply_contract_missing" in item.blocked_reasons for item in report.attempts)


def test_unavailable_tests_are_not_passed(tmp_path):
    report = PostApplyE2ERunner(tmp_path / "evidence").run(PostApplyE2ERequest(provider_id="local", model_id="m", twin_assist_report_path=str(_source_report(tmp_path)), project_fixture_root="tests/fixtures/twin_assist", case_ids=["public_contract_preservation"], run_tests=False))
    assert all(item.status == "unavailable" for item in report.attempts)
    assert all(item.test_status == "unavailable" for item in report.attempts)
