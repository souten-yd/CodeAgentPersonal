from agent.atlas_auto_policy_presets import atlas_auto_policy_presets
from agent.atlas_automation_gate_service import AtlasAutomationGateService
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool


def _pool_item(**kw):
    pool = AtlasPlanPool(pool_id='p1', root_goal='g', project_path=kw.pop('project_path', '/tmp/repo'))
    md = kw.pop('metadata', {})
    item = AtlasPlanItem(item_id='i1', pool_id='p1', title='t', goal='g', risk_level=kw.pop('risk_level', 'low'), item_type=kw.pop('item_type', 'implementation'), target_files=kw.pop('target_files', ['a.txt']), metadata=md, **kw)
    return pool, item


def test_manual_only_always_requires_manual():
    pool, item = _pool_item(metadata={'approval': {'decision': 'approved'}, 'patch': 'x', 'action_type': 'update'})
    d = AtlasAutomationGateService().decide_pre_safe_apply(pool, item, atlas_auto_policy_presets()['manual_only'])
    assert d.decision == 'require_manual'


def test_guarded_low_risk_allows_approved_patch_draft():
    pool, item = _pool_item(metadata={'approval': {'decision': 'approved'}, 'patch': 'x', 'action_type': 'update', 'source_proposal_id': 'pp1'})
    d = AtlasAutomationGateService().decide_pre_safe_apply(pool, item, atlas_auto_policy_presets()['guarded_low_risk'])
    assert d.decision == 'allow'


def test_guarded_low_risk_blocks_content_missing():
    pool, item = _pool_item(metadata={'approval': {'decision': 'approved'}, 'action_type': 'update', 'source_proposal_id': 'pp1'})
    d = AtlasAutomationGateService().decide_pre_safe_apply(pool, item, atlas_auto_policy_presets()['guarded_low_risk'])
    assert d.decision in {'block', 'require_manual'} and 'content_missing' in d.reasons


def test_guarded_low_risk_blocks_unapproved_item():
    pool, item = _pool_item(metadata={'patch': 'x', 'action_type': 'update', 'source_proposal_id': 'pp1'})
    assert AtlasAutomationGateService().decide_pre_safe_apply(pool, item, atlas_auto_policy_presets()['guarded_low_risk']).decision != 'allow'


def test_guarded_low_risk_blocks_delete_run_command():
    for action in ('delete', 'run_command'):
        pool, item = _pool_item(metadata={'approval': {'decision': 'approved'}, 'patch': 'x', 'action_type': action, 'source_proposal_id': 'pp1'})
        assert AtlasAutomationGateService().decide_pre_safe_apply(pool, item, atlas_auto_policy_presets()['guarded_low_risk']).decision == 'block'


def test_guarded_low_risk_blocks_medium_high_risk():
    for risk in ('medium', 'high'):
        pool, item = _pool_item(risk_level=risk, metadata={'approval': {'decision': 'approved'}, 'patch': 'x', 'action_type': 'update', 'source_proposal_id': 'pp1'})
        assert AtlasAutomationGateService().decide_pre_safe_apply(pool, item, atlas_auto_policy_presets()['guarded_low_risk']).decision == 'block'


def test_guarded_low_risk_requires_project_path():
    pool, item = _pool_item(project_path='', metadata={'approval': {'decision': 'approved'}, 'patch': 'x', 'action_type': 'update', 'source_proposal_id': 'pp1'})
    assert AtlasAutomationGateService().decide_pre_safe_apply(pool, item, atlas_auto_policy_presets()['guarded_low_risk']).decision != 'allow'
