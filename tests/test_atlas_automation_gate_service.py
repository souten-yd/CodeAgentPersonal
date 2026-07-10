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


def test_guarded_low_risk_allows_approved_surgical_edit_draft():
    pool, item = _pool_item(metadata={
        'approval': {'decision': 'approved'},
        'action_type': 'update',
        'source_proposal_id': 'pp1',
        'edits': [{'old_string': 'old', 'new_string': 'new'}],
    })
    d = AtlasAutomationGateService().decide_pre_safe_apply(pool, item, atlas_auto_policy_presets()['guarded_low_risk'])
    assert d.decision == 'allow'
    assert 'content_missing' not in d.reasons


def test_guarded_low_risk_blocks_content_missing():
    pool, item = _pool_item(metadata={'approval': {'decision': 'approved'}, 'action_type': 'update', 'source_proposal_id': 'pp1'})
    d = AtlasAutomationGateService().decide_pre_safe_apply(pool, item, atlas_auto_policy_presets()['guarded_low_risk'])
    assert d.decision in {'block', 'require_manual'} and 'content_missing' in d.reasons


def test_guarded_low_risk_allows_verified_already_satisfied_no_op():
    # Reproduces a 5th layer of the same live bug chain (#2128-#2131): a verified no-op (the step's
    # goal is already met by the file's existing content) carries no proposed_content/edits/etc, so
    # this gate's detect_executor_readable_content() saw it as content_missing and blocked
    # safe-apply even though proposal generation (fixed earlier) had already accepted it.
    pool, item = _pool_item(metadata={
        'approval': {'decision': 'approved'}, 'action_type': 'update', 'source_proposal_id': 'pp1',
        'already_satisfied_no_op': True,
    })
    d = AtlasAutomationGateService().decide_pre_safe_apply(pool, item, atlas_auto_policy_presets()['guarded_low_risk'])
    assert d.decision == 'allow'
    assert 'content_missing' not in d.reasons


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


def test_guarded_low_risk_allows_ordinary_multi_file_low_risk_item():
    # A left-unset max_changed_files_per_item on the DEFAULT preset falls back to the schema's
    # floor of 1, which would block nearly any real low-risk step (e.g. an HTML+CSS scaffold)
    # despite the preset otherwise gating on risk, not file count. 2 files must be allowed.
    pool, item = _pool_item(
        target_files=['index.html', 'style.css'],
        metadata={'approval': {'decision': 'approved'}, 'patch': 'x', 'action_type': 'create', 'source_proposal_id': 'pp1'},
    )
    d = AtlasAutomationGateService().decide_pre_safe_apply(pool, item, atlas_auto_policy_presets()['guarded_low_risk'])
    assert d.decision == 'allow'
    assert 'target_files_too_many' not in d.reasons


def test_guarded_low_risk_still_blocks_excessive_file_count():
    # The cap must still guard against a "low risk" item ballooning to touch many files.
    pool, item = _pool_item(
        target_files=[f'f{i}.py' for i in range(6)],
        metadata={'approval': {'decision': 'approved'}, 'patch': 'x', 'action_type': 'update', 'source_proposal_id': 'pp1'},
    )
    d = AtlasAutomationGateService().decide_pre_safe_apply(pool, item, atlas_auto_policy_presets()['guarded_low_risk'])
    assert d.decision != 'allow'
    assert 'target_files_too_many' in d.reasons
