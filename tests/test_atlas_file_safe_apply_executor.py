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


def test_multi_file_apply_success(tmp_path):
    pool = AtlasPlanPool(pool_id='p1', root_goal='g')
    item = AtlasPlanItem(
        item_id='i1',
        pool_id='p1',
        title='t',
        goal='g',
        item_type='implementation',
        risk_level='low',
        status='ready',
        target_files=['index.html'],
        metadata={
            'action_type': 'create',
            'file_changes': [
                {'change_id': 'fc_index', 'path': 'index.html', 'action_type': 'create', 'proposed_content': '<!doctype html>\n'},
                {'change_id': 'fc_css', 'path': 'style.css', 'action_type': 'create', 'proposed_content': 'body{}\n'},
            ],
        },
    )
    out = AtlasFileSafeApplyExecutor(workspace_root=tmp_path).apply_plan_item_safe(item=item, pool=pool)
    assert out['status'] == 'applied'
    assert out['changed_files'] == ['index.html', 'style.css']
    assert [r['status'] for r in out['file_results']] == ['applied', 'applied']
    assert (Path(tmp_path) / 'index.html').read_text(encoding='utf-8') == '<!doctype html>\n'
    assert (Path(tmp_path) / 'style.css').read_text(encoding='utf-8') == 'body{}\n'
    assert item.target_files == ['index.html', 'style.css']


def test_multi_file_requires_file_changes(tmp_path):
    pool, item = _pool_and_item(tmp_path, action_type='create', target='index.html', metadata={'proposed_content': '<!doctype html>\n'})
    item.target_files = ['index.html', 'style.css']
    out = AtlasFileSafeApplyExecutor(workspace_root=tmp_path).apply_plan_item_safe(item=item, pool=pool)
    assert out['status'] == 'blocked'
    assert 'multi_file_item_requires_file_changes' in out['reasons']


def test_multi_file_duplicate_path_blocks_without_writes(tmp_path):
    pool = AtlasPlanPool(pool_id='p1', root_goal='g')
    item = AtlasPlanItem(item_id='i1', pool_id='p1', title='t', goal='g', item_type='implementation', risk_level='low', status='ready', metadata={
        'action_type': 'create',
        'file_changes': [
            {'path': 'a.txt', 'action_type': 'create', 'proposed_content': 'one\n'},
            {'path': 'a.txt', 'action_type': 'create', 'proposed_content': 'two\n'},
        ],
    })
    out = AtlasFileSafeApplyExecutor(workspace_root=tmp_path).apply_plan_item_safe(item=item, pool=pool)
    assert out['status'] == 'blocked'
    assert 'duplicate_file_change_path' in out['reasons']
    assert not (Path(tmp_path) / 'a.txt').exists()


def test_critical_risk_blocks_even_with_valid_file_changes(tmp_path):
    pool = AtlasPlanPool(pool_id='p1', root_goal='g')
    item = AtlasPlanItem(item_id='i1', pool_id='p1', title='t', goal='g', item_type='implementation', risk_level='critical', status='ready', metadata={
        'action_type': 'create',
        'file_changes': [{'path': 'a.txt', 'action_type': 'create', 'proposed_content': 'a\n'}],
    })
    out = AtlasFileSafeApplyExecutor(workspace_root=tmp_path).apply_plan_item_safe(item=item, pool=pool)
    assert out['status'] == 'blocked'
    assert 'critical_risk_not_allowed' in out['reasons']
    assert not (Path(tmp_path) / 'a.txt').exists()


