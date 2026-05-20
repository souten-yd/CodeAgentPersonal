from pathlib import Path

def test_safety_patterns_absent():
    txt=(Path('agent/atlas_verification_planning_service.py').read_text()+Path('agent/atlas_verification_planning_schema.py').read_text())
    for bad in ['shell=True','subprocess.run','git push','git pull','git clone','Path("ca_data")','runVerification','autoVerifyOne','safe_apply','patch generation','retry','rollback']:
        assert bad not in txt
