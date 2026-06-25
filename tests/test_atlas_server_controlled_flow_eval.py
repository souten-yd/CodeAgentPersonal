from __future__ import annotations

from pathlib import Path


SOURCE = Path("tools/run_atlas_server_controlled_flow_eval.py").read_text(encoding="utf-8")


def test_sc7_runner_targets_local_8080_and_records_blocked_unavailable() -> None:
    assert "http://127.0.0.1:8080" in SOURCE
    assert "blocked_live_llm_unavailable" in SOURCE
    assert "/v1/models" in SOURCE
    assert "main._phase1_llm_json" in SOURCE


def test_sc7_runner_uses_run_api_not_direct_browser_or_patch_authority() -> None:
    assert '"/api/atlas/runs"' in SOURCE
    assert "/api/atlas/runs/{run_id}/status" in SOURCE
    assert "/api/atlas/patch-proposals/generate" not in SOURCE
    assert "/api/atlas/patch-proposals/decide" not in SOURCE
    assert "/api/atlas/automation/safe-apply-one-and-verify" not in SOURCE
    assert "runMultiItemAutopilot" not in SOURCE


def test_sc7_runner_covers_required_acceptance_checks() -> None:
    required = [
        "web_app_greenfield_plan_run_apply_verify",
        "existing_web_app_repair_seeded_defect_run_verify_fix",
        "business_config_bounded_edit_deterministic_check",
        "cli_starts_run_status_api_observes",
        "api_starts_run_cli_watches",
    ]
    for marker in required:
        assert marker in SOURCE


def test_sc7_runner_uses_safe_default_assumptions_for_live_acceptance_plans() -> None:
    assert '"requirement_mode": "auto"' in SOURCE
    assert '"planner_mode": "real_planner"' in SOURCE
    assert 'RUNNABLE_PLAN_STATUSES = {"ready", "approval_required"}' in SOURCE


def test_sc7_runner_has_file_level_deterministic_checks() -> None:
    assert "Atlas SC7 Greenfield Ready" in SOURCE
    assert "Atlas SC7 Repair Ready" in SOURCE
    assert "sc7_live_eval_plan_payload" in SOURCE
    assert "sc7_web_repair_text_contract" in SOURCE
    assert "sc7_config_json_contract" in SOURCE
    assert "checkout_enabled_true" in SOURCE
    assert "owner_preserved" in SOURCE
    assert "deterministic_config_check_authoritative" in SOURCE
    assert "verification_blocked" in SOURCE
