from pathlib import Path
from app.atlas.workspace_snapshot import create_workspace_snapshot
from app.atlas.patch_transaction import create_patch_transaction
from app.atlas.risk_classification import create_risk_classification_record
from app.atlas.verification_allowlist import create_verification_allowlist_record
from app.atlas.dry_run_approval_gate import create_dry_run_approval_record
from app.atlas.rollback_readiness_gate import create_rollback_readiness_record
from app.atlas.artifact_capture_gate import create_artifact_capture_record
from app.atlas.stop_kill_switch_gate import create_stop_kill_switch_record
from app.atlas.loop_bound_gate import create_loop_bound_record
from app.atlas.remote_git_gate import create_remote_git_record
from app.atlas.self_improvement_gate import create_self_improvement_record, evaluate_self_improvement_gate

def test_integration_refs(tmp_path: Path):
    (tmp_path/'docs').mkdir(); (tmp_path/'docs'/'x.md').write_text('x',encoding='utf-8')
    snap=create_workspace_snapshot(project_path=tmp_path,data_root=tmp_path,include_paths=['docs/x.md'])
    tx=create_patch_transaction(project_path=tmp_path,data_root=tmp_path,proposed_files=[{'relative_path':'docs/x.md'}])
    risk=create_risk_classification_record(project_path=tmp_path,data_root=tmp_path,proposed_files=[{'relative_path':'docs/x.md'}])
    allow=create_verification_allowlist_record(project_path=tmp_path,data_root=tmp_path,proposed_commands=['pytest -q tests/test_atlas_quality_gate_contract.py'],risk_level='low')
    dry=create_dry_run_approval_record(project_path=tmp_path,data_root=tmp_path,risk_level='low',dry_run_status='passed',approval_status='approved',confirmation_token_present=True,explicit_decision='approve',payload_valid=True)
    rb=create_rollback_readiness_record(project_path=tmp_path,data_root=tmp_path,snapshot_id='s',snapshot_manifest_path=snap['manifest_path'],restore_plan_status='ready',restore_supported=True,restore_manual_only=True,rollback_metadata_present=True,snapshot_manifest_valid=True,snapshot_path_safety_valid=True,transaction_rollback_metadata_valid=True,dry_run_gate_ready=True)
    art=create_artifact_capture_record(project_path=tmp_path,data_root=tmp_path,plan_id='p',plan_summary='p',snapshot_id=snap['snapshot_id'],snapshot_manifest_path=snap['manifest_path'],transaction_id=tx['transaction_id'],transaction_manifest_path=tx['manifest_path'],rollback_metadata_present=True,rollback_readiness_gate_id=rb['rollback_gate_id'],rollback_readiness_manifest_path=rb['manifest_path'],risk_id=risk['risk_id'],risk_manifest_path=risk['manifest_path'],allowlist_id=allow['allowlist_id'],allowlist_manifest_path=allow['manifest_path'],dry_run_gate_id=dry['gate_id'],dry_run_gate_manifest_path=dry['manifest_path'],recovery_instructions=['manual'])
    st=create_stop_kill_switch_record(project_path=tmp_path,data_root=tmp_path,stop_state='armed',kill_switch_available=True,stop_state_visible=True,ui_stop_visible=True,cli_stop_available=True,api_stop_available=True,operator_loop_stop_visible=True,recovery_instructions=['manual'])
    loop=create_loop_bound_record(project_path=tmp_path,data_root=tmp_path,stop_gate_id='s',artifact_gate_id='a',dry_run_gate_id='d',rollback_gate_id='r',risk_id='k',max_actions_per_loop=1,max_retries=0,max_runtime_seconds=10,max_files_changed=1,max_consecutive_failures=0,max_verification_attempts=1,max_patch_transactions=1,max_risk_level='low',recovery_instructions=['manual'])
    rg=create_remote_git_record(project_path=tmp_path,data_root=tmp_path,loop_gate_id='l',stop_gate_id='s',artifact_gate_id='a',risk_id='r',dry_run_gate_id='d',recovery_instructions=['manual'])
    ev=evaluate_self_improvement_gate(project_path=tmp_path,data_root=tmp_path,self_improvement_requested=True,self_improvement_kind='docs_only',target_paths=['app/atlas/self_improvement_gate.py'],snapshot_id=snap['snapshot_id'],snapshot_manifest_path=snap['manifest_path'],transaction_id=tx['transaction_id'],transaction_manifest_path=tx['manifest_path'],risk_id=risk['risk_id'],risk_manifest_path=risk['manifest_path'],allowlist_id=allow['allowlist_id'],allowlist_manifest_path=allow['manifest_path'],dry_run_gate_id=dry['gate_id'],dry_run_gate_manifest_path=dry['manifest_path'],rollback_gate_id=rb['rollback_gate_id'],rollback_readiness_manifest_path=rb['manifest_path'],artifact_gate_id=art['artifact_gate_id'],artifact_capture_manifest_path=art['manifest_path'],stop_gate_id=st['stop_gate_id'],stop_gate_manifest_path=st['manifest_path'],loop_gate_id=loop['loop_gate_id'],loop_bound_manifest_path=loop['manifest_path'],remote_git_gate_id=rg['remote_git_gate_id'],remote_git_manifest_path=rg['manifest_path'],risk_level='strict_gate',strict_gate_satisfied=True,human_approval_present=True,dry_run_satisfied=True,rollback_ready=True,artifact_capture_ready=True,stop_gate_ready=True,loop_bound_ready=True,remote_git_gate_ready=True,verification_allowlist_ready=True,recovery_instructions=['manual'])
    assert ev['self_improvement_gate_ready'] is True
    rec=create_self_improvement_record(**{k:v for k,v in ev.items() if k!='data_root'},data_root=tmp_path)
    assert rec['manifest']['remote_git_gate_id']==rg['remote_git_gate_id']
    assert evaluate_self_improvement_gate(project_path=tmp_path,data_root=tmp_path,self_improvement_requested=True,self_improvement_kind='docs_only',target_paths=['docs/x.md'],snapshot_id='s',transaction_id='t',risk_id='r',allowlist_id='a',dry_run_gate_id='d',rollback_gate_id='rb',artifact_gate_id='ag',stop_gate_id='sg',loop_gate_id='lg',remote_git_gate_id='',risk_level='low',dry_run_satisfied=True,rollback_ready=True,artifact_capture_ready=True,stop_gate_ready=True,loop_bound_ready=True,remote_git_gate_ready=True,verification_allowlist_ready=True,recovery_instructions=['manual'])['self_improvement_gate_ready'] is False
