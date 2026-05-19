from agent.atlas_multi_item_supervised_status_schema import AtlasMultiItemSupervisedStatusRequest
from agent.atlas_multi_item_supervised_status_service import AtlasMultiItemSupervisedStatusService
from agent.atlas_next_action_orchestrator_schema import AtlasNextActionOrchestratorRequest
from agent.atlas_next_action_orchestrator_service import AtlasNextActionOrchestratorService
from tests.test_atlas_multi_item_supervised_status_service import DummyFinalize, DummyStorage, RecordingJournal, mk_pool

def _build_orchestrator(action='approve_patch_candidate', payload=None):
    journal=RecordingJournal(); ms=AtlasMultiItemSupervisedStatusService(storage=DummyStorage(mk_pool()), journal=journal, supervised_item_status_service=DummyFinalize(action=action,payload=payload))
    svc=AtlasNextActionOrchestratorService(storage=DummyStorage(mk_pool()), journal=journal, supervised_status_service=ms)
    return svc

def test_prepare_uses_latest_multi_status_queue():
    svc=_build_orchestrator(); out=svc.prepare(AtlasNextActionOrchestratorRequest(pool_id='p1', run_id='r1'))
    assert out.action_contract is not None
    assert out.action_contract.execution_allowed is False

def test_manual_review_is_manual_display_not_execution_candidate():
    svc=_build_orchestrator(action='manual_review', payload={}); out=svc.prepare(AtlasNextActionOrchestratorRequest(pool_id='p1', run_id='r1'))
    assert out.action_contract.action_kind=='manual_display'
    assert out.action_contract.target_api_path==''
