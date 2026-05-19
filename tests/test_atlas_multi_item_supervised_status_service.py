from agent.atlas_multi_item_supervised_status_schema import AtlasMultiItemSupervisedStatusRequest
from agent.atlas_multi_item_supervised_status_service import AtlasMultiItemSupervisedStatusService
from agent.atlas_plan_pool_schema import AtlasPlanPool, AtlasPlanItem

class DummyStorage:
    def __init__(self, pool): self.pool=pool
    def load_pool(self, _): return self.pool
class DummyJournal:
    def append_event(self, *a, **k): return None
class DummyFinalize:
    def finalize(self, req):
        class T: to_status='patch_candidate_ready'; evidence_type='patch_candidate'; evidence_run_id='r1'
        class R: transition=T(); next_action='approve_patch_candidate'; next_action_payload={'regen_run_id':'x','proposal_id':'y'}
        return R()

def test_build_status_queue_refreshes_item_statuses():
    pool=AtlasPlanPool(pool_id='p1', root_goal='g', items=[AtlasPlanItem(pool_id='p1', item_id='i1', title='t', goal='g')])
    svc=AtlasMultiItemSupervisedStatusService(storage=DummyStorage(pool), journal=DummyJournal(), supervised_item_status_service=DummyFinalize())
    res=svc.build_status(AtlasMultiItemSupervisedStatusRequest(pool_id='p1', run_id='r1'))
    assert res.item_summaries
    assert res.next_item is not None
    assert res.next_item.next_action == 'approve_patch_candidate'
