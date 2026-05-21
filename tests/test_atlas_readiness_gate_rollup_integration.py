from pathlib import Path
from app.atlas.workspace_snapshot import create_workspace_snapshot
from app.atlas.patch_transaction import create_patch_transaction
from app.atlas.risk_classification import create_risk_classification_record
from app.atlas.verification_allowlist import create_verification_allowlist_record
from app.atlas.readiness_gate_rollup import evaluate_readiness_gate_rollup, create_readiness_gate_rollup_record


def test_rollup_integration(tmp_path: Path):
    (tmp_path/'a.txt').write_text('x',encoding='utf-8')
    s=create_workspace_snapshot(project_path=tmp_path,data_root=tmp_path,include_paths=['a.txt'])
    t=create_patch_transaction(project_path=tmp_path,data_root=tmp_path,snapshot_id=s['snapshot_id'],proposed_files=[{'path':'a.txt','change_type':'modify'}])
    r=create_risk_classification_record(project_path=tmp_path,data_root=tmp_path,proposed_files=['a.txt'],transaction_id=t['transaction_id'])
    a=create_verification_allowlist_record(project_path=tmp_path,data_root=tmp_path,proposed_commands=['python -m py_compile app/atlas/readiness_gate_rollup.py'],risk_level='low',risk_id=r['risk_id'],transaction_id=t['transaction_id'])
    ev=evaluate_readiness_gate_rollup(project_path=tmp_path,data_root=tmp_path,snapshot_id=s['snapshot_id'],transaction_id=t['transaction_id'],risk_id=r['risk_id'],allowlist_id=a['allowlist_id'],dry_run_gate_id='d',rollback_gate_id='rb',artifact_gate_id='ag',stop_gate_id='sg',loop_gate_id='lg',remote_git_gate_id='rg',self_improvement_gate_id='si',snapshot_ready=True,patch_transaction_ready=True,risk_classification_ready=True,verification_allowlist_ready=True,dry_run_approval_ready=True,rollback_readiness_ready=True,artifact_capture_ready=True,stop_kill_switch_ready=True,loop_bound_ready=True,remote_git_gate_ready=True,self_improvement_gate_ready=True,recovery_instructions=['manual'])
    ev2=dict(ev); ev2.pop('data_root',None); rec=create_readiness_gate_rollup_record(data_root=tmp_path,**ev2)
    assert Path(rec['manifest_path']).exists()
    assert rec['manifest']['snapshot_id']==s['snapshot_id'] and rec['manifest']['transaction_id']==t['transaction_id']
    assert evaluate_readiness_gate_rollup(**{**ev,'self_improvement_gate_id':''})['readiness_rollup_ready'] is False
    assert evaluate_readiness_gate_rollup(**{**ev,'remote_git_gate_id':''})['readiness_rollup_ready'] is False
    assert evaluate_readiness_gate_rollup(**{**ev,'loop_gate_id':''})['readiness_rollup_ready'] is False
    assert evaluate_readiness_gate_rollup(**{**ev,'snapshot_manifest_path':'/tmp/bad.json'})['readiness_rollup_ready'] is False