def test_multi_file_preflight_atomicity_content_missing(tmp_path):
    pool = AtlasPlanPool(pool_id='p1', root_goal='g')
    item = AtlasPlanItem(item_id='i1', pool_id='p1', title='t', goal='g', item_type='implementation', risk_level='low', status='ready', metadata={
        'action_type': 'create',
        'file_changes': [
            {'path': 'a.txt', 'action_type': 'create', 'proposed_content': 'a\n'},
            {'path': 'b.txt', 'action_type': 'create'},
            {'path': 'c.txt', 'action_type': 'create', 'proposed_content': 'c\n'},
        ],
    })
    out = AtlasFileSafeApplyExecutor(workspace_root=tmp_path).apply_plan_item_safe(item=item, pool=pool)
    assert out['status'] == 'blocked'
    assert 'multi_file_preflight_failed' in out['reasons']
    assert any(r.get('reason') == 'content_missing' for r in out['file_results'])
    assert not (Path(tmp_path) / 'a.txt').exists()
    assert not (Path(tmp_path) / 'c.txt').exists()


def test_multi_file_unsafe_path_atomicity(tmp_path):
    pool = AtlasPlanPool(pool_id='p1', root_goal='g')
    item = AtlasPlanItem(item_id='i1', pool_id='p1', title='t', goal='g', item_type='implementation', risk_level='low', status='ready', metadata={
        'action_type': 'create',
        'file_changes': [
            {'path': 'safe.txt', 'action_type': 'create', 'proposed_content': 'safe\n'},
            {'path': '../evil.txt', 'action_type': 'create', 'proposed_content': 'evil\n'},
        ],
    })
    out = AtlasFileSafeApplyExecutor(workspace_root=tmp_path).apply_plan_item_safe(item=item, pool=pool)
    assert out['status'] == 'blocked'
    assert 'unsafe_target_path' in out['reasons']
    assert not (Path(tmp_path) / 'safe.txt').exists()


def test_multi_file_update_target_missing_blocks_without_writes(tmp_path):
    pool = AtlasPlanPool(pool_id='p1', root_goal='g')
    item = AtlasPlanItem(item_id='i1', pool_id='p1', title='t', goal='g', item_type='implementation', risk_level='low', status='ready', metadata={
        'action_type': 'update',
        'file_changes': [{'path': 'missing.txt', 'action_type': 'update', 'proposed_content': 'x\n'}],
    })
    out = AtlasFileSafeApplyExecutor(workspace_root=tmp_path).apply_plan_item_safe(item=item, pool=pool)
    assert out['status'] == 'blocked'
    assert 'update_target_missing' in out['reasons']


def test_multi_file_no_effective_change_blocks_without_writes(tmp_path):
    (Path(tmp_path) / 'a.txt').write_text('same\n', encoding='utf-8')
    pool = AtlasPlanPool(pool_id='p1', root_goal='g')
    item = AtlasPlanItem(item_id='i1', pool_id='p1', title='t', goal='g', item_type='implementation', risk_level='low', status='ready', metadata={
        'action_type': 'update',
        'file_changes': [
            {'path': 'a.txt', 'action_type': 'update', 'proposed_content': 'same\n'},
            {'path': 'b.txt', 'action_type': 'create', 'proposed_content': 'b\n'},
        ],
    })
    out = AtlasFileSafeApplyExecutor(workspace_root=tmp_path).apply_plan_item_safe(item=item, pool=pool)
    assert out['status'] == 'blocked'
    assert 'no_effective_change' in out['reasons']
    assert not (Path(tmp_path) / 'b.txt').exists()


def test_multi_file_diagnoses_all_file_changes(tmp_path):
    pool = AtlasPlanPool(pool_id='p1', root_goal='g')
    item = AtlasPlanItem(item_id='i1', pool_id='p1', title='t', goal='g', item_type='implementation', risk_level='low', status='ready', metadata={
        'action_type': 'create',
        'file_changes': [
            {'path': '../bad.txt', 'action_type': 'create', 'proposed_content': 'bad\n'},
            {'path': 'missing.txt', 'action_type': 'update', 'proposed_content': 'x\n'},
            {'path': 'empty.txt', 'action_type': 'create'},
        ],
    })
    out = AtlasFileSafeApplyExecutor(workspace_root=tmp_path).apply_plan_item_safe(item=item, pool=pool)
    reasons = [r.get('reason') for r in out['file_results']]
    assert 'unsafe_target_path' in reasons
    assert 'update_target_missing' in reasons
    assert 'content_missing' in reasons


