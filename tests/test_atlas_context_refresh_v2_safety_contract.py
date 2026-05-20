from pathlib import Path


def test_safety_tokens_absent():
    files = ['agent/atlas_context_refresh_v2_schema.py','agent/atlas_context_refresh_v2_service.py','app/api/atlas_context_refresh.py','tests/test_atlas_context_refresh_v2_service.py']
    bad = ['shell=True','subprocess.run','git push','git pull','git clone','Path("ca_data")','runVerification','autoVerifyOne','safe_apply','patch generation','retry','rollback']
    for f in files:
        t=Path(f).read_text(encoding='utf-8')
        for b in bad:
            assert b not in t
