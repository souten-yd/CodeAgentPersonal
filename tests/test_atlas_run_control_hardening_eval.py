from __future__ import annotations

from pathlib import Path


SOURCE = Path("tools/run_atlas_run_control_hardening_eval.py").read_text(encoding="utf-8")


def test_cs15_runner_targets_local_8080_and_records_blocked_unavailable() -> None:
    assert "http://127.0.0.1:8080" in SOURCE
    assert "/v1/models" in SOURCE
    assert "/v1/chat/completions" in SOURCE
    assert "blocked_live_llm_unavailable" in SOURCE


def test_cs15_runner_uses_run_api_and_kasane_cli_paths() -> None:
    assert '"/api/atlas/runs"' in SOURCE
    assert "/api/atlas/runs/recover-stale" in SOURCE
    assert 'kasane_commands.run_cli(["watch"' in SOURCE
    assert '"/run pool_cli"' in SOURCE
    assert "run_repl(" in SOURCE
    assert "/api/atlas/patch-proposals/generate" not in SOURCE
    assert "/api/atlas/automation/safe-apply-one-and-verify" not in SOURCE
    assert "runMultiItemAutopilot" not in SOURCE


def test_cs15_runner_covers_required_scenarios() -> None:
    for marker in [
        "api_starts_run_cli_watches_browser_status_observes",
        "cli_interactive_style_starts_run_api_watches",
        "failed_item_retry_uses_run_retry_endpoint",
        "resume_without_client_item_ids_skips_completed",
        "duplicate_start_rejected_or_idempotent",
        "stale_running_recovery_marks_blocked_retryable_not_success",
        "banner_interactive_present_json_absent",
    ]:
        assert marker in SOURCE


def test_cs15_runner_preserves_truthful_evidence_contract() -> None:
    assert 'report["status"] = "passed" if not failed else "failed"' in SOURCE
    assert '"blocked_reason"] = "blocked_live_llm_unavailable"' in SOURCE
    assert '"unavailable_checks"' in SOURCE
    assert "RUNNABLE_PLAN_STATUSES = {\"ready\", \"approval_required\"}" in SOURCE
