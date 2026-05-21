from pathlib import Path

from app.atlas.artifact_capture_gate import create_artifact_capture_record
from app.atlas.dry_run_approval_gate import create_dry_run_approval_record
from app.atlas.loop_bound_gate import create_loop_bound_record, evaluate_loop_bound_gate
from app.atlas.risk_classification import create_risk_classification_record
from app.atlas.rollback_readiness_gate import create_rollback_readiness_record
from app.atlas.stop_kill_switch_gate import create_stop_kill_switch_record


def test_reference_wiring_and_non_mutation(tmp_path: Path) -> None:
    p = tmp_path / "p"; p.mkdir()
    d = tmp_path / "d"
    risk = create_risk_classification_record(project_path=p, data_root=d, proposed_files=["docs/a.md"])
    dry = create_dry_run_approval_record(project_path=p, data_root=d, dry_run_status="passed", confirmation_token_present=True, confirmation_text="EXECUTE ONE ACTION", payload_valid=True, risk_level="low", transaction_id="tx1", snapshot_id="sn1")
    rb = create_rollback_readiness_record(project_path=p, data_root=d, risk_level="low", restore_plan_status="valid", restore_supported=True, rollback_metadata_present=True, snapshot_manifest_valid=True, snapshot_path_safety_valid=True, transaction_rollback_metadata_valid=True)
    art = create_artifact_capture_record(project_path=p, data_root=d, plan_id="p1", snapshot_id="s1", transaction_id="t1", rollback_metadata_present=True, rollback_readiness_gate_id=rb["rollback_gate_id"], risk_id=risk["risk_id"], allowlist_id="al1", dry_run_gate_id=dry["gate_id"], warnings=[], recovery_instructions=["x"])
    stop = create_stop_kill_switch_record(project_path=p, data_root=d, kill_switch_available=True, stop_state_visible=True, ui_stop_visible=True, cli_stop_available=True, api_stop_available=True, operator_loop_stop_visible=True, artifact_gate_id=art["artifact_gate_id"], recovery_instructions=["x"], warnings=[])
    stop_before = Path(stop["manifest_path"]).read_text(encoding="utf-8")

    gate = evaluate_loop_bound_gate(project_path=p, data_root=d, stop_gate_id=stop["stop_gate_id"], artifact_gate_id=art["artifact_gate_id"], dry_run_gate_id=dry["gate_id"], rollback_gate_id=rb["rollback_gate_id"], risk_id=risk["risk_id"], warnings=[], recovery_instructions=["x"], max_actions_per_loop=2, max_retries=1, max_runtime_seconds=20, max_files_changed=2, max_consecutive_failures=1, max_verification_attempts=1, max_patch_transactions=1, max_risk_level="high", current_risk_level="low")
    gate.pop("data_root", None)
    rec = create_loop_bound_record(data_root=d, **gate)
    assert rec["manifest"]["stop_gate_id"] == stop["stop_gate_id"]
    assert rec["manifest"]["artifact_gate_id"] == art["artifact_gate_id"]
    assert rec["manifest"]["dry_run_gate_id"] == dry["gate_id"]
    assert rec["manifest"]["rollback_gate_id"] == rb["rollback_gate_id"]
    assert rec["manifest"]["risk_id"] == risk["risk_id"]
    assert Path(stop["manifest_path"]).read_text(encoding="utf-8") == stop_before


def test_missing_refs_and_stop_requested_block(tmp_path: Path) -> None:
    p = tmp_path / "p"; p.mkdir()
    b = dict(project_path=p, warnings=[], recovery_instructions=["x"], max_actions_per_loop=2, max_retries=1, max_runtime_seconds=20, max_files_changed=2, max_consecutive_failures=1, max_verification_attempts=1, max_patch_transactions=1, max_risk_level="high", current_risk_level="low")
    assert evaluate_loop_bound_gate(**{**b, "stop_gate_id": "", "artifact_gate_id": "a", "dry_run_gate_id": "d", "rollback_gate_id": "r", "risk_id": "rk"})["loop_bound_ready"] is False
    assert evaluate_loop_bound_gate(**{**b, "stop_gate_id": "s", "artifact_gate_id": "", "dry_run_gate_id": "d", "rollback_gate_id": "r", "risk_id": "rk"})["loop_bound_ready"] is False
    assert evaluate_loop_bound_gate(**{**b, "stop_gate_id": "s", "artifact_gate_id": "a", "dry_run_gate_id": "d", "rollback_gate_id": "r", "risk_id": ""})["loop_bound_ready"] is False
    stop = evaluate_loop_bound_gate(**{**b, "stop_gate_id": "s", "artifact_gate_id": "a", "dry_run_gate_id": "d", "rollback_gate_id": "r", "risk_id": "rk", "stop_requested": True})
    assert stop["status"] == "stop_requested_manual_halt"
    text = Path("app/atlas/loop_bound_gate.py").read_text(encoding="utf-8")
    for s in ["restore_workspace_snapshot", "safe_apply(", "pytest", "subprocess", "while True"]:
        assert s not in text
