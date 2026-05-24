import subprocess
import sys
from pathlib import Path

from app.atlas.readiness_gate_rollup import evaluate_readiness_gate_rollup


def _base(tmp_path: Path) -> dict:
    return {
        "project_path": tmp_path,
        "data_root": tmp_path,
        "snapshot_id": "s",
        "transaction_id": "t",
        "risk_id": "r",
        "allowlist_id": "a",
        "dry_run_gate_id": "d",
        "rollback_gate_id": "rb",
        "artifact_gate_id": "ag",
        "stop_gate_id": "sg",
        "loop_gate_id": "lg",
        "remote_git_gate_id": "rg",
        "self_improvement_gate_id": "si",
        "snapshot_ready": True,
        "patch_transaction_ready": True,
        "risk_classification_ready": True,
        "verification_allowlist_ready": True,
        "dry_run_approval_ready": True,
        "rollback_readiness_ready": True,
        "artifact_capture_ready": True,
        "stop_kill_switch_ready": True,
        "loop_bound_ready": True,
        "remote_git_gate_ready": True,
        "self_improvement_gate_ready": True,
        "recovery_instructions": ["manual recovery only"],
    }


def test_scale_114_rollup_contract_and_advisory_only(tmp_path: Path):
    payload = evaluate_readiness_gate_rollup(**_base(tmp_path))

    assert payload["advisory_only"] is True
    assert payload["computes_execution_eligibility"] is False
    assert payload["execution_enabled"] is False
    assert payload["runtime_level"] == "level_0_manual_only"
    assert payload["level1_execution_enabled"] is False
    assert payload["autonomous_execution_enabled"] is False

    expected_gates = {
        "snapshot",
        "transaction",
        "risk",
        "allowlist",
        "dry_run_gate",
        "rollback_readiness",
        "artifact_capture",
        "stop_gate",
        "loop_bound",
        "remote_git",
        "self_improvement",
    }
    assert set(payload["gate_evidence_summary"].keys()) == expected_gates
    assert all(v["evidence_status"] == "present" for v in payload["gate_evidence_summary"].values())


def test_scale_114_missing_evidence_is_explicit(tmp_path: Path):
    base = _base(tmp_path)
    base["remote_git_gate_id"] = ""
    base["remote_git_gate_ready"] = False
    payload = evaluate_readiness_gate_rollup(**base)

    assert payload["gate_evidence_summary"]["remote_git"]["evidence_status"] == "missing"
    assert "remote git gate" in payload["missing_required_gates"]
    assert "remote git gate" in payload["failed_required_gates"]


def test_scale_114_no_forbidden_execution_or_mutation_strings_introduced():
    src = Path("app/atlas/readiness_gate_rollup.py").read_text(encoding="utf-8")
    forbidden = [
        "@router.post(",
        "@router.put(",
        "@router.patch(",
        "@router.delete(",
        "safe_apply(",
        "git push",
        "git commit",
        "subprocess.run",
        "autonomous_loop",
        "self_modify",
    ]
    assert not [token for token in forbidden if token in src]


def test_scale_114_manifest_validator_still_passes():
    root = Path(__file__).resolve().parents[1]
    validator = root / "scripts" / "validate_atlas_automation_plan.py"
    result = subprocess.run(
        [sys.executable, str(validator)],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Atlas automation plan contract OK" in result.stdout
