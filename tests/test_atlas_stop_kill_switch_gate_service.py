from pathlib import Path

from app.atlas.stop_kill_switch_gate import create_stop_kill_switch_record, evaluate_stop_kill_switch_gate


def _base(project: Path, data: Path) -> dict:
    return dict(project_path=project, data_root=data, kill_switch_available=True, stop_state_visible=True, ui_stop_visible=True, cli_stop_available=True, api_stop_available=True, operator_loop_stop_visible=True, artifact_gate_id="ag1", recovery_instructions=["manual recovery"], warnings=[])


def test_create_manifest_and_rules(tmp_path: Path) -> None:
    p = tmp_path / "p"; p.mkdir()
    d = tmp_path / "d"
    out = create_stop_kill_switch_record(**_base(p, d))
    assert Path(out["manifest_path"]).exists()
    m = out["manifest"]
    for k in ["schema_version", "stop_gate_id", "project_path", "data_root", "stop_gate_ready", "missing_stop_controls", "blocking_reasons", "stop_state_summary", "summary"]:
        assert k in m


def test_blocks_and_statuses(tmp_path: Path) -> None:
    p = tmp_path / "p"; p.mkdir()
    d = tmp_path / "d"
    b = _base(p, d)
    assert evaluate_stop_kill_switch_gate(**{**b, "kill_switch_available": False})["stop_gate_ready"] is False
    assert evaluate_stop_kill_switch_gate(**{**b, "stop_state_visible": False})["stop_gate_ready"] is False
    assert evaluate_stop_kill_switch_gate(**{**b, "ui_stop_visible": False})["stop_gate_ready"] is False
    assert evaluate_stop_kill_switch_gate(**{**b, "artifact_gate_id": "", "artifact_capture_manifest_path": ""})["stop_gate_ready"] is False
    assert evaluate_stop_kill_switch_gate(**{**b, "recovery_instructions": []})["stop_gate_ready"] is False
    assert evaluate_stop_kill_switch_gate(**{**b, "auto_continue_enabled": True})["stop_gate_ready"] is False
    assert evaluate_stop_kill_switch_gate(**{**b, "execute_all_enabled": True})["stop_gate_ready"] is False
    assert evaluate_stop_kill_switch_gate(**{**b, "automatic_execute_enabled": True})["stop_gate_ready"] is False
    assert evaluate_stop_kill_switch_gate(**{**b, "autonomous_execution_enabled": True})["stop_gate_ready"] is False

    req = evaluate_stop_kill_switch_gate(**{**b, "stop_requested": True, "running_action_count": 2})
    assert req["status"] == "stop_requested_manual_halt"
    ack = evaluate_stop_kill_switch_gate(**{**b, "stop_requested": True, "stop_acknowledged": True, "stop_request_id": "r1"})
    assert ack["status"] == "stop_acknowledged_manual_halt"
    inc = evaluate_stop_kill_switch_gate(**{**b, "stop_acknowledged": True})
    assert inc["stop_gate_ready"] is False


def test_no_mutation_and_safety_flags(tmp_path: Path) -> None:
    p = tmp_path / "p"; p.mkdir()
    f = p / "k.txt"; f.write_text("x", encoding="utf-8")
    before = f.read_text(encoding="utf-8")
    g = evaluate_stop_kill_switch_gate(**_base(p, tmp_path / "d"))
    assert f.read_text(encoding="utf-8") == before
    assert g["automatic_stop_execution_enabled"] is False
    assert g["automatic_execute_enabled"] is False
    assert g["automatic_retry_enabled"] is False
    assert g["automatic_rollback_enabled"] is False
    assert g["automatic_verification_enabled"] is False
    assert g["automatic_safe_apply_enabled"] is False


def test_no_forbidden_calls() -> None:
    src = Path("app/atlas/stop_kill_switch_gate.py").read_text(encoding="utf-8")
    assert 'Path("ca_data")' not in src
    assert "import subprocess" not in src
    for s in ["os.kill", "terminate(", "kill(", "restore_workspace_snapshot", "safe_apply("]:
        assert s not in src
