from agent.atlas_multi_item_supervised_status_schema import AtlasMultiItemSupervisedStatusRequest
from agent.atlas_multi_item_supervised_status_service import AtlasMultiItemSupervisedStatusService
from agent.atlas_plan_pool_schema import AtlasPlanPool, AtlasPlanItem


class DummyStorage:
    def __init__(self, pool): self.pool = pool
    def load_pool(self, _): return self.pool


class RecordingJournal:
    def __init__(self): self.events = []
    def append_event(self, *a, **k): self.events.append((a, k))


class DummyFinalize:
    def __init__(self, action='approve_patch_candidate', payload=None):
        self.action = action
        self.payload = payload if payload is not None else {'regen_run_id': 'x', 'proposal_id': 'y'}
    def finalize(self, req):
        class T: to_status='patch_candidate_ready'; evidence_type='patch_candidate'; evidence_run_id='r1'
        class R: pass
        r=R(); r.transition=T(); r.next_action=self.action; r.next_action_payload=self.payload
        return r


def mk_pool(item_ids=('i1',)):
    return AtlasPlanPool(pool_id='p1', root_goal='g', items=[AtlasPlanItem(pool_id='p1', item_id=i, title=i, goal='g') for i in item_ids])


def build(action, payload):
    journal = RecordingJournal()
    svc = AtlasMultiItemSupervisedStatusService(storage=DummyStorage(mk_pool()), journal=journal, supervised_item_status_service=DummyFinalize(action=action, payload=payload))
    return svc.build_status(AtlasMultiItemSupervisedStatusRequest(pool_id='p1', run_id='r1')), journal


def test_payload_validation_safe_apply_requires_handoff_id():
    res, _ = build('run_supervised_safe_apply', {})
    assert res.item_summaries[0].selectable is False
    assert res.item_summaries[0].blocked_reason == 'missing_safe_apply_handoff_id'


def test_payload_validation_verification_requires_safe_apply_execution_id():
    res, _ = build('run_supervised_verification', {'handoff_id': 'h1'})
    s = res.item_summaries[0]
    assert s.selectable is False
    assert s.blocked_reason == 'missing_safe_apply_execution_id'


def test_payload_validation_retry_requires_verification_and_safe_apply_ids():
    res, _ = build('run_supervised_retry', {'verification_run_id': 'v1'})
    assert res.item_summaries[0].blocked_reason == 'missing_retry_payload'


def test_payload_validation_regen_recommendation_requires_recommendation_run_id():
    res, _ = build('run_patch_regen_from_recommendation', {})
    assert res.item_summaries[0].blocked_reason == 'missing_recommendation_run_id'


def test_unselectable_items_excluded_from_next_item():
    pool = mk_pool(('i1', 'i2'))
    journal = RecordingJournal()
    class MixedFinalize:
        def finalize(self, req):
            class T: to_status='patch_candidate_ready'; evidence_type='x'; evidence_run_id='r'
            class R: pass
            r=R(); r.transition=T()
            if req.item_id == 'i1':
                r.next_action='run_supervised_safe_apply'; r.next_action_payload={}
            else:
                r.next_action='manual_review'; r.next_action_payload={}
            return r
    svc = AtlasMultiItemSupervisedStatusService(storage=DummyStorage(pool), journal=journal, supervised_item_status_service=MixedFinalize())
    res = svc.build_status(AtlasMultiItemSupervisedStatusRequest(pool_id='p1', run_id='r1'))
    assert res.next_item.item_id == 'i2'


def test_empty_pool_blocks():
    pool = AtlasPlanPool(pool_id='p1', root_goal='g', items=[])
    svc = AtlasMultiItemSupervisedStatusService(storage=DummyStorage(pool), journal=RecordingJournal(), supervised_item_status_service=DummyFinalize())
    res = svc.build_status(AtlasMultiItemSupervisedStatusRequest(pool_id='p1', run_id='r1'))
    assert res.status == 'blocked'
    assert 'no_items_selected' in res.warnings


def test_all_requested_items_missing_blocks():
    svc = AtlasMultiItemSupervisedStatusService(storage=DummyStorage(mk_pool(('i1',))), journal=RecordingJournal(), supervised_item_status_service=DummyFinalize())
    res = svc.build_status(AtlasMultiItemSupervisedStatusRequest(pool_id='p1', run_id='r1', item_ids=['x1']))
    assert res.status == 'blocked'
    assert 'all_requested_items_missing' in res.warnings


def test_items_selected_event_emitted():
    res, journal = build('approve_patch_candidate', {'regen_run_id': 'x', 'proposal_id': 'y'})
    events = [a[2]['event_type'] for a, _ in journal.events]
    assert 'multi_item_supervised_status_items_selected' in events


def test_ranked_ready_blocked_events_emitted():
    _, journal_ready = build('manual_review', {})
    events_ready = [a[2]['event_type'] for a, _ in journal_ready.events]
    assert 'multi_item_supervised_status_ranked' in events_ready
    assert 'multi_item_supervised_status_ready' in events_ready

    _, journal_blocked = build('run_supervised_safe_apply', {})
    events_blocked = [a[2]['event_type'] for a, _ in journal_blocked.events]
    assert 'multi_item_supervised_status_blocked' in events_blocked


def test_result_metadata_contains_queue_summary_and_payload_validation():
    res, _ = build('run_supervised_safe_apply', {})
    md = res.metadata
    assert md['queue_only'] is True and md['supervised_status_integrated'] is True
    assert 'payload_validation_summary' in md
    assert md['side_effects']['next_action_executed'] is False


def test_markdown_contains_counts_action_queue_payload_validation_safety():
    res, _ = build('manual_review', {})
    from pathlib import Path
    p = Path('ca_data/atlas/multi_item_supervised_status/p1') / f"{res.multi_status_run_id}.md"
    t = p.read_text(encoding='utf-8')
    assert '## Counts' in t and '## Action Queue' in t and '## Payload Validation' in t and '## Safety' in t


def test_no_side_effect_services_called():
    res, _ = build('manual_review', {})
    assert res.metadata['next_action_executed'] is False
    assert res.metadata['safe_apply_executed'] is False
