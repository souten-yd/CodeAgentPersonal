from pathlib import Path

from app.atlas.artifact_capture_gate import create_artifact_capture_record
from app.atlas.stop_kill_switch_gate import create_stop_kill_switch_record, evaluate_stop_kill_switch_gate


def test_reference_and_non_mutation(tmp_path: Path) -> None:
    p = tmp_path / "p"; p.mkdir()
    data = tmp_path / "d"
    a = create_artifact_capture_record(project_path=p, data_root=data, plan_id="p1", snapshot_id="s1", transaction_id="t1", rollback_metadata_present=True, rollback_readiness_gate_id="rb1", risk_id="r1", allowlist_id="al1", dry_run_gate_id="dr1", warnings=[], recovery_instructions=["x"])
    before = Path(a["manifest_path"]).read_text(encoding="utf-8")
    gate = evaluate_stop_kill_switch_gate(project_path=p, data_root=data, kill_switch_available=True, stop_state_visible=True, ui_stop_visible=True, cli_stop_available=True, api_stop_available=True, operator_loop_stop_visible=True, artifact_gate_id=a["artifact_gate_id"], artifact_capture_manifest_path=a["manifest_path"], recovery_instructions=["manual"], warnings=[], stop_requested=True)
    gate.pop("data_root", None)
    rec = create_stop_kill_switch_record(data_root=data, **gate)
    assert rec["manifest"]["artifact_gate_id"] == a["artifact_gate_id"]
    assert Path(a["manifest_path"]).read_text(encoding="utf-8") == before
    assert rec["manifest"]["stop_requested"] is True


def test_missing_artifact_blocks_and_no_execution_signals(tmp_path: Path) -> None:
    p = tmp_path / "p"; p.mkdir()
    g = evaluate_stop_kill_switch_gate(project_path=p, kill_switch_available=True, stop_state_visible=True, ui_stop_visible=True, cli_stop_available=True, api_stop_available=True, operator_loop_stop_visible=True, recovery_instructions=["manual"], warnings=[], stop_acknowledged=True)
    assert g["stop_gate_ready"] is False
    assert g["status"] == "stop_acknowledged_manual_halt"
    text = Path("app/atlas/stop_kill_switch_gate.py").read_text(encoding="utf-8")
    for s in ["restore_workspace_snapshot", "safe_apply(", "pytest", "os.kill", "terminate("]:
        assert s not in text
