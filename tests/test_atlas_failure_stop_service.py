from types import SimpleNamespace

from agent.atlas_failure_stop_service import AtlasFailureStopService


class _Journal:
    def __init__(self): self.events=[]
    def append_event(self, pool_id, run_id, payload): self.events.append(payload)


def test_failure_stop_suggests_manual_restore_after_verification_failed():
    journal = _Journal()
    pool = SimpleNamespace(pool_id='p1')
    item = SimpleNamespace(item_id='i1', metadata={'auto_safe_apply': {'status': 'applied', 'change_snapshot': {'manifest_path': '/tmp/m.json', 'changed_files': ['app.py']}}})
    out = AtlasFailureStopService(journal=journal).build_for_verification_failure(pool, item, 'r1', {'status': 'failed'})
    assert out.status == 'stopped'
    assert out.restore_candidate
    assert out.snapshot_manifest_path
    assert any('Restore from Change Snapshot manually' in x for x in out.suggested_manual_actions)


def test_failure_stop_does_not_restore_or_debug_or_patch():
    journal = _Journal()
    pool = SimpleNamespace(pool_id='p1')
    item = SimpleNamespace(item_id='i1', metadata={'auto_safe_apply': {'status': 'applied', 'change_snapshot': {'manifest_path': '/tmp/m.json'}}})
    AtlasFailureStopService(journal=journal).build_for_verification_failure(pool, item, 'r1', {'status': 'failed'})
    text = '\n'.join(str(e) for e in journal.events)
    for forbidden in ['change_snapshot_restore_manual_started','change_snapshot_restore_auto_started','auto_rollback_started','debug_review_auto_started','patch_proposal_auto_started']:
        assert forbidden not in text
