from pathlib import Path

from app.atlas.dry_run_approval_gate import create_dry_run_approval_record, evaluate_dry_run_approval_gate


def _base(project: Path) -> dict:
    return dict(
        project_path=project,
        dry_run_status="passed",
        confirmation_token_present=True,
        confirmation_text="EXECUTE ONE ACTION",
        payload_valid=True,
        risk_level="low",
        transaction_id="txn1",
        snapshot_id="snap1",
    )


def test_create_record_and_manifest(tmp_path: Path) -> None:
    p = tmp_path / "p"; p.mkdir()
    out = create_dry_run_approval_record(data_root=tmp_path / "data", **_base(p))
    mpath = Path(out["manifest_path"])
    assert mpath.exists()
    assert "ca_data" not in str(mpath)
    m = out["manifest"]
    for k in ["schema_version", "gate_id", "project_path", "data_root", "gate_ready", "missing_requirements", "blocking_reasons", "summary"]:
        assert k in m


def test_gate_rules_and_flags(tmp_path: Path) -> None:
    p = tmp_path / "p"; p.mkdir()
    blocked = evaluate_dry_run_approval_gate(project_path=p, dry_run_status="missing")
    assert blocked["gate_ready"] is False
    assert "dry_run_passed" in blocked["missing_requirements"]

    failed = evaluate_dry_run_approval_gate(project_path=p, dry_run_status="failed")
    assert failed["gate_ready"] is False

    token_missing = evaluate_dry_run_approval_gate(project_path=p, dry_run_status="passed", payload_valid=True, confirmation_text="EXECUTE ONE ACTION")
    assert token_missing["gate_ready"] is False

    text_bad = evaluate_dry_run_approval_gate(project_path=p, dry_run_status="passed", payload_valid=True, confirmation_token_present=True, confirmation_text="WRONG")
    assert text_bad["gate_ready"] is False

    medium = evaluate_dry_run_approval_gate(project_path=p, dry_run_status="passed", payload_valid=True, confirmation_token_present=True, confirmation_text="EXECUTE ONE ACTION", risk_level="medium", transaction_id="t", snapshot_id="s")
    assert medium["requires_explicit_approval"] is True
    assert medium["explicit_approval_satisfied"] is False

    ready = evaluate_dry_run_approval_gate(project_path=p, dry_run_status="passed", payload_valid=True, confirmation_token_present=True, confirmation_text="EXECUTE ONE ACTION", risk_level="high", approval_status="approved", explicit_decision="approve", transaction_id="t", snapshot_id="s")
    assert ready["automatic_execute_enabled"] is False
    assert ready["automatic_dry_run_enabled"] is False
    assert ready["automatic_approval_enabled"] is False
    assert ready["automatic_verification_enabled"] is False
    assert ready["automatic_safe_apply_enabled"] is False
    assert ready["automatic_rollback_enabled"] is False

    low_ready = evaluate_dry_run_approval_gate(**_base(p))
    assert low_ready["gate_ready"] is True

    unknown = evaluate_dry_run_approval_gate(**{**_base(p), "risk_level": "unknown"})
    assert unknown["gate_ready"] is False


def test_evaluation_does_not_modify_project(tmp_path: Path) -> None:
    p = tmp_path / "p"; p.mkdir()
    f = p / "keep.txt"; f.write_text("x", encoding="utf-8")
    before = f.read_text(encoding="utf-8")
    _ = evaluate_dry_run_approval_gate(**_base(p))
    assert f.read_text(encoding="utf-8") == before


def test_no_subprocess_and_no_ca_data_literal() -> None:
    src = Path("app/atlas/dry_run_approval_gate.py").read_text(encoding="utf-8")
    assert "import subprocess" not in src
    assert "Path(\"ca_data\")" not in src
