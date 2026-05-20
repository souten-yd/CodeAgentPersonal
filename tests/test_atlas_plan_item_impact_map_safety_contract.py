from pathlib import Path


def test_no_forbidden_tokens():
    files = [
        'agent/atlas_plan_item_impact_map_schema.py',
        'agent/atlas_plan_item_impact_map_service.py',
        'app/api/atlas_repo_context.py',
        'tests/test_atlas_plan_item_impact_map_service.py',
        'tests/test_atlas_plan_item_impact_map_api.py',
        'tests/test_atlas_plan_item_impact_map_planpool_integration.py',
        'tests/test_atlas_plan_item_impact_map_ui_contract.py',
    ]
    text = '\n'.join(Path(f).read_text(encoding='utf-8') for f in files)
    for tok in ['shell=True', 'subprocess.run', 'git push', 'git pull', 'git clone', 'Path("ca_data")', 'runVerification', 'autoVerifyOne', 'safe_apply', 'patch generation', 'retry', 'rollback']:
        assert tok not in text
