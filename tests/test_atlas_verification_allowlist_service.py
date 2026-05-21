
from pathlib import Path
from app.atlas.verification_allowlist import create_verification_allowlist_record, classify_verification_command

def test_allowlist_record_and_policy(tmp_path: Path) -> None:
    project = tmp_path / 'project'; project.mkdir(); (project/'tests').mkdir(); (project/'app').mkdir(parents=True); (project/'web/js').mkdir(parents=True)
    rec = create_verification_allowlist_record(project_path=project, data_root=tmp_path/'data', proposed_commands=['pytest -q tests/test_example.py','pytest -q tests/test_example.py::test_name','python -m py_compile app/foo.py','node --check web/js/foo.js','pytest','git push origin main','rm -rf x','pip install x','pytest -q /tmp/a.py','pytest -q tests/../x.py','unknown cmd'], risk_level='medium')
    mpath = Path(rec['manifest_path']); assert mpath.exists()
    m = rec['manifest']
    for k in ['schema_version','allowlist_id','project_path','data_root','proposed_commands','command_results','policy','summary']:
        assert k in m
    assert m['automatic_verification_enabled'] is False
    assert all(r['automatic_execution_enabled'] is False for r in m['command_results'])
    assert any(r['allowed'] and r['category']=='pytest_targeted' for r in m['command_results'])
    assert any((not r['allowed']) and r['reason']=='broad_pytest_forbidden' for r in m['command_results'])
    assert any((not r['allowed']) and 'shell_metacharacter' in r['reason'] for r in [classify_verification_command(command='pytest -q tests/x.py; whoami', project_path=project, risk_level='low')])
    assert 'ca_data' not in str(mpath)

def test_classification_does_not_modify_files(tmp_path: Path) -> None:
    p = tmp_path / 'project'; p.mkdir(); f = p/'keep.txt'; f.write_text('x', encoding='utf-8')
    before = f.read_text(encoding='utf-8')
    r = classify_verification_command(command='pytest -q tests/test_example.py', project_path=p, risk_level='high')
    assert r['requires_human_approval'] is True
    assert f.read_text(encoding='utf-8') == before

def test_unknown_risk_is_blocked(tmp_path: Path) -> None:
    p=tmp_path/'p'; p.mkdir(); (p/'tests').mkdir()
    r = classify_verification_command(command='pytest -q tests/test_example.py', project_path=p, risk_level='mystery')
    assert r['allowed'] is False
    assert r['automatic_execution_enabled'] is False
