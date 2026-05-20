from pathlib import Path

def test_safety_contract_no_forbidden_tokens():
    files=['agent/atlas_verification_recommendation_schema.py','agent/atlas_verification_recommendation_service.py','app/api/atlas_repo_context.py','tests/test_atlas_verification_recommendation_service.py','tests/test_atlas_verification_recommendation_api.py','tests/test_atlas_verification_recommendation_planpool_integration.py','tests/test_atlas_verification_recommendation_ui_contract.py']
    txt='\n'.join(Path(f).read_text() for f in files if Path(f).exists())
    for bad in ['shell=True','subprocess.run','git push','git pull','git clone','Path("ca_data")','runVerification','autoVerifyOne','safe_apply','patch generation','retry','rollback']:
        assert bad not in txt
