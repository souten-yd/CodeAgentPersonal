from __future__ import annotations

from agent.atlas_ci_failure_repair_schema import AtlasCIFailureRepairRequest
from agent.atlas_ci_failure_repair_service import AtlasCIFailureRepairService


def test_pytest_failure_log_maps_to_bounded_ci_repair_plan() -> None:
    result = AtlasCIFailureRepairService().build(
        AtlasCIFailureRepairRequest(
            source="github_actions",
            run_id="run-1",
            job_id="job-1",
            failing_command="python -m pytest -q tests/test_app.py",
            log_text="FAILED tests/test_app.py::test_feature - AssertionError: expected true",
            allowed_paths=["tests/"],
            plan_items=[{"item_id": "test-fix", "target_files": ["tests/test_app.py"]}],
        )
    )

    evidence = result["ci_failure_evidence"]
    plan = result["ci_repair_plan"]
    assert evidence["failing_test_names"] == ["tests/test_app.py::test_feature"]
    assert evidence["affected_files"] == ["tests/test_app.py"]
    assert evidence["confidence"] == "high"
    assert plan["status"] == "planned"
    assert plan["failure_class"] == "pytest_failure"
    assert plan["mapped_plan_item_ids"] == ["test-fix"]
    assert plan["allowed_repair_files"] == ["tests/test_app.py"]
    assert plan["post_repair_verification_required"] is True
    assert result["post_ci_repair_verification_required"] is True


def test_unrelated_ci_log_does_not_fabricate_confidence_or_repair_scope() -> None:
    result = AtlasCIFailureRepairService().build(
        AtlasCIFailureRepairRequest(
            source="manual",
            log_text="runner unavailable before tests started",
            allowed_paths=["src/"],
        )
    )

    evidence = result["ci_failure_evidence"]
    plan = result["ci_repair_plan"]
    assert evidence["failing_test_names"] == []
    assert evidence["affected_files"] == []
    assert evidence["confidence"] == "unknown"
    assert plan["status"] == "blocked"
    assert plan["allowed_repair_files"] == []
    assert "no_failing_tests_detected" in plan["warnings"]
    assert result["post_ci_repair_verification_required"] is False


def test_ci_repair_plan_respects_allowed_paths_and_never_executes() -> None:
    result = AtlasCIFailureRepairService().build(
        AtlasCIFailureRepairRequest(
            failing_command="python -m pytest -q tests/test_app.py",
            log_text="FAILED tests/test_app.py::test_feature - AssertionError",
            affected_files=["src/app.py"],
            allowed_paths=["tests/"],
        )
    )

    plan = result["ci_repair_plan"]
    assert plan["allowed_repair_files"] == ["tests/test_app.py"]
    assert plan["blocked_files"] == ["src/app.py"]
    assert "affected_files_outside_allowed_paths" in plan["warnings"]
    for block in (result["ci_failure_evidence"], plan):
        assert block["metadata"]["advisory_only"] is True
        assert block["metadata"]["executed"] is False
        assert block["metadata"]["remote_ci_fetched"] is False
        assert block["metadata"]["shell_executed"] is False
        assert block["metadata"]["remote_git_push_executed"] is False
        assert block["metadata"]["auto_repair_executed"] is False
    ingestion = result["ci_failure_ingestion"]
    assert ingestion["advisory_only"] is True
    assert ingestion["executed"] is False
    assert ingestion["remote_ci_fetched"] is False
    assert ingestion["shell_executed"] is False
    assert ingestion["remote_git_push_executed"] is False
    assert ingestion["auto_repair_executed"] is False
