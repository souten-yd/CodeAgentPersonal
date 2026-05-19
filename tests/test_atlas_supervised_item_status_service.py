from pathlib import Path
from agent.atlas_plan_pool_schema import AtlasPlanPool, AtlasPlanItem
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_supervised_item_status_schema import AtlasSupervisedItemStatusFinalizeRequest
from agent.atlas_supervised_item_status_service import AtlasSupervisedItemStatusService


def make_env(tmp_path):
    storage = AtlasPlanPoolStorage(tmp_path)
    pool = AtlasPlanPool(pool_id='p1', root_goal='g', items=[AtlasPlanItem(item_id='i1', pool_id='p1', title='t', goal='g')])
    storage.save_pool(pool)
    return storage


def test_completed_from_passed_verification_and_evaluator_continue(tmp_path):
    st = make_env(tmp_path); p=st.load_pool('p1'); i=p.get_item('i1'); i.metadata['supervised_handoff_verification_results']=[{'status':'passed','verification_status':'passed','evaluator_decision':'continue'}]; st.save_pool(p)
    res = AtlasSupervisedItemStatusService(storage=st).finalize(AtlasSupervisedItemStatusFinalizeRequest(pool_id='p1', item_id='i1'))
    assert res.supervised_status_after == 'completed' and res.next_action == 'none'

def test_dry_run_does_not_update_item(tmp_path):
    st = make_env(tmp_path)
    req=AtlasSupervisedItemStatusFinalizeRequest(pool_id='p1', item_id='i1', dry_run=True)
    res=AtlasSupervisedItemStatusService(storage=st).finalize(req)
    assert res.status == 'dry_run'
