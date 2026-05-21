from pathlib import Path
from app.atlas.loop_bound_gate import create_loop_bound_record
from app.atlas.stop_kill_switch_gate import create_stop_kill_switch_record
from app.atlas.artifact_capture_gate import create_artifact_capture_record
from app.atlas.risk_classification import create_risk_classification_record
from app.atlas.dry_run_approval_gate import create_dry_run_approval_record
from app.atlas.remote_git_gate import create_remote_git_record, evaluate_remote_git_gate


def test_reference_integration_and_no_mutation(tmp_path: Path):
    loop = create_loop_bound_record(data_root=tmp_path, project_path=tmp_path, stop_gate_id="s", artifact_gate_id="a", dry_run_gate_id="d", rollback_gate_id="r", risk_id="k", recovery_instructions=["x"], max_actions_per_loop=1, max_retries=0, max_runtime_seconds=1, max_files_changed=1, max_consecutive_failures=0, max_verification_attempts=0, max_patch_transactions=0, max_risk_level="low")
    stop = create_stop_kill_switch_record(data_root=tmp_path, project_path=tmp_path, kill_switch_available=True, stop_state_visible=True, ui_stop_visible=True, cli_stop_available=True, api_stop_available=True, operator_loop_stop_visible=True, artifact_gate_id="a", recovery_instructions=["x"])
    art = create_artifact_capture_record(data_root=tmp_path, project_path=tmp_path, plan_id="p", snapshot_id="s", transaction_id="t", risk_id="r", allowlist_id="a", dry_run_gate_id="d", rollback_readiness_gate_id="b", recovery_instructions=["x"])
    risk = create_risk_classification_record(data_root=tmp_path, project_path=tmp_path, proposed_files=["x.py"])
    dry = create_dry_run_approval_record(data_root=tmp_path, project_path=tmp_path, risk_level="low", transaction_id="t", snapshot_id="s", allowlist_id="a", dry_run_status="passed", confirmation_token_present=True, confirmation_text="EXECUTE ONE ACTION", explicit_decision="approve", approval_status="approved", payload_valid=True, manual_only=True)
    before = Path(loop["manifest_path"]).read_text()
    r = evaluate_remote_git_gate(project_path=tmp_path, data_root=tmp_path, loop_gate_id=loop["loop_gate_id"], loop_bound_manifest_path=loop["manifest_path"], stop_gate_id=stop["stop_gate_id"], stop_gate_manifest_path=stop["manifest_path"], artifact_gate_id=art["artifact_gate_id"], artifact_capture_manifest_path=art["manifest_path"], risk_id=risk["risk_id"], risk_manifest_path=risk["manifest_path"], dry_run_gate_id=dry["gate_id"], dry_run_gate_manifest_path=dry["manifest_path"], recovery_instructions=["x"])
    rec = create_remote_git_record(**r)
    assert rec["manifest"]["loop_gate_id"] == loop["loop_gate_id"]
    assert rec["manifest"]["stop_gate_id"] == stop["stop_gate_id"]
    assert rec["manifest"]["artifact_gate_id"] == art["artifact_gate_id"]
    assert rec["manifest"]["risk_id"] == risk["risk_id"]
    assert rec["manifest"]["dry_run_gate_id"] == dry["gate_id"]
    assert Path(loop["manifest_path"]).read_text() == before
    assert evaluate_remote_git_gate(project_path=tmp_path, data_root=tmp_path, stop_gate_id="s", artifact_gate_id="a", risk_id="r", dry_run_gate_id="d", recovery_instructions=["x"])["remote_git_gate_ready"] is False
    assert evaluate_remote_git_gate(project_path=tmp_path, data_root=tmp_path, loop_gate_id="l", stop_gate_id="s", risk_id="r", dry_run_gate_id="d", recovery_instructions=["x"])["remote_git_gate_ready"] is False
    assert evaluate_remote_git_gate(project_path=tmp_path, data_root=tmp_path, loop_gate_id="l", stop_gate_id="s", artifact_gate_id="a", risk_id="r", dry_run_gate_id="d", recovery_instructions=["x"], requested_operation="git_push")["remote_git_gate_ready"] is False
