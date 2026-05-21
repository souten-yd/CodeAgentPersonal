from pathlib import Path

from app.atlas.dry_run_approval_gate import create_dry_run_approval_record
from app.atlas.patch_transaction import create_patch_transaction
from app.atlas.risk_classification import create_risk_classification_record
from app.atlas.rollback_readiness_gate import create_rollback_readiness_record, evaluate_rollback_readiness_gate
from app.atlas.verification_allowlist import create_verification_allowlist_record
from app.atlas.workspace_snapshot import create_workspace_snapshot


def test_reference_integration_no_mutation(tmp_path: Path) -> None:
    project = tmp_path / "project"; project.mkdir(); (project / "tests").mkdir(); (project / "tests" / "a.py").write_text("print('x')\n", encoding="utf-8")
    data_root = tmp_path / "data"
    snap = create_workspace_snapshot(project_path=project, data_root=data_root, include_paths=["tests/a.py"])
    txn = create_patch_transaction(project_path=project, data_root=data_root, snapshot_id=snap["snapshot_id"], snapshot_manifest_path=snap["manifest_path"], proposed_files=[{"relative_path": "tests/a.py", "change_type": "modify"}])
    risk = create_risk_classification_record(project_path=project, data_root=data_root, proposed_files=["tests/a.py"])
    allow = create_verification_allowlist_record(project_path=project, data_root=data_root, proposed_commands=["pytest -q tests/a.py"], risk_level="low")
    dry = create_dry_run_approval_record(data_root=data_root, project_path=project, dry_run_status="passed", confirmation_token_present=True, confirmation_text="EXECUTE ONE ACTION", payload_valid=True, risk_level="low", transaction_id=txn["transaction_id"], snapshot_id=snap["snapshot_id"], allowlist_id=allow["allowlist_id"])

    files = [snap["manifest_path"], txn["manifest_path"], risk["manifest_path"], allow["manifest_path"], dry["manifest_path"]]
    before = {f: Path(f).read_text(encoding="utf-8") for f in files}

    gate = evaluate_rollback_readiness_gate(project_path=project, risk_level="low", risk_id=risk["risk_id"], allowlist_id=allow["allowlist_id"], transaction_id=txn["transaction_id"], transaction_manifest_path=txn["manifest_path"], snapshot_id=snap["snapshot_id"], snapshot_manifest_path=snap["manifest_path"], restore_plan_status="valid", restore_supported=True, restore_manual_only=True, rollback_metadata_present=True, rollback_strategy="restore_snapshot_manual", snapshot_manifest_valid=True, snapshot_path_safety_valid=True, transaction_rollback_metadata_valid=True, dry_run_gate_id=dry["gate_id"], dry_run_gate_manifest_path=dry["manifest_path"], dry_run_gate_ready=True)
    rec = create_rollback_readiness_record(data_root=data_root, **gate)
    m = rec["manifest"]
    assert m["snapshot_id"] == snap["snapshot_id"]
    assert m["transaction_id"] == txn["transaction_id"]
    assert m["risk_id"] == risk["risk_id"]
    assert m["dry_run_gate_id"] == dry["gate_id"]
    assert m["allowlist_id"] == allow["allowlist_id"]

    after = {f: Path(f).read_text(encoding="utf-8") for f in files}
    assert before == after


def test_missing_reference_blocks_and_no_restore_symbols(tmp_path: Path) -> None:
    p = tmp_path / "p"; p.mkdir()
    missing_txn = evaluate_rollback_readiness_gate(project_path=p, snapshot_id="s", snapshot_manifest_valid=True, snapshot_path_safety_valid=True, restore_plan_status="valid", restore_supported=True, rollback_metadata_present=True, rollback_strategy="restore_snapshot_manual", transaction_rollback_metadata_valid=True, dry_run_gate_id="g", dry_run_gate_ready=True, risk_level="low")
    assert missing_txn["rollback_ready"] is False
    missing_snap = evaluate_rollback_readiness_gate(project_path=p, transaction_id="t", restore_plan_status="valid", restore_supported=True, rollback_metadata_present=True, rollback_strategy="restore_snapshot_manual", transaction_rollback_metadata_valid=True, dry_run_gate_id="g", dry_run_gate_ready=True, risk_level="low")
    assert missing_snap["rollback_ready"] is False
    missing_plan = evaluate_rollback_readiness_gate(project_path=p, transaction_id="t", snapshot_id="s", snapshot_manifest_valid=True, snapshot_path_safety_valid=True, restore_supported=True, rollback_metadata_present=True, rollback_strategy="restore_snapshot_manual", transaction_rollback_metadata_valid=True, dry_run_gate_id="g", dry_run_gate_ready=True, risk_level="low")
    assert missing_plan["rollback_ready"] is False
    src = Path("app/atlas/rollback_readiness_gate.py").read_text(encoding="utf-8")
    assert "AtlasSafeApply" not in src
    assert "restore_workspace_snapshot" not in src
    assert "verification" in src
