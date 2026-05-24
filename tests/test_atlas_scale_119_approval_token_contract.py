from pathlib import Path

from app.atlas.level1_approval_token_contract import (
    REQUIRED_CONFIRMATION_TEXT,
    SCHEMA_VERSION,
    create_level1_approval_token_contract,
    read_level1_approval_token_contract,
    validate_level1_approval_token_contract,
    write_level1_approval_token_contract,
)


def test_scale_119_creates_digest_only_approval_token_contract_without_execution() -> None:
    created = create_level1_approval_token_contract(
        workspace_id="ws_1",
        pool_id="pool_1",
        item_id="item_1",
        run_id="run_1",
        action_id="action_1",
        dry_run_artifact_id="dry_run_artifact_1",
        dry_run_manifest_path="atlas/dry_run_artifacts/dry_run_artifact_1/manifest.json",
        risk_level="low",
        token="scale119-test-token",
    )

    assert created["schema_version"] == SCHEMA_VERSION
    assert created["approval_token"] == "scale119-test-token"
    assert created["runtime_level"] == "level_0_manual_only"
    assert created["manual_only"] is True
    assert created["execution_authorized"] is False
    assert created["autonomous_loop_authorized"] is False

    contract = created["contract"]
    assert "approval_token" not in contract
    assert contract["token_digest"] != "scale119-test-token"
    assert "token_preview" not in contract
    assert contract["token_digest_preview"] == f"{contract['token_digest'][:12]}..."
    assert contract["runtime_level"] == "level_0_manual_only"
    assert contract["requires_confirmation_text"] == REQUIRED_CONFIRMATION_TEXT
    assert contract["token_authorizes_execution"] is False
    assert contract["token_authorizes_autonomous_loop"] is False
    assert contract["token_authorizes_mutation"] is False
    assert contract["execution_performed"] is False
    assert contract["mutation_performed"] is False
    assert contract["level1_execution_enabled"] is False
    assert contract["autonomous_execution_enabled"] is False
    assert contract["next_required_pr"] == "PR-ATLAS-SCALE-120"


def test_scale_119_validation_never_authorizes_execution_or_autonomous_loop() -> None:
    created = create_level1_approval_token_contract(
        dry_run_artifact_id="dry_run_artifact_1",
        token="scale119-test-token",
    )

    valid = validate_level1_approval_token_contract(
        contract=created["contract"],
        provided_token="scale119-test-token",
        confirmation_text=REQUIRED_CONFIRMATION_TEXT,
    )
    assert valid["approval_token_valid"] is True
    assert valid["status"] == "valid_for_manual_gate_review"
    assert valid["execution_authorized"] is False
    assert valid["autonomous_loop_authorized"] is False
    assert valid["mutation_authorized"] is False
    assert valid["level1_execution_enabled"] is False
    assert valid["autonomous_execution_enabled"] is False

    blocked = validate_level1_approval_token_contract(
        contract=created["contract"],
        provided_token="wrong-token",
        confirmation_text="EXECUTE ALL",
    )
    assert blocked["approval_token_valid"] is False
    assert blocked["status"] == "blocked"
    assert "matching_approval_token" in blocked["missing_requirements"]
    assert "confirmation_text" in blocked["missing_requirements"]


def test_scale_119_persists_contract_digest_only_under_data_root(tmp_path: Path) -> None:
    created = create_level1_approval_token_contract(
        dry_run_artifact_id="dry_run_artifact_1",
        token="scale119-test-token",
    )

    written = write_level1_approval_token_contract(data_root=tmp_path, contract=created["contract"])
    manifest_path = Path(str(written["manifest_path"]))
    assert manifest_path.exists()
    assert manifest_path.is_relative_to(tmp_path)
    assert "approval_token" not in written["manifest"]
    assert written["manifest"]["token_digest"] != "scale119-test-token"
    assert written["execution_authorized"] is False
    assert written["autonomous_loop_authorized"] is False

    loaded = read_level1_approval_token_contract(manifest_path=manifest_path, data_root=tmp_path)
    assert loaded["manifest"]["schema_version"] == SCHEMA_VERSION
    assert "approval_token" not in loaded["manifest"]


def test_scale_119_contract_forbids_execution_mutation_remote_git_tokens() -> None:
    source = Path("app/atlas/level1_approval_token_contract.py").read_text(encoding="utf-8").lower()
    for token in [
        "subprocess",
        "shell=true",
        "safe_apply",
        "git push",
        "git pull",
        "git clone",
        "apply_patch",
        "rollback(",
        "retry(",
    ]:
        assert token not in source
