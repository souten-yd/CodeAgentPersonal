from pathlib import Path

from app.atlas.level1_disabled_command_runner import (
    SCHEMA_VERSION,
    build_disabled_single_allowlisted_command_runner_contract,
    write_disabled_single_allowlisted_command_runner_contract,
)


def test_scale_121_allows_only_allowlisted_candidate_but_runner_stays_disabled(tmp_path: Path) -> None:
    result = build_disabled_single_allowlisted_command_runner_contract(
        command="pytest -q tests/test_atlas_scale_120_dry_run_result_viewer_contract.py",
        project_path=Path.cwd(),
        risk_level="low",
        workspace_id="ws_1",
        run_id="run_1",
        action_id="action_1",
    )

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["status"] == "disabled_allowlisted_candidate"
    assert result["runtime_level"] == "level_0_manual_only"
    assert result["manual_only"] is True
    assert result["runner_enabled"] is False
    assert result["execution_supported"] is False
    assert result["execution_performed"] is False
    assert result["mutation_performed"] is False
    assert result["level1_execution_enabled"] is False
    assert result["autonomous_execution_enabled"] is False

    contract = result["contract"]
    assert contract["allowlisted"] is True
    assert contract["default_disabled"] is True
    assert contract["single_action_only"] is True
    assert contract["dry_run_required"] is True
    assert contract["explicit_approval_required"] is True
    assert contract["runner_enabled"] is False
    assert contract["execution_supported"] is False
    assert contract["execution_performed"] is False
    assert contract["verification_performed"] is False
    assert contract["next_required_pr"] == "PR-ATLAS-SCALE-122"

    written = write_disabled_single_allowlisted_command_runner_contract(data_root=tmp_path, contract=contract)
    manifest_path = Path(str(written["manifest_path"]))
    assert manifest_path.exists()
    assert manifest_path.is_relative_to(tmp_path)
    assert written["manifest"]["runner_enabled"] is False
    assert written["execution_performed"] is False


def test_scale_121_blocks_unknown_or_forbidden_commands_without_execution(tmp_path: Path) -> None:
    for command in [
        "pytest",
        "git push origin main",
        "pytest -q tests/test_atlas_scale_120_dry_run_result_viewer_contract.py && echo bad",
    ]:
        result = build_disabled_single_allowlisted_command_runner_contract(
            command=command,
            project_path=tmp_path,
            risk_level="low",
        )
        contract = result["contract"]
        assert result["status"] == "blocked"
        assert contract["allowlisted"] is False
        assert "allowlisted_command" in contract["missing_requirements"]
        assert contract["runner_enabled"] is False
        assert contract["execution_performed"] is False
        assert contract["mutation_performed"] is False
        assert contract["level1_execution_enabled"] is False
        assert contract["autonomous_execution_enabled"] is False


def test_scale_121_contract_has_no_command_execution_implementation_tokens() -> None:
    source = Path("app/atlas/level1_disabled_command_runner.py").read_text(encoding="utf-8")
    for token in [
        "subprocess",
        "os.system",
        "shell=True",
        "Popen",
        "check_output",
        "safe_apply",
        "git push",
        "git pull",
        "git clone",
        "@router.post",
        "/api/atlas/level1/execute",
    ]:
        assert token not in source
