from __future__ import annotations

from pathlib import Path


SOURCE = Path("tools/run_atlas_restore_visual_recovery_eval.py").read_text(encoding="utf-8")


def test_rv7_runner_targets_local_8080_and_records_blocked_unavailable() -> None:
    assert "http://127.0.0.1:8080" in SOURCE
    assert "/v1/models" in SOURCE
    assert "/v1/chat/completions" in SOURCE
    assert "blocked_live_llm_unavailable" in SOURCE


def test_rv7_runner_uses_project_planpool_and_run_api_authority() -> None:
    assert '"/api/atlas/projects"' in SOURCE
    assert '"/api/atlas/plan-pools?sync=1"' in SOURCE
    assert '"/api/atlas/runs"' in SOURCE
    assert "/api/atlas/continuation/latest" in SOURCE
    assert "/api/atlas/recovery/latest" in SOURCE
    assert "/api/atlas/patch-proposals/generate" not in SOURCE
    assert "/api/atlas/automation/safe-apply-one-and-verify" not in SOURCE
    assert "runMultiItemAutopilot" not in SOURCE


def test_rv7_runner_records_required_live_result_fields() -> None:
    for marker in [
        "project_name",
        "workspace_id",
        "pool_id",
        "run_id",
        "visual_contract_id",
        "artifact_type",
        "status",
        "warnings",
        "missing_signals",
        "canvas_exists_absent_from_hard_missing",
    ]:
        assert marker in SOURCE


def test_rv7_runner_keeps_browser_smoke_unavailable_truthful() -> None:
    assert "browser_smoke_status" in SOURCE
    assert "skipped_static_only" in SOURCE
    assert '"browser_smoke_truthful"' in SOURCE


def test_rv7_runner_does_not_treat_live_unavailable_as_passed() -> None:
    assert 'report.update({"status": "blocked", "blocked_reason": "blocked_live_llm_unavailable"' in SOURCE
    assert "blocked_live_llm_patch_generation_failed" in SOURCE
    assert 'if not failed:' in SOURCE
    assert 'elif failed == ["run_completed"] and final_status.get("error") == "patch_proposal_failed":' in SOURCE
    assert 'report["status"] = "failed"' in SOURCE


def test_rv8_final_review_mode_builds_required_evidence_bundle() -> None:
    assert "--final-review" in SOURCE
    assert "build_final_review_bundle" in SOURCE
    for marker in [
        "focused_test_outputs",
        "project_isolation_fixture_result",
        "local_storage_scoped_key_assertion",
        "backend_workspace_isolation_result",
        "rubik_classification_result",
        "visual_contract_result",
        "live_8080_result",
        "unavailable_checks",
    ]:
        assert marker in SOURCE


def test_rv8_final_review_does_not_convert_blocked_evidence_to_passed() -> None:
    assert "convert blocked or unavailable evidence into passed evidence" in SOURCE
    assert "blocked_live_llm_patch_generation_failed is acceptable closeout" in SOURCE
    assert "raw_status" in SOURCE
    assert "blocking_issues" in SOURCE
    assert "missing_deterministic_checks" in SOURCE
    assert "contradictory_evidence" in SOURCE
