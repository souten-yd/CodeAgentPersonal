from pathlib import Path
from app.atlas.self_improvement_gate import create_self_improvement_record, evaluate_self_improvement_gate


def _ok(tmp_path: Path):
    return dict(project_path=tmp_path, data_root=tmp_path, self_improvement_requested=True, self_improvement_kind='docs_only', target_paths=['docs/a.md'], snapshot_id='s', transaction_id='t', risk_id='r', allowlist_id='a', dry_run_gate_id='d', rollback_gate_id='rb', artifact_gate_id='ag', stop_gate_id='sg', loop_gate_id='lg', remote_git_gate_id='rg', risk_level='low', dry_run_satisfied=True, rollback_ready=True, artifact_capture_ready=True, stop_gate_ready=True, loop_bound_ready=True, remote_git_gate_ready=True, verification_allowlist_ready=True, recovery_instructions=['manual'])


def test_create_and_manifest(tmp_path: Path):
    rec = create_self_improvement_record(**_ok(tmp_path))
    assert rec['manifest_path'].startswith(str(tmp_path)) and Path(rec['manifest_path']).exists()
    m = rec['manifest']
    for k in ['schema_version','self_improvement_gate_id','project_path','data_root','self_improvement_gate_ready','missing_required_gates','unsafe_automation_flags','blocking_reasons','self_improvement_state_summary','summary']:
        assert k in m


def test_blocking_and_strict_and_static_contracts(tmp_path: Path):
    assert evaluate_self_improvement_gate(**{**_ok(tmp_path), 'self_improvement_kind':'unknown'})['self_improvement_gate_ready'] is False
    assert evaluate_self_improvement_gate(**{**_ok(tmp_path), 'risk_level':'unknown'})['self_improvement_gate_ready'] is False
    assert evaluate_self_improvement_gate(**{**_ok(tmp_path), 'target_paths':['/x']})['self_improvement_gate_ready'] is False
    assert evaluate_self_improvement_gate(**{**_ok(tmp_path), 'target_paths':['../x']})['self_improvement_gate_ready'] is False
    for p in ['app/atlas/a.py','app/api/a.py','agent/x.py','ui.html','web/js/atlas_dashboard.js','docs/atlas_autonomous_execution_readiness_policy.md','tests/test_atlas_quality_gate_contract.py']:
        assert evaluate_self_improvement_gate(**{**_ok(tmp_path), 'target_paths':[p]})['strict_gate_required'] is True
    assert evaluate_self_improvement_gate(**{**_ok(tmp_path), 'self_improvement_kind':'self_modification'})['self_improvement_gate_ready'] is False
    for miss in ['snapshot_id','transaction_id','risk_id','allowlist_id','dry_run_gate_id','rollback_gate_id','artifact_gate_id','stop_gate_id','loop_gate_id','remote_git_gate_id']:
        b=_ok(tmp_path); b[miss]=''; assert evaluate_self_improvement_gate(**b)['self_improvement_gate_ready'] is False
    for flag in ['dry_run_satisfied','rollback_ready','artifact_capture_ready','stop_gate_ready','loop_bound_ready','remote_git_gate_ready','verification_allowlist_ready']:
        assert evaluate_self_improvement_gate(**{**_ok(tmp_path), flag: False})['self_improvement_gate_ready'] is False
    assert evaluate_self_improvement_gate(**{**_ok(tmp_path), 'recovery_instructions':[]})['self_improvement_gate_ready'] is False
    for flag in ['autonomous_self_improvement_enabled','automatic_self_modification_enabled','automatic_patch_generation_enabled','automatic_patch_apply_enabled','automatic_safe_apply_enabled','automatic_verification_enabled','automatic_command_execution_enabled','remote_git_operations_enabled','automatic_pr_creation_enabled','direct_merge_enabled']:
        assert evaluate_self_improvement_gate(**_ok(tmp_path), **{flag: True})['self_improvement_gate_ready'] is False
    r = evaluate_self_improvement_gate(**_ok(tmp_path))
    assert r['self_improvement_gate_ready'] is True and r['autonomous_self_improvement_enabled'] is False
    s = Path('app/atlas/self_improvement_gate.py').read_text(encoding='utf-8')
    assert 'Path("ca_data")' not in s and 'import subprocess' not in s and 'subprocess.run' not in s and 'safe_apply(' not in s and 'restore_workspace_snapshot(' not in s and 'git push' not in s