def test_multi_file_write_failure_rollback_deletes_created_file(tmp_path, monkeypatch):
    """When b.txt write fails, the already-created a.txt is rolled back (deleted)."""
    pool = AtlasPlanPool(pool_id='p1', root_goal='g')
    item = AtlasPlanItem(item_id='i1', pool_id='p1', title='t', goal='g', item_type='implementation', risk_level='low', status='ready', metadata={
        'action_type': 'create',
        'file_changes': [
            {'path': 'a.txt', 'action_type': 'create', 'proposed_content': 'a\n'},
            {'path': 'b.txt', 'action_type': 'create', 'proposed_content': 'b\n'},
        ],
    })
    original_write_text = Path.write_text

    def fail_on_b(self, *args, **kwargs):
        if self.name == 'b.txt':
            raise OSError('disk full')
        return original_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, 'write_text', fail_on_b)
    out = AtlasFileSafeApplyExecutor(workspace_root=tmp_path).apply_plan_item_safe(item=item, pool=pool)
    assert out['status'] == 'failed'
    assert out['rollback_attempted'] is True
    assert out['rollback_succeeded'] is True
    assert out['partial_write_possible'] is False
    assert out['changed_files'] == []
    assert 'a.txt' in out['restored_files']
    assert out['unrestored_files'] == []
    assert not (Path(tmp_path) / 'a.txt').exists()
    assert any(r.get('reason') == 'write_failed' for r in out['file_results'])


def test_multi_file_write_failure_rollback_restores_updated_file(tmp_path, monkeypatch):
    """When b.txt write fails, the already-updated a.txt is rolled back to original content."""
    (Path(tmp_path) / 'a.txt').write_text('original\n', encoding='utf-8')
    pool = AtlasPlanPool(pool_id='p1', root_goal='g')
    item = AtlasPlanItem(item_id='i1', pool_id='p1', title='t', goal='g', item_type='implementation', risk_level='low', status='ready', metadata={
        'action_type': 'update',
        'file_changes': [
            {'path': 'a.txt', 'action_type': 'update', 'proposed_content': 'updated\n'},
            {'path': 'b.txt', 'action_type': 'create', 'proposed_content': 'b\n'},
        ],
    })
    original_write_text = Path.write_text

    def fail_on_b(self, *args, **kwargs):
        if self.name == 'b.txt':
            raise OSError('disk full')
        return original_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, 'write_text', fail_on_b)
    out = AtlasFileSafeApplyExecutor(workspace_root=tmp_path).apply_plan_item_safe(item=item, pool=pool)
    assert out['status'] == 'failed'
    assert out['rollback_attempted'] is True
    assert out['rollback_succeeded'] is True
    assert out['partial_write_possible'] is False
    assert out['changed_files'] == []
    assert (Path(tmp_path) / 'a.txt').read_text(encoding='utf-8') == 'original\n'


def test_multi_file_rollback_delete_failure_reports_partial_write(tmp_path, monkeypatch):
    """When b.txt write fails and rollback unlink also fails, partial_write_possible=True."""
    pool = AtlasPlanPool(pool_id='p1', root_goal='g')
    item = AtlasPlanItem(item_id='i1', pool_id='p1', title='t', goal='g', item_type='implementation', risk_level='low', status='ready', metadata={
        'action_type': 'create',
        'file_changes': [
            {'path': 'a.txt', 'action_type': 'create', 'proposed_content': 'a\n'},
            {'path': 'b.txt', 'action_type': 'create', 'proposed_content': 'b\n'},
        ],
    })
    original_write_text = Path.write_text
    original_unlink = Path.unlink

    def fail_on_b_write(self, *args, **kwargs):
        if self.name == 'b.txt':
            raise OSError('disk full')
        return original_write_text(self, *args, **kwargs)

    def fail_unlink(self, *args, **kwargs):
        raise OSError('cannot delete')

    monkeypatch.setattr(Path, 'write_text', fail_on_b_write)
    monkeypatch.setattr(Path, 'unlink', fail_unlink)
    out = AtlasFileSafeApplyExecutor(workspace_root=tmp_path).apply_plan_item_safe(item=item, pool=pool)
    assert out['status'] == 'failed'
    assert out['rollback_attempted'] is True
    assert out['rollback_succeeded'] is False
    assert out['partial_write_possible'] is True
    assert 'a.txt' in out['unrestored_files']


