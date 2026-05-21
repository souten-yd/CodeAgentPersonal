from pathlib import Path
from app.atlas.readiness_gate_rollup import create_readiness_gate_rollup_record, evaluate_readiness_gate_rollup


def _ok(tmp_path: Path):
    return dict(project_path=tmp_path, data_root=tmp_path, snapshot_id='s', transaction_id='t', risk_id='r', allowlist_id='a', dry_run_gate_id='d', rollback_gate_id='rb', artifact_gate_id='ag', stop_gate_id='sg', loop_gate_id='lg', remote_git_gate_id='rg', self_improvement_gate_id='si', snapshot_ready=True, patch_transaction_ready=True, risk_classification_ready=True, verification_allowlist_ready=True, dry_run_approval_ready=True, rollback_readiness_ready=True, artifact_capture_ready=True, stop_kill_switch_ready=True, loop_bound_ready=True, remote_git_gate_ready=True, self_improvement_gate_ready=True, recovery_instructions=['manual'])


def test_create_and_contract(tmp_path: Path):
    rec = create_readiness_gate_rollup_record(**_ok(tmp_path))
    assert rec['manifest_path'].startswith(str(tmp_path)) and Path(rec['manifest_path']).exists()
    m = rec['manifest']
    for k in ['schema_version','readiness_rollup_id','project_path','data_root','readiness_rollup_ready','level0_foundation_complete','runtime_level','missing_required_gates','failed_required_gates','unsafe_automation_flags','blocking_reasons','level0_state_summary','summary']:
        assert k in m


def test_blocking_cases_and_static_safety(tmp_path: Path):
    for miss in ['snapshot_id','transaction_id','risk_id','allowlist_id','dry_run_gate_id','rollback_gate_id','artifact_gate_id','stop_gate_id','loop_gate_id','remote_git_gate_id','self_improvement_gate_id']:
        b=_ok(tmp_path); b[miss]=''; assert evaluate_readiness_gate_rollup(**b)['readiness_rollup_ready'] is False
    for flag in ['snapshot_ready','patch_transaction_ready','risk_classification_ready','verification_allowlist_ready','dry_run_approval_ready','rollback_readiness_ready','artifact_capture_ready','stop_kill_switch_ready','loop_bound_ready','remote_git_gate_ready','self_improvement_gate_ready']:
        assert evaluate_readiness_gate_rollup(**{**_ok(tmp_path), flag:False})['readiness_rollup_ready'] is False
    assert evaluate_readiness_gate_rollup(**{**_ok(tmp_path), 'runtime_level':'unknown'})['readiness_rollup_ready'] is False
    assert evaluate_readiness_gate_rollup(**{**_ok(tmp_path), 'runtime_level':'level_1_guarded_execution_candidate'})['readiness_rollup_ready'] is False
    for f in ['level1_execution_enabled','autonomous_execution_enabled','automatic_execute_enabled','automatic_command_execution_enabled','automatic_verification_enabled','automatic_patch_generation_enabled','automatic_patch_apply_enabled','automatic_safe_apply_enabled','automatic_rollback_enabled','automatic_restore_enabled','automatic_loop_enabled','automatic_retry_enabled','auto_continue_enabled','execute_all_enabled','remote_git_operations_enabled','direct_merge_enabled']:
        assert evaluate_readiness_gate_rollup(**_ok(tmp_path), **{f:True})['readiness_rollup_ready'] is False
    for f in ['vue_next_started','vue_next_default_enabled','vue_next_execution_enabled']:
        assert evaluate_readiness_gate_rollup(**_ok(tmp_path), **{f:True})['readiness_rollup_ready'] is False
    assert evaluate_readiness_gate_rollup(**{**_ok(tmp_path), 'recovery_instructions':[]})['readiness_rollup_ready'] is False
    r=evaluate_readiness_gate_rollup(**_ok(tmp_path)); assert r['readiness_rollup_ready'] is True and r['level1_execution_enabled'] is False
    src=Path('app/atlas/readiness_gate_rollup.py').read_text(encoding='utf-8')
    assert 'Path("ca_data")' not in src and 'import subprocess' not in src and 'safe_apply(' not in src and 'restore_workspace_snapshot(' not in src and 'git push' not in src
