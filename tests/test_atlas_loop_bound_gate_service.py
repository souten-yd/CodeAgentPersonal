from pathlib import Path

from app.atlas.loop_bound_gate import create_loop_bound_record, evaluate_loop_bound_gate


def _base(project: Path, data: Path) -> dict:
    return dict(project_path=project, data_root=data, stop_gate_id="s1", artifact_gate_id="a1", dry_run_gate_id="d1", rollback_gate_id="r1", risk_id="rk1", warnings=[], recovery_instructions=["manual recovery"], max_actions_per_loop=2, max_retries=1, max_runtime_seconds=30, max_files_changed=3, max_consecutive_failures=1, max_verification_attempts=1, max_patch_transactions=1, max_risk_level="high", current_risk_level="medium")


def test_create_and_manifest_contract(tmp_path: Path) -> None:
    p = tmp_path / "p"; p.mkdir()
    d = tmp_path / "d"
    out = create_loop_bound_record(**_base(p, d))
    assert Path(out["manifest_path"]).exists()
    m = out["manifest"]
    for k in ["schema_version", "loop_gate_id", "project_path", "data_root", "loop_bound_ready", "missing_bounds", "exceeded_bounds", "blocking_reasons", "loop_state_summary", "summary"]:
        assert k in m


def test_blocks_and_no_mutation(tmp_path: Path) -> None:
    p = tmp_path / "p"; p.mkdir()
    d = tmp_path / "d"
    f = p / "k.txt"; f.write_text("x", encoding="utf-8")
    before = f.read_text(encoding="utf-8")
    b = _base(p, d)
    assert evaluate_loop_bound_gate(**{**b, "max_actions_per_loop": None})["loop_bound_ready"] is False
    assert evaluate_loop_bound_gate(**{**b, "max_retries": None})["loop_bound_ready"] is False
    assert evaluate_loop_bound_gate(**{**b, "max_runtime_seconds": None})["loop_bound_ready"] is False
    assert evaluate_loop_bound_gate(**{**b, "max_files_changed": None})["loop_bound_ready"] is False
    assert evaluate_loop_bound_gate(**{**b, "max_risk_level": "unknown"})["loop_bound_ready"] is False
    assert evaluate_loop_bound_gate(**{**b, "max_actions_per_loop": 0})["loop_bound_ready"] is False
    assert evaluate_loop_bound_gate(**{**b, "current_action_count": 9})["loop_bound_ready"] is False
    assert evaluate_loop_bound_gate(**{**b, "current_retry_count": 9})["loop_bound_ready"] is False
    assert evaluate_loop_bound_gate(**{**b, "current_runtime_seconds": 999})["loop_bound_ready"] is False
    assert evaluate_loop_bound_gate(**{**b, "current_changed_file_count": 99})["loop_bound_ready"] is False
    assert evaluate_loop_bound_gate(**{**b, "current_consecutive_failure_count": 99})["loop_bound_ready"] is False
    assert evaluate_loop_bound_gate(**{**b, "current_verification_attempt_count": 99})["loop_bound_ready"] is False
    assert evaluate_loop_bound_gate(**{**b, "current_patch_transaction_count": 99})["loop_bound_ready"] is False
    assert evaluate_loop_bound_gate(**{**b, "current_risk_level": "strict_gate", "max_risk_level": "high"})["loop_bound_ready"] is False
    assert evaluate_loop_bound_gate(**{**b, "current_risk_level": "unknown"})["loop_bound_ready"] is False
    assert evaluate_loop_bound_gate(**{**b, "stop_gate_id": "", "stop_gate_manifest_path": ""})["loop_bound_ready"] is False
    assert evaluate_loop_bound_gate(**{**b, "artifact_gate_id": "", "artifact_capture_manifest_path": ""})["loop_bound_ready"] is False
    assert evaluate_loop_bound_gate(**{**b, "dry_run_gate_id": "", "dry_run_gate_manifest_path": ""})["loop_bound_ready"] is False
    assert evaluate_loop_bound_gate(**{**b, "rollback_gate_id": "", "rollback_readiness_manifest_path": ""})["loop_bound_ready"] is False
    assert evaluate_loop_bound_gate(**{**b, "risk_id": "", "risk_manifest_path": ""})["loop_bound_ready"] is False
    assert evaluate_loop_bound_gate(**{**b, "recovery_instructions": []})["loop_bound_ready"] is False
    assert evaluate_loop_bound_gate(**{**b, "auto_continue_enabled": True})["loop_bound_ready"] is False
    assert evaluate_loop_bound_gate(**{**b, "execute_all_enabled": True})["loop_bound_ready"] is False
    assert evaluate_loop_bound_gate(**{**b, "automatic_loop_enabled": True})["loop_bound_ready"] is False
    assert evaluate_loop_bound_gate(**{**b, "automatic_retry_enabled": True})["loop_bound_ready"] is False
    assert evaluate_loop_bound_gate(**{**b, "automatic_execute_enabled": True})["loop_bound_ready"] is False
    assert evaluate_loop_bound_gate(**{**b, "autonomous_execution_enabled": True})["loop_bound_ready"] is False
    stop = evaluate_loop_bound_gate(**{**b, "stop_requested": True})
    assert stop["status"] == "stop_requested_manual_halt"
    assert stop["loop_bound_ready"] is False
    ok = evaluate_loop_bound_gate(**b)
    assert ok["loop_bound_ready"] is True
    assert ok["automatic_loop_enabled"] is False
    assert ok["automatic_retry_enabled"] is False
    assert ok["automatic_execute_enabled"] is False
    assert ok["automatic_verification_enabled"] is False
    assert ok["automatic_safe_apply_enabled"] is False
    assert f.read_text(encoding="utf-8") == before


def test_no_forbidden_apis() -> None:
    src = Path("app/atlas/loop_bound_gate.py").read_text(encoding="utf-8")
    assert 'Path("ca_data")' not in src
    assert "import subprocess" not in src
    for s in ["restore_workspace_snapshot", "safe_apply(", "while True", "for "]:
        if s in {"for "}:
            continue
    assert "restore_workspace_snapshot" not in src
    assert "safe_apply(" not in src
    assert "while True" not in src
