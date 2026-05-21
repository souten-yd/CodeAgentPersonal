from pathlib import Path

from app.atlas.artifact_capture_gate import create_artifact_capture_record, evaluate_artifact_capture_gate


def _ready(project: Path, data_root: Path) -> dict:
    (data_root / "atlas" / "x").mkdir(parents=True, exist_ok=True)
    files = {}
    for name in ["plan.json", "snap.json", "txn.json", "risk.json", "allow.json", "dry.json", "rollback.json"]:
        p = data_root / "atlas" / "x" / name
        p.write_text("{}", encoding="utf-8")
        files[name] = p
    return dict(project_path=project, data_root=data_root, plan_id="plan1", plan_manifest_path=str(files["plan.json"]), snapshot_id="snap1", snapshot_manifest_path=str(files["snap.json"]), transaction_id="txn1", transaction_manifest_path=str(files["txn.json"]), rollback_metadata_present=True, rollback_readiness_gate_id="rb1", rollback_readiness_manifest_path=str(files["rollback.json"]), risk_id="r1", risk_manifest_path=str(files["risk.json"]), allowlist_id="a1", allowlist_manifest_path=str(files["allow.json"]), dry_run_gate_id="d1", dry_run_gate_manifest_path=str(files["dry.json"]), warnings=[], recovery_instructions=["restore from snapshot"]) 


def test_create_and_manifest(tmp_path: Path) -> None:
    p = tmp_path / "p"; p.mkdir()
    data = tmp_path / "data"
    out = create_artifact_capture_record(**_ready(p, data))
    mpath = Path(out["manifest_path"])
    assert mpath.exists()
    assert str(data.resolve()) in str(mpath.resolve())
    m = out["manifest"]
    for k in ["schema_version", "artifact_gate_id", "project_path", "data_root", "artifact_capture_ready", "missing_required_artifacts", "blocking_reasons", "artifact_index", "summary"]:
        assert k in m


def test_missing_rules_block(tmp_path: Path) -> None:
    p = tmp_path / "p"; p.mkdir()
    data = tmp_path / "d"
    base = _ready(p, data)
    assert evaluate_artifact_capture_gate(**{**base, "plan_id": "", "plan_manifest_path": ""})["artifact_capture_ready"] is False
    assert evaluate_artifact_capture_gate(**{**base, "snapshot_id": "", "snapshot_manifest_path": ""})["artifact_capture_ready"] is False
    assert evaluate_artifact_capture_gate(**{**base, "transaction_id": "", "transaction_manifest_path": ""})["artifact_capture_ready"] is False
    assert evaluate_artifact_capture_gate(**{**base, "rollback_metadata_present": False})["artifact_capture_ready"] is False
    assert evaluate_artifact_capture_gate(**{**base, "risk_id": "", "risk_manifest_path": ""})["artifact_capture_ready"] is False
    assert evaluate_artifact_capture_gate(**{**base, "allowlist_id": "", "allowlist_manifest_path": ""})["artifact_capture_ready"] is False
    assert evaluate_artifact_capture_gate(**{**base, "dry_run_gate_id": "", "dry_run_gate_manifest_path": ""})["artifact_capture_ready"] is False
    assert evaluate_artifact_capture_gate(**{**base, "rollback_readiness_gate_id": "", "rollback_readiness_manifest_path": ""})["artifact_capture_ready"] is False
    assert evaluate_artifact_capture_gate(**{**base, "recovery_instructions": []})["artifact_capture_ready"] is False


def test_optional_missing_recorded_and_flags(tmp_path: Path) -> None:
    p = tmp_path / "p"; p.mkdir()
    data = tmp_path / "d"
    gate = evaluate_artifact_capture_gate(**_ready(p, data))
    assert gate["artifact_capture_ready"] is True
    assert "dry_run_result_reference" in gate["missing_optional_artifacts"]
    assert "execution_result_reference" in gate["missing_optional_artifacts"]
    assert "verification_plan_reference" in gate["missing_optional_artifacts"]
    assert "verification_result_reference" in gate["missing_optional_artifacts"]
    assert gate["automatic_execute_enabled"] is False
    assert gate["automatic_artifact_capture_enabled"] is False
    assert gate["automatic_verification_enabled"] is False
    assert gate["automatic_safe_apply_enabled"] is False
    assert gate["automatic_rollback_enabled"] is False


def test_evaluation_does_not_modify_project(tmp_path: Path) -> None:
    p = tmp_path / "p"; p.mkdir()
    f = p / "keep.txt"; f.write_text("x", encoding="utf-8")
    before = f.read_text(encoding="utf-8")
    _ = evaluate_artifact_capture_gate(**_ready(p, tmp_path / "d"))
    assert f.read_text(encoding="utf-8") == before


def test_no_subprocess_no_restore_no_safe_apply_no_ca_data_literal() -> None:
    src = Path("app/atlas/artifact_capture_gate.py").read_text(encoding="utf-8")
    assert "import subprocess" not in src
    assert "restore_workspace_snapshot" not in src
    assert "safe_apply(" not in src
    assert 'Path("ca_data")' not in src
