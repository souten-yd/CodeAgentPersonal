
from app.atlas.verification_allowlist import classify_verification_command, create_verification_allowlist_record

def test_risk_policy(tmp_path):
    p=tmp_path/'p'; p.mkdir(); (p/'tests').mkdir()
    assert classify_verification_command(command='pytest -q tests/test_x.py', project_path=p, risk_level='low')['allowed'] is True
    assert classify_verification_command(command='pytest -q tests/test_x.py', project_path=p, risk_level='medium')['requires_human_approval'] is True
    assert classify_verification_command(command='pytest -q tests/test_x.py', project_path=p, risk_level='high')['requires_human_approval'] is True
    assert classify_verification_command(command='pytest -q tests/test_x.py', project_path=p, risk_level='strict_gate')['requires_human_approval'] is True
    assert classify_verification_command(command='pytest -q tests/test_x.py', project_path=p, risk_level='unknownx')['allowed'] is False
    rec=create_verification_allowlist_record(project_path=p,data_root=tmp_path/'d',proposed_commands=['pytest -q tests/test_x.py','pytest'],risk_level='high')
    s=rec['manifest']['summary']; assert s['allowed_count']>=0 and s['blocked_count']>=1 and s['human_approval_required'] is True
