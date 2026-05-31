from types import SimpleNamespace

from agent.atlas_journal import AtlasJournal
from agent.atlas_patch_proposal_planitem_service import AtlasPatchProposalPlanItemDraftService
from agent.atlas_patch_proposal_service import AtlasPatchProposalService
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_planner_bridge import AtlasPlannerBridge
from agent.atlas_planner_bridge_schema import AtlasPlannerBridgeRequest


def test_planner_bridge_carries_file_changes_into_plan_payload(tmp_path):
    bridge = AtlasPlannerBridge(ca_data_dir=str(tmp_path))
    planner_result = {
        'status': 'planned',
        'plan': {
            'implementation_steps': [{
                'step_id': 'step_1',
                'title': 'Create app',
                'action_type': 'create',
                'risk_level': 'low',
                'target_files': ['index.html'],
                'file_changes': [
                    {'path': 'index.html', 'action_type': 'create', 'proposed_content': '<!doctype html>\n'},
                    {'path': 'style.css', 'action_type': 'create', 'proposed_content': 'body{}\n'},
                ],
            }]
        },
    }
    pool = bridge.build_pool_from_planner_result(AtlasPlannerBridgeRequest(input='make app'), planner_result)
    item = pool.items[0]
    assert item.metadata['file_changes'][1]['path'] == 'style.css'
    assert item.target_files == ['index.html', 'style.css']


def test_patch_proposal_build_output_carries_file_changes(tmp_path):
    svc = AtlasPatchProposalService(journal=AtlasJournal(tmp_path), storage=AtlasPlanPoolStorage(tmp_path))
    file_changes = [
        {'path': 'index.html', 'action_type': 'create', 'proposed_content': '<!doctype html>\n'},
        {'path': 'style.css', 'action_type': 'create', 'proposed_content': 'body{}\n'},
    ]
    proposal, has_content = svc._build_proposal_from_output(
        {'summary': 'multi', 'file_changes': file_changes, 'risk_level': 'low'},
        {'pool_id': 'p1', 'item_id': 'i1', 'item': {'target_files': ['index.html'], 'risk_level': 'low'}, 'source_type': 'plan_item'},
    )
    assert has_content is True
    assert proposal.metadata['file_changes'] == file_changes
    assert proposal.target_files == ['index.html', 'style.css']


def test_patch_proposal_planitem_draft_carries_file_changes(tmp_path):
    storage = AtlasPlanPoolStorage(tmp_path)
    journal = AtlasJournal(tmp_path)
    svc = AtlasPatchProposalPlanItemDraftService(journal=journal, storage=storage)
    file_changes = [
        {'path': 'index.html', 'action_type': 'create', 'proposed_content': '<!doctype html>\n'},
        {'path': 'style.css', 'action_type': 'create', 'proposed_content': 'body{}\n'},
    ]
    item = AtlasPlanItem(
        item_id='i1',
        pool_id='p1',
        title='t',
        goal='g',
        target_files=['index.html'],
        metadata={'patch_proposal': {'proposal_id': 'pp1', 'target_files': ['index.html'], 'metadata': {'file_changes': file_changes}}},
    )
    pool = AtlasPlanPool(pool_id='p1', root_goal='g', items=[item])
    draft = svc.build_draft_item(pool, item, SimpleNamespace(run_id='r1'))
    assert [fc['path'] for fc in draft.metadata['file_changes']] == ['index.html', 'style.css']
    assert draft.target_files == ['index.html', 'style.css']
    assert draft.metadata['change_set']['apply_strategy'] == 'preflight_all_then_apply_all'
