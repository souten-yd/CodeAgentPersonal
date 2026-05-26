import json
from pathlib import Path

from app.atlas.bounded_loop_policy import create_bounded_loop_policy_v1, read_bounded_loop_policy_v1


def _write_pr_update_result(tmp_path: Path, overrides: dict[str, object] | None = None) -> tuple[Path, Path]:
    data_root = tmp_path / "data"
    update_dir = data_root / "atlas" / "branch_proposals" / "proposal_1"
    update_dir.mkdir(parents=True)
    payload: dict[str, object] = {
        "schema_version": "atlas.draft_pr_update_result.v1",
        "status": "updated",
        "update_id": "update_1",
        "transaction_id": "txn_1",
        "draft_pr_number": 136,
        "draft_pr_url": "https://example.test/pr/136",
        "changed_files": ["a.txt"],
        "pr_updated": True,
        "push_performed": False,
        "autonomous_execution_enabled": False,
        "draft": True,
    }
    if overrides:
        payload.update(overrides)
    path = update_dir / "draft_pr_update_result.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return data_root, path


def test_create_bounded_loop_policy_v1_writes_policy_only_manifest(tmp_path: Path) -> None:
    data_root, update_path = _write_pr_update_result(tmp_path)

    result = create_bounded_loop_policy_v1(
        pr_update_result_path=update_path,
        data_root=data_root,
        approval_status="approved",
        explicit_decision="approve",
        max_iterations=2,
    )

    assert result["status"] == "created"
    assert result["policy_only"] is True
    assert result["max_iterations"] == 2
    assert result["loop_execution_enabled"] is False
    assert result["bounded_retry_enabled"] is False
    assert result["autonomous_execution_enabled"] is False
    assert result["self_modification_enabled"] is False
    policy = read_bounded_loop_policy_v1(policy_path=result["policy_path"], data_root=data_root)["policy"]
    assert policy["schema_version"] == "atlas.bounded_loop_policy.v1"
    assert "execute_without_human_approval" in policy["forbidden_iteration_actions"]
    updated = json.loads(update_path.read_text(encoding="utf-8"))
    assert updated["bounded_loop_policy_status"] == "created"
    assert updated["loop_execution_enabled"] is False


def test_create_bounded_loop_policy_v1_blocks_without_approval(tmp_path: Path) -> None:
    data_root, update_path = _write_pr_update_result(tmp_path)

    result = create_bounded_loop_policy_v1(pr_update_result_path=update_path, data_root=data_root)

    assert result["status"] == "blocked"
    assert "explicit_human_approval_required" in result["blocked_reasons"]
    assert result["loop_execution_enabled"] is False
    assert not Path(result["policy_path"]).exists()


def test_create_bounded_loop_policy_v1_blocks_out_of_bounds_iterations(tmp_path: Path) -> None:
    data_root, update_path = _write_pr_update_result(tmp_path)

    result = create_bounded_loop_policy_v1(
        pr_update_result_path=update_path,
        data_root=data_root,
        approval_status="approved",
        explicit_decision="approve",
        max_iterations=4,
    )

    assert result["status"] == "blocked"
    assert "max_iterations_out_of_bounds" in result["blocked_reasons"]
    assert not Path(result["policy_path"]).exists()


def test_create_bounded_loop_policy_v1_blocks_untrusted_update_result(tmp_path: Path) -> None:
    data_root, update_path = _write_pr_update_result(
        tmp_path,
        {"status": "blocked", "pr_updated": False, "autonomous_execution_enabled": True},
    )

    result = create_bounded_loop_policy_v1(
        pr_update_result_path=update_path,
        data_root=data_root,
        approval_status="approved",
        explicit_decision="approve",
    )

    assert result["status"] == "blocked"
    assert "pr_update_result_required" in result["blocked_reasons"]
    assert "autonomous_execution_enabled_must_be_false" in result["blocked_reasons"]


def test_create_bounded_loop_policy_v1_dry_run_does_not_write_policy(tmp_path: Path) -> None:
    data_root, update_path = _write_pr_update_result(tmp_path)

    result = create_bounded_loop_policy_v1(
        pr_update_result_path=update_path,
        data_root=data_root,
        approval_status="approved",
        explicit_decision="approve",
        dry_run=True,
    )

    assert result["status"] == "planned"
    assert result["loop_execution_enabled"] is False
    assert not Path(result["policy_path"]).exists()


def test_no_network_or_process_execution_in_bounded_loop_policy_source() -> None:
    text = Path("app/atlas/bounded_loop_policy.py").read_text(encoding="utf-8")
    assert "subprocess" not in text
    assert "os.system" not in text
    assert "requests" not in text
    assert "Github" not in text
