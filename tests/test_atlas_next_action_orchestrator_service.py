from pathlib import Path
from agent.atlas_next_action_orchestrator_schema import AtlasNextActionOrchestratorRequest
from agent.atlas_next_action_orchestrator_service import AtlasNextActionOrchestratorService
from tests.test_atlas_multi_item_supervised_status_service import DummyFinalize, DummyStorage, RecordingJournal, mk_pool
from agent.atlas_multi_item_supervised_status_service import AtlasMultiItemSupervisedStatusService


def _build_orchestrator(action='approve_patch_candidate', payload=None):
    journal = RecordingJournal()
    ms = AtlasMultiItemSupervisedStatusService(storage=DummyStorage(mk_pool()), journal=journal, supervised_item_status_service=DummyFinalize(action=action, payload=payload))
    svc = AtlasNextActionOrchestratorService(storage=DummyStorage(mk_pool()), journal=journal, supervised_status_service=ms)
    return svc, journal


def _run(**kwargs):
    svc, journal = _build_orchestrator(kwargs.pop('action', 'approve_patch_candidate'), kwargs.pop('payload', None))
    return svc.prepare(AtlasNextActionOrchestratorRequest(pool_id='p1', run_id='r1', refresh_queue=True, **kwargs)), journal


def test_unselectable_item_blocks_even_with_valid_payload(monkeypatch):
    svc, _ = _build_orchestrator()
    monkeypatch.setattr(svc, 'select_action_item', lambda q, r: ({'item_id':'i1','next_action':'approve_patch_candidate','next_action_payload':{'regen_run_id':'x','proposal_id':'y'},'selectable':False,'supervised_status':'in_progress'}, None))
    out = svc.prepare(AtlasNextActionOrchestratorRequest(pool_id='p1', run_id='r1', refresh_queue=True))
    assert out.status == 'blocked'


def test_completed_item_no_action(monkeypatch):
    svc, _ = _build_orchestrator()
    monkeypatch.setattr(svc, 'select_action_item', lambda q, r: ({'item_id':'i1','next_action':'approve_patch_candidate','next_action_payload':{'regen_run_id':'x','proposal_id':'y'},'selectable':True,'supervised_status':'completed'}, None))
    out = svc.prepare(AtlasNextActionOrchestratorRequest(pool_id='p1', run_id='r1', refresh_queue=True))
    assert out.status == 'blocked'


def test_failed_internal_item_blocks(monkeypatch):
    svc, _ = _build_orchestrator()
    monkeypatch.setattr(svc, 'select_action_item', lambda q, r: ({'item_id':'i1','next_action':'approve_patch_candidate','next_action_payload':{'regen_run_id':'x','proposal_id':'y'},'selectable':True,'supervised_status':'failed_internal'}, None))
    out = svc.prepare(AtlasNextActionOrchestratorRequest(pool_id='p1', run_id='r1', refresh_queue=True))
    assert out.status == 'blocked'


def test_contract_errors_force_blocked(monkeypatch):
    svc, _ = _build_orchestrator()
    monkeypatch.setattr(svc, 'select_action_item', lambda q, r: ({'item_id':'i1','next_action':'run_supervised_verification','next_action_payload':{},'selectable':True,'supervised_status':'in_progress'}, None))
    out = svc.prepare(AtlasNextActionOrchestratorRequest(pool_id='p1', run_id='r1', refresh_queue=True))
    assert out.status == 'blocked'


def test_queue_next_action_executed_blocks(monkeypatch):
    svc, _ = _build_orchestrator()
    original = svc.load_or_build_multi_status_queue
    def wrapped(request):
        q, m, w, e = original(request)
        q.metadata['next_action_executed'] = True
        return q, m, w, e
    monkeypatch.setattr(svc, 'load_or_build_multi_status_queue', wrapped)
    out = svc.prepare(AtlasNextActionOrchestratorRequest(pool_id='p1', run_id='r1'))
    assert out.status == 'blocked'


def test_queue_side_effect_true_blocks(monkeypatch):
    svc, _ = _build_orchestrator()
    original = svc.load_or_build_multi_status_queue
    def wrapped(request):
        q, m, w, e = original(request)
        q.metadata['side_effects']['safe_apply_executed'] = True
        return q, m, w, e
    monkeypatch.setattr(svc, 'load_or_build_multi_status_queue', wrapped)
    out = svc.prepare(AtlasNextActionOrchestratorRequest(pool_id='p1', run_id='r1'))
    assert out.status == 'blocked'


def test_queue_not_integrated_blocks(monkeypatch):
    svc, _ = _build_orchestrator()
    original = svc.load_or_build_multi_status_queue
    def wrapped(request):
        q, m, w, e = original(request)
        q.metadata['supervised_status_integrated'] = False
        return q, m, w, e
    monkeypatch.setattr(svc, 'load_or_build_multi_status_queue', wrapped)
    out = svc.prepare(AtlasNextActionOrchestratorRequest(pool_id='p1', run_id='r1'))
    assert out.status == 'blocked'


def test_requested_action_mismatch_blocks():
    out, _ = _run(requested_next_action='run_supervised_safe_apply', item_id='i1')
    assert out.status == 'blocked'


def test_queue_loaded_event_emitted():
    _, journal = _run()
    events = [a[2]['event_type'] for a, _ in journal.events]
    assert 'next_action_orchestrator_queue_loaded' in events


def test_action_ready_event_emitted(monkeypatch):
    svc, journal = _build_orchestrator()
    monkeypatch.setattr(svc, 'select_action_item', lambda q, r: ({'item_id':'i1','next_action':'approve_patch_candidate','next_action_payload':{'regen_run_id':'x','proposal_id':'y'},'selectable':True,'supervised_status':'in_progress'}, None))
    svc.prepare(AtlasNextActionOrchestratorRequest(pool_id='p1', run_id='r1', refresh_queue=True))
    events = [a[2]['event_type'] for a, _ in journal.events]
    assert 'next_action_orchestrator_action_ready' in events


def test_manual_display_event_emitted():
    out, journal = _run(action='manual_review', payload={})
    assert out.status == 'manual_display'
    events = [a[2]['event_type'] for a, _ in journal.events]
    assert 'next_action_orchestrator_manual_display' in events


def test_failed_internal_result_saved_on_exception(monkeypatch):
    svc, _ = _build_orchestrator()
    monkeypatch.setattr(svc, 'map_next_action_to_contract', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('x')))
    out = svc.prepare(AtlasNextActionOrchestratorRequest(pool_id='p1', run_id='r1'))
    assert out.status == 'failed_internal'
    assert Path(f"ca_data/atlas/next_action_orchestrator/p1/{out.orchestrator_run_id}.json").exists()


def test_markdown_contains_action_contract_payload_preview_queue_summary():
    out, _ = _run(action='manual_review', payload={})
    t = Path(f"ca_data/atlas/next_action_orchestrator/p1/{out.orchestrator_run_id}.md").read_text(encoding='utf-8')
    assert '## Action Contract' in t and '## Payload Preview' in t and '## Queue Summary' in t


def test_metadata_contains_contract_validation_and_queue_safety():
    out, _ = _run(action='manual_review', payload={})
    assert 'contract_validation' in out.metadata
    assert out.metadata['queue_safety_checked'] is True


def test_no_side_effect_services_called():
    out, _ = _run(action='manual_review', payload={})
    se = out.metadata['side_effects']
    assert se['next_action_executed'] is False and se['safe_apply_executed'] is False
