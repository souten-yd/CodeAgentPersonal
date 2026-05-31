from pathlib import Path
from types import SimpleNamespace

import pytest

from agent.atlas_journal import AtlasJournal
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_safe_apply_execution_schema import AtlasSafeApplyExecutionRequest
from agent.atlas_safe_apply_execution_service import AtlasSafeApplyExecutionService


class _Adapter:
    implementation_executor = object()

    def __init__(self, result):
        self.result = result

    def evaluate_safe_apply(self, item, pool, **kwargs):
        return SimpleNamespace(decision='allow')

    def apply_low_risk_item(self, item, pool, request):
        return self.result


def _service(tmp_path, result, pool):
    storage = AtlasPlanPoolStorage(tmp_path)
    journal = AtlasJournal(tmp_path)
    storage.save_pool(pool)
    journal.save_plan_pool(pool)
    return AtlasSafeApplyExecutionService(journal=journal, storage=storage, safe_apply_adapter=_Adapter(result), workspace_root=tmp_path), storage


def _pool_with_item(metadata=None, target_files=None):
    item = AtlasPlanItem(
        item_id='i1',
        pool_id='p1',
        title='t',
        goal='g',
        item_type='implementation',
        risk_level='low',
        status='ready',
        target_files=['a.txt'] if target_files is None else target_files,
        metadata={'action_type': 'create', 'approval': {'decision': 'approved'}, **(metadata or {})},
    )
    return AtlasPlanPool(pool_id='p1', root_goal='g', project_path='.', items=[item])


@pytest.mark.parametrize(
    ('adapter_result', 'expected_status', 'expected_changed'),
    [
        ({'status': 'applied', 'actual_file_changed': True, 'changed_files': ['a.txt'], 'file_results': [{'path': 'a.txt', 'status': 'applied'}]}, 'applied', ['a.txt']),
        ({'status': 'blocked', 'reasons': ['content_missing'], 'actual_file_changed': False, 'changed_files': [], 'file_results': [{'path': 'a.txt', 'status': 'blocked', 'reason': 'content_missing'}]}, 'blocked', []),
        ({'status': 'failed', 'reasons': ['write_failed'], 'actual_file_changed': False, 'changed_files': [], 'file_results': [{'path': 'a.txt', 'status': 'failed', 'reason': 'write_failed'}]}, 'failed', []),
    ],
)
def test_safe_apply_metadata_persisted_for_applied_blocked_failed(tmp_path, adapter_result, expected_status, expected_changed):
    pool = _pool_with_item()
    svc, storage = _service(tmp_path, adapter_result, pool)
    result = svc.execute_item(AtlasSafeApplyExecutionRequest(pool_id='p1', item_id='i1', run_id='r1'))
    assert result.status == expected_status
    item = storage.load_pool('p1').get_item('i1')
    safe = item.metadata['safe_apply']
    assert safe['status'] == expected_status
    assert safe['changed_files'] == expected_changed
    assert safe['file_results']
    if expected_status != 'applied':
        assert safe['actual_file_changed'] is False


def test_write_time_failure_metadata_preserves_partial_write_changed_files(tmp_path):
    adapter_result = {
        'status': 'failed',
        'reasons': ['write_failed'],
        'actual_file_changed': True,
        'changed_files': ['a.txt'],
        'partial_write_possible': True,
        'file_results': [
            {'path': 'a.txt', 'status': 'applied'},
            {'path': 'b.txt', 'status': 'failed', 'reason': 'write_failed'},
        ],
    }
    pool = _pool_with_item(target_files=['a.txt', 'b.txt'])
    svc, storage = _service(tmp_path, adapter_result, pool)

    result = svc.execute_item(AtlasSafeApplyExecutionRequest(pool_id='p1', item_id='i1', run_id='r1'))

    assert result.status == 'failed'
    item = storage.load_pool('p1').get_item('i1')
    safe = item.metadata['safe_apply']
    assert safe['status'] == 'failed'
    assert safe['partial_write_possible'] is True
    assert safe['actual_file_changed'] is True
    assert safe['changed_files'] == ['a.txt']
    assert safe['file_results'] == adapter_result['file_results']


def test_rollback_fields_persisted_in_safe_apply_metadata(tmp_path):
    adapter_result = {
        'status': 'failed',
        'reasons': ['write_failed'],
        'actual_file_changed': False,
        'changed_files': [],
        'partial_write_possible': False,
        'rollback_attempted': True,
        'rollback_succeeded': True,
        'restored_files': ['a.txt'],
        'unrestored_files': [],
        'file_results': [
            {'path': 'a.txt', 'status': 'failed', 'reason': 'write_failed'},
        ],
    }
    pool = _pool_with_item()
    svc, storage = _service(tmp_path, adapter_result, pool)
    result = svc.execute_item(AtlasSafeApplyExecutionRequest(pool_id='p1', item_id='i1', run_id='r1'))
    assert result.status == 'failed'
    item = storage.load_pool('p1').get_item('i1')
    safe = item.metadata['safe_apply']
    assert safe['rollback_attempted'] is True
    assert safe['rollback_succeeded'] is True
    assert safe['restored_files'] == ['a.txt']
    assert safe['unrestored_files'] == []
    assert safe['partial_write_possible'] is False


def test_rollback_failure_fields_persisted_in_safe_apply_metadata(tmp_path):
    adapter_result = {
        'status': 'failed',
        'reasons': ['write_failed'],
        'actual_file_changed': True,
        'changed_files': ['a.txt'],
        'partial_write_possible': True,
        'rollback_attempted': True,
        'rollback_succeeded': False,
        'restored_files': [],
        'unrestored_files': ['a.txt'],
        'file_results': [
            {'path': 'a.txt', 'status': 'failed', 'reason': 'write_failed'},
        ],
    }
    pool = _pool_with_item()
    svc, storage = _service(tmp_path, adapter_result, pool)
    svc.execute_item(AtlasSafeApplyExecutionRequest(pool_id='p1', item_id='i1', run_id='r1'))
    item = storage.load_pool('p1').get_item('i1')
    safe = item.metadata['safe_apply']
    assert safe['rollback_attempted'] is True
    assert safe['rollback_succeeded'] is False
    assert safe['unrestored_files'] == ['a.txt']
    assert safe['partial_write_possible'] is True


def test_file_changes_are_normalized_and_saved_before_snapshot(tmp_path):
    pool = _pool_with_item(target_files=[], metadata={
        'file_changes': [
            {'path': 'index.html', 'action_type': 'create', 'proposed_content': '<!doctype html>\n'},
            {'path': 'style.css', 'action_type': 'create', 'proposed_content': 'body{}\n'},
        ],
    })
    svc, storage = _service(tmp_path, {'status': 'blocked', 'reasons': ['stop'], 'file_results': [{'path': 'index.html', 'status': 'blocked'}]}, pool)
    svc.execute_item(AtlasSafeApplyExecutionRequest(pool_id='p1', item_id='i1', run_id='r1'))
    item = storage.load_pool('p1').get_item('i1')
    assert item.target_files == ['index.html', 'style.css']
    safe = item.metadata['safe_apply']
    assert safe['change_snapshot_id']
    assert Path(safe['change_snapshot_manifest_path']).exists()
