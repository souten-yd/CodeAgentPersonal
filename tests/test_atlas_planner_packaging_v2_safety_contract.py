from pathlib import Path

def test_forbidden_tokens_absent():
    files=['agent/atlas_planner_packaging_v2_schema.py','agent/atlas_planner_packaging_v2_service.py','tests/test_atlas_planner_packaging_v2_service.py','tests/test_atlas_planner_packaging_v2_api.py']
    text='\n'.join(Path(f).read_text() for f in files)
    for t in ['shell=True','subprocess.run','git push','git pull','git clone','Path("ca_data")']:
        assert t not in text
