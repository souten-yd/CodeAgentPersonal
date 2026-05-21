from pathlib import Path

from app.atlas.dry_run_approval_gate import create_dry_run_approval_record, evaluate_dry_run_approval_gate
from app.atlas.patch_transaction import create_patch_transaction
from app.atlas.risk_classification import create_risk_classification_record
from app.atlas.verification_allowlist import create_verification_allowlist_record


def test_gate_reference_integration_no_mutation(tmp_path: Path) -> None:
    project = tmp_path / "project"; project.mkdir(); (project / "tests").mkdir(); (project / "web/js").mkdir(parents=True)
    data_root = tmp_path / "data"
    txn = create_patch_transaction(project_path=project, data_root=data_root, snapshot_id="snap1", proposed_files=[{"relative_path": "tests/a.py", "change_type": "modify"}])
    risk = create_risk_classification_record(project_path=project, data_root=data_root, proposed_files=["tests/a.py"])
    allow = create_verification_allowlist_record(project_path=project, data_root=data_root, proposed_commands=["pytest -q tests/a.py"], risk_level="low")

    t_before = Path(txn["manifest_path"]).read_text(encoding="utf-8")
    r_before = Path(risk["manifest_path"]).read_text(encoding="utf-8")
    a_before = Path(allow["manifest_path"]).read_text(encoding="utf-8")

    gate = evaluate_dry_run_approval_gate(
        project_path=project,
        dry_run_status="passed",
        confirmation_token_present=True,
        confirmation_text="EXECUTE ONE ACTION",
        payload_valid=True,
        risk_level="low",
        transaction_id=txn["transaction_id"],
        risk_id=risk["risk_id"],
        allowlist_id=allow["allowlist_id"],
        snapshot_id="snap1",
    )
    rec = create_dry_run_approval_record(data_root=data_root, project_path=project, dry_run_status="passed", confirmation_token_present=True, confirmation_text="EXECUTE ONE ACTION", payload_valid=True, risk_level="low", transaction_id=txn["transaction_id"], risk_id=risk["risk_id"], allowlist_id=allow["allowlist_id"], snapshot_id="snap1")
    assert rec["manifest"]["transaction_id"] == txn["transaction_id"]
    assert rec["manifest"]["risk_id"] == risk["risk_id"]
    assert rec["manifest"]["allowlist_id"] == allow["allowlist_id"]

    assert Path(txn["manifest_path"]).read_text(encoding="utf-8") == t_before
    assert Path(risk["manifest_path"]).read_text(encoding="utf-8") == r_before
    assert Path(allow["manifest_path"]).read_text(encoding="utf-8") == a_before


def test_missing_references_policy(tmp_path: Path) -> None:
    p = tmp_path / "p"; p.mkdir()
    blocked = evaluate_dry_run_approval_gate(project_path=p, dry_run_status="passed", confirmation_token_present=True, confirmation_text="EXECUTE ONE ACTION", payload_valid=True, risk_level="low")
    assert blocked["gate_ready"] is False
    assert "transaction_reference_required" in blocked["blocking_reasons"]
    assert "snapshot_reference_required" in blocked["blocking_reasons"]
    assert "allowlist_reference_missing" in blocked["warnings"]
    src = Path("app/atlas/dry_run_approval_gate.py").read_text(encoding="utf-8")
    assert "restore" not in src
    assert "import subprocess" not in src
