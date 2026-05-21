from pathlib import Path
import json
from app.atlas.remote_git_gate import create_remote_git_record, evaluate_remote_git_gate


def _base(tmp_path: Path):
    return dict(project_path=tmp_path, data_root=tmp_path, loop_gate_id="l", stop_gate_id="s", artifact_gate_id="a", risk_id="r", dry_run_gate_id="d", recovery_instructions=["manual review"])


def test_create_record_and_manifest(tmp_path: Path):
    rec = create_remote_git_record(**_base(tmp_path))
    m = rec["manifest"]
    assert rec["manifest_path"].startswith(str(tmp_path))
    assert Path(rec["manifest_path"]).exists()
    for k in ["schema_version", "remote_git_gate_id", "project_path", "data_root", "remote_git_gate_ready", "forbidden_operations", "blocking_reasons", "remote_git_state_summary", "summary"]:
        assert k in m


def test_block_operations_commands_flags_and_missing_refs(tmp_path: Path):
    forbidden_ops = ["git_push","git_pull","git_clone","git_fetch","git_remote","create_branch","create_pr","draft_pr","merge_pr","direct_merge"]
    for op in forbidden_ops:
        r = evaluate_remote_git_gate(**_base(tmp_path), requested_operation=op)
        assert r["remote_git_gate_ready"] is False and r["requested_operation_forbidden"] is True
    for cmd in ["git push", "git pull", "git clone", "git fetch", "git remote", "gh pr create", "gh pr merge", "git merge", "echo a; rm", "a && b", "a || b", "a | b", "a > b", "a >> b", "a < b", "$(x)", "`x`"]:
        r = evaluate_remote_git_gate(**_base(tmp_path), requested_command=cmd)
        assert r["requested_command_blocked"] is True and r["remote_git_gate_ready"] is False
    for flag in ["remote_git_operations_enabled","git_push_enabled","git_pull_enabled","git_clone_enabled","git_fetch_enabled","git_remote_enabled","branch_creation_enabled","automatic_pr_creation_enabled","draft_pr_creation_enabled","direct_merge_enabled","auto_continue_enabled","execute_all_enabled","automatic_execute_enabled","autonomous_execution_enabled"]:
        r = evaluate_remote_git_gate(**_base(tmp_path), **{flag: True})
        assert r["remote_git_gate_ready"] is False
    for miss in ["loop_gate_id","stop_gate_id","artifact_gate_id","risk_id","dry_run_gate_id"]:
        b = _base(tmp_path); b[miss] = ""
        assert evaluate_remote_git_gate(**b)["remote_git_gate_ready"] is False
    assert evaluate_remote_git_gate(project_path=tmp_path, data_root=tmp_path, loop_gate_id="l", stop_gate_id="s", artifact_gate_id="a", risk_id="r", dry_run_gate_id="d")["remote_git_gate_ready"] is False


def test_static_safety_contracts(tmp_path: Path):
    s = Path("app/atlas/remote_git_gate.py").read_text(encoding="utf-8")
    assert 'Path("ca_data")' not in s
    assert "import subprocess" not in s and "subprocess.run" not in s
    assert "safe_apply(" not in s and "restore_workspace_snapshot(" not in s
    r = evaluate_remote_git_gate(**_base(tmp_path))
    assert r["remote_git_operations_enabled"] is False
    assert r["manual_only"] is True


def test_unknown_operation_and_reference_blocking_reasons_force_not_ready(tmp_path: Path):
    outside = tmp_path.parent / "outside.json"
    outside.write_text("{}", encoding="utf-8")

    unknown = evaluate_remote_git_gate(**_base(tmp_path), requested_operation="unknown")
    assert unknown["remote_git_gate_ready"] is False
    assert unknown["requested_operation_forbidden"] is True
    assert "requested_operation_not_allowed" in unknown["blocking_reasons"]

    outside_ref = evaluate_remote_git_gate(
        **_base(tmp_path),
        loop_bound_manifest_path=str(outside),
    )
    assert outside_ref["remote_git_gate_ready"] is False
    assert "reference_path_outside_data_root" in outside_ref["blocking_reasons"]

    unreadable = tmp_path / "unreadable.json"
    unreadable.write_text("{}", encoding="utf-8")
    read_failed = evaluate_remote_git_gate(
        **_base(tmp_path),
        loop_bound_manifest_path=str(unreadable),
    )
    assert read_failed["remote_git_gate_ready"] is False
    assert "reference_read_failed" in read_failed["blocking_reasons"]
