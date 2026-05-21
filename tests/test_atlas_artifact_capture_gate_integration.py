from pathlib import Path

from app.atlas.artifact_capture_gate import create_artifact_capture_record, evaluate_artifact_capture_gate
from app.atlas.dry_run_approval_gate import create_dry_run_approval_record
from app.atlas.patch_transaction import create_patch_transaction
from app.atlas.risk_classification import create_risk_classification_record
from app.atlas.rollback_readiness_gate import create_rollback_readiness_record
from app.atlas.verification_allowlist import create_verification_allowlist_record
from app.atlas.workspace_snapshot import create_workspace_snapshot


def test_integration_references_and_non_mutation(tmp_path: Path) -> None:
    project = tmp_path / "p"; project.mkdir(); (project / "a.txt").write_text("x", encoding="utf-8")
    data = tmp_path / "d"
    snap = create_workspace_snapshot(project_path=project, data_root=data)
    txn = create_patch_transaction(project_path=project, data_root=data, snapshot_id=snap["snapshot_id"], snapshot_manifest_path=snap["manifest_path"], proposed_files=[{"relative_path": "a.txt", "change_type": "modify"}])
    risk = create_risk_classification_record(project_path=project, data_root=data, proposed_files=[{"relative_path": "a.txt", "change_type": "modify"}] )
    allow = create_verification_allowlist_record(project_path=project, data_root=data, proposed_commands=["pytest -q tests/test_atlas_workspace_snapshot_service.py"])
    dry = create_dry_run_approval_record(project_path=project, data_root=data, dry_run_status="passed", confirmation_token_present=True, confirmation_text="EXECUTE ONE ACTION", payload_valid=True, risk_level="low", transaction_id=txn["transaction_id"], snapshot_id=snap["snapshot_id"])
    rb = create_rollback_readiness_record(project_path=project, data_root=data, risk_level="low", transaction_id=txn["transaction_id"], transaction_manifest_path=txn["manifest_path"], snapshot_id=snap["snapshot_id"], snapshot_manifest_path=snap["manifest_path"], restore_plan_status="valid", restore_supported=True, restore_manual_only=True, rollback_metadata_present=True, rollback_strategy="restore_snapshot_manual", snapshot_manifest_valid=True, snapshot_path_safety_valid=True, transaction_rollback_metadata_valid=True, dry_run_gate_id=dry["gate_id"], dry_run_gate_manifest_path=dry["manifest_path"], dry_run_gate_ready=True)
    snap_before = Path(snap["manifest_path"]).read_text(encoding="utf-8")
    gate = evaluate_artifact_capture_gate(project_path=project, data_root=data, plan_id="p1", plan_summary="intent", snapshot_id=snap["snapshot_id"], snapshot_manifest_path=snap["manifest_path"], transaction_id=txn["transaction_id"], transaction_manifest_path=txn["manifest_path"], rollback_metadata_present=True, rollback_readiness_gate_id=rb["rollback_gate_id"], rollback_readiness_manifest_path=rb["manifest_path"], risk_id=risk["risk_id"], risk_manifest_path=risk["manifest_path"], allowlist_id=allow["allowlist_id"], allowlist_manifest_path=allow["manifest_path"], dry_run_gate_id=dry["gate_id"], dry_run_gate_manifest_path=dry["manifest_path"], warnings=[], recovery_instructions=["manual restore"])
    rec = create_artifact_capture_record(data_root=data, **gate)
    m = rec["manifest"]
    assert m["snapshot_reference_present"] is True
    assert m["transaction_reference_present"] is True
    assert m["risk_reference_present"] is True
    assert m["allowlist_reference_present"] is True
    assert m["dry_run_gate_reference_present"] is True
    assert m["rollback_readiness_reference_present"] is True
    assert Path(snap["manifest_path"]).read_text(encoding="utf-8") == snap_before
    assert "execution_result_reference" in m["missing_optional_artifacts"]
    assert "verification_result_reference" in m["missing_optional_artifacts"]


def test_integration_missing_blocks(tmp_path: Path) -> None:
    p = tmp_path / "p"; p.mkdir()
    data = tmp_path / "d"
    g = evaluate_artifact_capture_gate(project_path=p, data_root=data, plan_id="p", rollback_metadata_present=True, risk_id="r", allowlist_id="a", dry_run_gate_id="d", rollback_readiness_gate_id="rb", warnings=[], recovery_instructions=["x"])
    assert g["artifact_capture_ready"] is False
    assert "snapshot_reference_missing" in g["blocking_reasons"]
    assert "transaction_reference_missing" in g["blocking_reasons"]
