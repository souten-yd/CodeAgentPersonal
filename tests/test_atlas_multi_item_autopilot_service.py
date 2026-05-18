from pathlib import Path
from agent.atlas_multi_item_autopilot_policies import list_multi_item_policies

def test_policies_present():
    ids = {p.policy_id for p in list_multi_item_policies()}
    assert 'guarded_multi_item_v1' in ids
    assert 'dry_run_multi_item_v1' in ids

def test_no_forbidden_strings():
    t = Path('agent/atlas_multi_item_autopilot_service.py').read_text(encoding='utf-8')
    assert 'shell=True' not in t
    assert 'git push' not in t
