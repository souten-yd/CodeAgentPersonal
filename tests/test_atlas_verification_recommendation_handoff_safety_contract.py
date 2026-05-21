from pathlib import Path


def test_no_forbidden_tokens_in_handoff_files():
    paths = [
        'agent/atlas_verification_recommendation_handoff_service.py',
        'agent/atlas_verification_recommendation_handoff_schema.py',
        'app/api/atlas_repo_context.py',
    ]
    text = '\n'.join(Path(p).read_text() for p in paths)
    for token in ['shell=True','subprocess.run','git push','git pull','git clone','Path("ca_data")','runVerification','autoVerifyOne','safe_apply','patch generation','retry','rollback']:
        assert token not in text
