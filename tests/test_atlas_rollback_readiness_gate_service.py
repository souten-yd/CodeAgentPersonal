from pathlib import Path

from app.atlas.rollback_readiness_gate import create_rollback_readiness_record, evaluate_rollback_readiness_gate


def _ready(project: Path) -> dict:
    return dict(
        project_path=project,
        risk_level="low",
        transaction_id="txn1",
        snapshot_id="snap1",
        restore_plan_status="valid",
        restore_supported=True,
        restore_manual_only=True,
        rollback_metadata_present=True,
        rollback_strategy="restore_snapshot_manual",
        snapshot_manifest_valid=True,
        snapshot_path_safety_valid=True,
        transaction_rollback_metadata_valid=True,
        dry_run_gate_id="gate1",
        dry_run_gate_ready=True,
    )


def test_create_record_and_manifest(tmp_path: Path) -> None:
    p = tmp_path / "p"; p.mkdir()
    out = create_rollback_readiness_record(data_root=tmp_path / "data", **_ready(p))
    mpath = Path(out["manifest_path"])
    assert mpath.exists()
    assert str((tmp_path / "data").resolve()) in str(mpath.resolve())
    m = out["manifest"]
    for k in ["schema_version", "rollback_gate_id", "project_path", "data_root", "rollback_ready", "missing_requirements", "blocking_reasons", "summary"]:
        assert k in m


def test_rules_and_flags(tmp_path: Path) -> None:
    p = tmp_path / "p"; p.mkdir()
    assert evaluate_rollback_readiness_gate(project_path=p)["rollback_ready"] is False
    assert evaluate_rollback_readiness_gate(project_path=p, snapshot_id="s")['rollback_ready'] is False
    assert evaluate_rollback_readiness_gate(project_path=p, snapshot_id="s", snapshot_manifest_valid=False)["rollback_ready"] is False
    assert evaluate_rollback_readiness_gate(project_path=p, snapshot_id="s", snapshot_manifest_valid=True, snapshot_path_safety_valid=False)["rollback_ready"] is False
    assert evaluate_rollback_readiness_gate(project_path=p, snapshot_id="s", snapshot_manifest_valid=True, snapshot_path_safety_valid=True, restore_plan_status="missing")["rollback_ready"] is False
    assert evaluate_rollback_readiness_gate(project_path=p, snapshot_id="s", snapshot_manifest_valid=True, snapshot_path_safety_valid=True, restore_plan_status="invalid")["rollback_ready"] is False
    assert evaluate_rollback_readiness_gate(project_path=p, snapshot_id="s", snapshot_manifest_valid=True, snapshot_path_safety_valid=True, restore_plan_status="valid", rollback_metadata_present=False)["rollback_ready"] is False
    assert evaluate_rollback_readiness_gate(project_path=p, snapshot_id="s", snapshot_manifest_valid=True, snapshot_path_safety_valid=True, restore_plan_status="valid", rollback_metadata_present=True, transaction_id="t", transaction_rollback_metadata_valid=False)["rollback_ready"] is False
    assert evaluate_rollback_readiness_gate(project_path=p, snapshot_id="s", snapshot_manifest_valid=True, snapshot_path_safety_valid=True, restore_plan_status="valid", rollback_metadata_present=True, transaction_rollback_metadata_valid=True)["rollback_ready"] is False
    assert evaluate_rollback_readiness_gate(project_path=p, snapshot_id="s", snapshot_manifest_valid=True, snapshot_path_safety_valid=True, restore_plan_status="valid", rollback_metadata_present=True, transaction_id="t", transaction_rollback_metadata_valid=True)["rollback_ready"] is False
    assert evaluate_rollback_readiness_gate(**{**_ready(p), "risk_level": "unknown"})["rollback_ready"] is False
    high = evaluate_rollback_readiness_gate(**{**_ready(p), "risk_level": "high"})
    assert high["risk_requires_human_review"] is True
    ready = evaluate_rollback_readiness_gate(**_ready(p))
    assert ready["rollback_ready"] is True
    assert ready["automatic_rollback_enabled"] is False
    assert ready["automatic_restore_enabled"] is False
    assert ready["automatic_execute_enabled"] is False
    assert ready["automatic_verification_enabled"] is False
    assert ready["automatic_safe_apply_enabled"] is False


def test_evaluation_does_not_modify_project(tmp_path: Path) -> None:
    p = tmp_path / "p"; p.mkdir()
    f = p / "keep.txt"; f.write_text("x", encoding="utf-8")
    before = f.read_text(encoding="utf-8")
    _ = evaluate_rollback_readiness_gate(**_ready(p))
    assert f.read_text(encoding="utf-8") == before


def test_no_subprocess_no_restore_no_ca_data_literal() -> None:
    src = Path("app/atlas/rollback_readiness_gate.py").read_text(encoding="utf-8")
    assert "import subprocess" not in src
    assert "restore_workspace_snapshot" not in src
    assert 'Path("ca_data")' not in src