def test_multi_file_rollback_restore_write_failure_reports_partial_write(tmp_path, monkeypatch):
    """When b.txt write fails and rollback write_text on updated a.txt also fails."""
    (Path(tmp_path) / 'a.txt').write_text('original\n', encoding='utf-8')
    pool = AtlasPlanPool(pool_id='p1', root_goal='g')
    item = AtlasPlanItem(item_id='i1', pool_id='p1', title='t', goal='g', item_type='implementation', risk_level='low', status='ready', metadata={
        'action_type': 'update',
        'file_changes': [
            {'path': 'a.txt', 'action_type': 'update', 'proposed_content': 'updated\n'},
            {'path': 'b.txt', 'action_type': 'create', 'proposed_content': 'b\n'},
        ],
    })
    call_count = {'n': 0}
    original_write_text = Path.write_text

    def selective_fail(self, content, *args, **kwargs):
        call_count['n'] += 1
        if self.name == 'b.txt':
            raise OSError('disk full')
        if self.name == 'a.txt' and call_count['n'] > 1:
            # Second write to a.txt (rollback restore) fails
            raise OSError('restore failed')
        return original_write_text(self, content, *args, **kwargs)

    monkeypatch.setattr(Path, 'write_text', selective_fail)
    out = AtlasFileSafeApplyExecutor(workspace_root=tmp_path).apply_plan_item_safe(item=item, pool=pool)
    assert out['status'] == 'failed'
    assert out['rollback_attempted'] is True
    assert out['rollback_succeeded'] is False
    assert out['partial_write_possible'] is True
    assert 'a.txt' in out['unrestored_files']


def test_multi_file_rollback_success_empty_changed_files(tmp_path, monkeypatch):
    """Successful rollback reports changed_files=[] and partial_write_possible=False."""
    pool = AtlasPlanPool(pool_id='p1', root_goal='g')
    item = AtlasPlanItem(item_id='i1', pool_id='p1', title='t', goal='g', item_type='implementation', risk_level='low', status='ready', metadata={
        'action_type': 'create',
        'file_changes': [
            {'path': 'x.txt', 'action_type': 'create', 'proposed_content': 'x\n'},
            {'path': 'y.txt', 'action_type': 'create', 'proposed_content': 'y\n'},
            {'path': 'z.txt', 'action_type': 'create', 'proposed_content': 'z\n'},
        ],
    })
    original_write_text = Path.write_text

    def fail_on_z(self, *args, **kwargs):
        if self.name == 'z.txt':
            raise OSError('disk full')
        return original_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, 'write_text', fail_on_z)
    out = AtlasFileSafeApplyExecutor(workspace_root=tmp_path).apply_plan_item_safe(item=item, pool=pool)
    assert out['status'] == 'failed'
    assert out['partial_write_possible'] is False
    assert out['changed_files'] == []
    assert out['rollback_succeeded'] is True
    assert not (Path(tmp_path) / 'x.txt').exists()
    assert not (Path(tmp_path) / 'y.txt').exists()


