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


def _finalize(st, **kwargs):
    return AtlasSupervisedItemStatusService(storage=st).finalize(AtlasSupervisedItemStatusFinalizeRequest(pool_id='p1', item_id='i1', **kwargs))


def test_source_run_id_priority_for_supervised_verification(tmp_path):
    st=make_env(tmp_path); p=st.load_pool('p1'); i=p.get_item('i1'); i.metadata['supervised_handoff_verification_results']=[{'verification_run_id':'old','status':'blocked'},{'verification_run_id':'new','status':'passed','verification_status':'passed','evaluator_decision':'continue'}]; st.save_pool(p)
    res=_finalize(st, source_type='supervised_verification', source_run_id='old')
    assert res.transition.to_status=='blocked' and res.transition.evidence_run_id=='old'

def test_source_not_found_blocks_and_saves_result(tmp_path):
    st=make_env(tmp_path)
    res=_finalize(st, source_type='supervised_verification', source_run_id='none')
    assert res.transition.to_status=='blocked' and res.transition.reason=='source_evidence_not_found'
    assert Path('ca_data/atlas/supervised_item_status/p1').exists()

def test_latest_selection_uses_created_at(tmp_path):
    st=make_env(tmp_path); p=st.load_pool('p1'); i=p.get_item('i1'); i.metadata['patch_regen_candidates']=[{'regen_run_id':'newer','created_at':'2026-01-01T00:00:00+00:00'},{'regen_run_id':'older','created_at':'2025-01-01T00:00:00+00:00'}]; st.save_pool(p)
    res=_finalize(st)
    assert res.evidence_index['latest_patch_candidate']['regen_run_id']=='newer'

def test_next_action_payload_for_verification(tmp_path):
    st=make_env(tmp_path); p=st.load_pool('p1'); i=p.get_item('i1'); i.metadata['supervised_handoff_safe_apply_results']=[{'status':'applied','execution_id':'e1','handoff_id':'h1'}]; st.save_pool(p)
    res=_finalize(st)
    assert res.next_action=='run_supervised_verification' and res.next_action_payload['safe_apply_execution_id']=='e1'

def test_next_action_payload_for_safe_apply(tmp_path):
    st=make_env(tmp_path); p=st.load_pool('p1'); i=p.get_item('i1'); i.metadata['safe_apply_handoffs']=[{'safe_apply_ready':'true','handoff_id':'h2'}]; st.save_pool(p)
    res=_finalize(st)
    assert res.next_action=='run_supervised_safe_apply' and res.next_action_payload['handoff_id']=='h2'

def test_next_action_payload_for_patch_candidate_approval(tmp_path):
    st=make_env(tmp_path); p=st.load_pool('p1'); i=p.get_item('i1'); i.metadata['patch_regen_candidates']=[{'status':'proposal_ready','approval_status':'pending','regen_run_id':'r1','proposal_id':'p9'}]; st.save_pool(p)
    res=_finalize(st)
    assert res.next_action_payload['regen_run_id']=='r1' and res.next_action_payload['proposal_id']=='p9'

def test_patch_regen_from_recommendation_created_becomes_patch_candidate_ready(tmp_path):
    st=make_env(tmp_path); p=st.load_pool('p1'); p.get_item('i1').metadata['patch_regen_from_recommendation_results']=[{'status':'patch_regen_created','patch_regen_status':'proposal_ready','approval_status':'pending','safe_apply_ready':False,'patch_regen_result_id':'x1'}]; st.save_pool(p)
    res=_finalize(st)
    assert res.transition.to_status=='patch_candidate_ready'

def test_patch_regen_from_recommendation_manual_required(tmp_path):
    st=make_env(tmp_path); p=st.load_pool('p1'); p.get_item('i1').metadata['patch_regen_from_recommendation_results']=[{'status':'manual_required'}]; st.save_pool(p)
    assert _finalize(st).transition.to_status=='manual_required'

def test_retry_exhausted_with_recommendation_ready_becomes_patch_regen_recommended(tmp_path):
    st=make_env(tmp_path); p=st.load_pool('p1'); it=p.get_item('i1'); it.metadata['supervised_handoff_retry_results']=[{'status':'exhausted'}]; it.metadata['patch_regen_recommendations']=[{'status':'recommendation_ready'}]; st.save_pool(p)
    assert _finalize(st).transition.to_status=='patch_regen_recommended'

def test_retry_exhausted_without_recommendation_becomes_needs_revision(tmp_path):
    st=make_env(tmp_path); p=st.load_pool('p1'); it=p.get_item('i1'); it.metadata['supervised_handoff_retry_results']=[{'status':'exhausted'}]; it.metadata['patch_regen_recommendations']=[{'status':'not_recommended'}]; st.save_pool(p)
    assert _finalize(st).transition.to_status=='needs_revision'

def test_evaluator_manual_required_becomes_manual_required(tmp_path):
    st=make_env(tmp_path); p=st.load_pool('p1'); p.get_item('i1').metadata['supervised_handoff_verification_results']=[{'evaluator_decision':'manual_required','verification_run_id':'v1'}]; st.save_pool(p)
    assert _finalize(st).transition.to_status=='manual_required'

def test_old_blocked_does_not_override_new_passed(tmp_path):
    st=make_env(tmp_path); p=st.load_pool('p1'); p.get_item('i1').metadata['supervised_handoff_verification_results']=[{'status':'blocked','created_at':'2025-01-01T00:00:00+00:00'},{'status':'passed','verification_status':'passed','evaluator_decision':'continue','verification_run_id':'v2','created_at':'2026-01-01T00:00:00+00:00'}]; st.save_pool(p)
    assert _finalize(st).transition.to_status=='completed'

def test_item_not_found_saves_blocked_result(tmp_path):
    st=make_env(tmp_path)
    res=AtlasSupervisedItemStatusService(storage=st).finalize(AtlasSupervisedItemStatusFinalizeRequest(pool_id='p1', item_id='missing'))
    assert res.status=='blocked'

def test_audit_events_recorded(tmp_path):
    st=make_env(tmp_path); _finalize(st)
    j = Path('ca_data') / 'atlas' / 'workspaces' / 'default' / 'plan_pools' / 'p1'
    assert j.exists()

def test_markdown_contains_transition_evidence_next_action_payload(tmp_path):
    st=make_env(tmp_path); res=_finalize(st)
    md=(Path('ca_data')/'atlas'/'supervised_item_status'/'p1'/f"{res.finalize_run_id}.md").read_text(encoding='utf-8')
    assert '## Transition' in md and '## Evidence' in md and '## Next Action Payload' in md

def test_no_side_effect_services_called(tmp_path):
    st=make_env(tmp_path); res=_finalize(st)
    assert res.metadata['side_effects']['safe_apply_executed'] is False and res.metadata['side_effects']['verification_executed'] is False
