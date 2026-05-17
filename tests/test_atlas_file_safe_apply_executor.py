from pathlib import Path

from agent.atlas_file_safe_apply_executor import AtlasFileSafeApplyExecutor
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool


def _pool_and_item(tmp_path, *, action_type='update', target='doc.txt', metadata=None):
    pool = AtlasPlanPool(pool_id='p1', root_goal='g')
    item = AtlasPlanItem(
        item_id='i1',
        pool_id='p1',
        title='t',
        goal='g',
        item_type='implementation',
        risk_level='low',
        status='ready',
        target_files=[target],
        metadata={'action_type': action_type, **(metadata or {})},
    )
    return pool, item


def test_update_changes_real_file(tmp_path):
    f = Path(tmp_path) / 'doc.txt'; f.write_text('old\n', encoding='utf-8')
    pool, item = _pool_and_item(tmp_path, metadata={'proposed_content': 'new\n'})
    ex = AtlasFileSafeApplyExecutor(workspace_root=tmp_path)
    out = ex.apply_plan_item_safe(item=item, pool=pool)
    assert out['status'] == 'applied'
    assert out['actual_file_changed'] is True
    assert out['changed_files'] == ['doc.txt']
    assert f.read_text(encoding='utf-8') == 'new\n'


def test_create_makes_new_file(tmp_path):
    pool, item = _pool_and_item(tmp_path, action_type='create', target='new.txt', metadata={'proposed_content': 'abc\n'})
    ex = AtlasFileSafeApplyExecutor(workspace_root=tmp_path)
    out = ex.apply_plan_item_safe(item=item, pool=pool)
    assert out['status'] == 'applied'
    assert (Path(tmp_path) / 'new.txt').read_text(encoding='utf-8') == 'abc\n'


def test_unsupported_patch_is_blocked(tmp_path):
    f = Path(tmp_path) / 'doc.txt'; f.write_text('old\n', encoding='utf-8')
    pool, item = _pool_and_item(tmp_path, metadata={'patch': 'not a diff'})
    ex = AtlasFileSafeApplyExecutor(workspace_root=tmp_path)
    out = ex.apply_plan_item_safe(item=item, pool=pool)
    assert out['status'] == 'blocked'
    assert 'unsupported_patch_format' in out['reasons']


def test_forbidden_paths_and_actions_blocked(tmp_path):
    pool, item = _pool_and_item(tmp_path, target='../bad.txt', metadata={'proposed_content': 'x'})
    ex = AtlasFileSafeApplyExecutor(workspace_root=tmp_path)
    assert ex.apply_plan_item_safe(item=item, pool=pool)['status'] == 'blocked'
    _, del_item = _pool_and_item(tmp_path, action_type='delete', metadata={'proposed_content': 'x'})
    assert ex.apply_plan_item_safe(item=del_item, pool=pool)['status'] == 'blocked'
