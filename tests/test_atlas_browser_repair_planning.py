from __future__ import annotations

from agent.atlas_patch_proposal_service import AtlasPatchProposalService
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_patch_proposal_schema import AtlasPatchProposalRequest


class _Storage:
    root_dir = 'ca_data'
    def __init__(self, pool): self._pool = pool
    def load_pool(self, _pid): return self._pool


class _Journal:
    def append_event(self, *a, **k): pass


def test_repair_prompt_for_browser_js_error_targets_browser_files_not_tests(tmp_path):
    (tmp_path / 'index.html').write_text('<script src="js/GameEngine.js"></script>', encoding='utf-8')
    item = AtlasPlanItem(
        item_id='i1', pool_id='p1', title='game', goal='repair browser game', item_type='implementation',
        risk_level='low', status='ready', target_files=['index.html', 'js/GameEngine.js'],
        metadata={'verification': {'status': 'failed', 'warnings': ['browser_smoke_failed:js_error:module_script_mismatch']}},
    )
    pool = AtlasPlanPool(pool_id='p1', root_goal='generated browser game', project_path=str(tmp_path), items=[item])
    svc = AtlasPatchProposalService(journal=_Journal(), storage=_Storage(pool))
    payload = svc.build_proposal_input(pool, item, AtlasPatchProposalRequest(pool_id='p1', item_id='i1'))
    feedback = svc._verification_feedback(payload)
    assert feedback is not None
    assert feedback['primary_reason'] == 'browser_smoke_failed:js_error:module_script_mismatch'
    assert feedback['repair_target_files'] == ['index.html', 'js/GameEngine.js']
    assert feedback['do_not_repair_by_tests_only'] is True
    assert 'Do NOT generate a Python test as the only repair' in feedback['instruction']
    assert 'index.html and relevant js/*.js' in feedback['instruction']