def test_single_file_write_failure_new_file_rollback_deletes(tmp_path, monkeypatch):
    """Single-file write failure on a NEW file: rollback deletes the partial file → not partial."""
    pool, item = _pool_and_item(tmp_path, action_type='create', target='new.txt', metadata={'proposed_content': 'abc\n'})
    original_write_text = Path.write_text

    def fail_write(self, *args, **kwargs):
        if self.name == 'new.txt':
            # Simulate a partial write then failure: create the file, then raise.
            original_write_text(self, 'partial', encoding='utf-8')
            raise OSError('disk full')
        return original_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, 'write_text', fail_write)
    out = AtlasFileSafeApplyExecutor(workspace_root=tmp_path).apply_plan_item_safe(item=item, pool=pool)
    assert out['status'] == 'failed'
    assert out['rollback_attempted'] is True
    assert out['rollback_succeeded'] is True
    assert out['partial_write_possible'] is False
    assert out['changed_files'] == []
    assert 'new.txt' in out['restored_files']
    assert not (Path(tmp_path) / 'new.txt').exists()


def test_single_file_write_failure_new_file_delete_failure_partial(tmp_path, monkeypatch):
    """New-file write failure where rollback unlink also fails → partial_write_possible=True."""
    pool, item = _pool_and_item(tmp_path, action_type='create', target='new.txt', metadata={'proposed_content': 'abc\n'})
    original_write_text = Path.write_text

    def fail_write(self, *args, **kwargs):
        if self.name == 'new.txt':
            original_write_text(self, 'partial', encoding='utf-8')
            raise OSError('disk full')
        return original_write_text(self, *args, **kwargs)

    def fail_unlink(self, *args, **kwargs):
        raise OSError('cannot delete')

    monkeypatch.setattr(Path, 'write_text', fail_write)
    monkeypatch.setattr(Path, 'unlink', fail_unlink)
    out = AtlasFileSafeApplyExecutor(workspace_root=tmp_path).apply_plan_item_safe(item=item, pool=pool)
    assert out['status'] == 'failed'
    assert out['rollback_succeeded'] is False
    assert out['partial_write_possible'] is True
    assert 'new.txt' in out['unrestored_files']
    assert out['changed_files'] == ['new.txt']


def test_single_file_write_failure_existing_file_rollback_restores(tmp_path, monkeypatch):
    """Single-file write failure on an EXISTING file: rollback restores original → not partial."""
    f = Path(tmp_path) / 'doc.txt'; f.write_text('original\n', encoding='utf-8')
    pool, item = _pool_and_item(tmp_path, target='doc.txt', metadata={'proposed_content': 'new\n'})
    original_write_text = Path.write_text
    call_count = {'n': 0}

    def fail_then_restore(self, content, *args, **kwargs):
        if self.name == 'doc.txt':
            call_count['n'] += 1
            if call_count['n'] == 1:
                # First write (the apply) corrupts then fails
                original_write_text(self, 'corrupt', encoding='utf-8')
                raise OSError('disk full')
        return original_write_text(self, content, *args, **kwargs)

    monkeypatch.setattr(Path, 'write_text', fail_then_restore)
    out = AtlasFileSafeApplyExecutor(workspace_root=tmp_path).apply_plan_item_safe(item=item, pool=pool)
    assert out['status'] == 'failed'
    assert out['rollback_succeeded'] is True
    assert out['partial_write_possible'] is False
    assert out['changed_files'] == []
    assert f.read_text(encoding='utf-8') == 'original\n'


def test_single_file_write_failure_existing_file_restore_failure_partial(tmp_path, monkeypatch):
    """Existing-file write failure where rollback restore also fails → partial_write_possible=True."""
    f = Path(tmp_path) / 'doc.txt'; f.write_text('original\n', encoding='utf-8')
    pool, item = _pool_and_item(tmp_path, target='doc.txt', metadata={'proposed_content': 'new\n'})
    original_write_text = Path.write_text

    def always_fail_doc(self, *args, **kwargs):
        if self.name == 'doc.txt':
            raise OSError('disk full')
        return original_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, 'write_text', always_fail_doc)
    out = AtlasFileSafeApplyExecutor(workspace_root=tmp_path).apply_plan_item_safe(item=item, pool=pool)
    assert out['status'] == 'failed'
    assert out['rollback_succeeded'] is False
    assert out['partial_write_possible'] is True
    assert 'doc.txt' in out['unrestored_files']
    assert out['changed_files'] == ['doc.txt']


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
