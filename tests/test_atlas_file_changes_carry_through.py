from types import SimpleNamespace

from agent.atlas_journal import AtlasJournal
from agent.atlas_patch_proposal_schema import AtlasPatchProposalRequest
from agent.atlas_patch_proposal_planitem_service import AtlasPatchProposalPlanItemDraftService
from agent.atlas_patch_proposal_service import AtlasPatchProposalService
from agent.atlas_plan_item_file_changes import (
    collect_normalization_warnings,
    detect_duplicate_file_change_paths,
    detect_executor_readable_content,
    extract_planned_paths,
)
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


def test_single_static_html_medium_risk_normalizes_to_low(tmp_path):
    svc = AtlasPatchProposalService(journal=AtlasJournal(tmp_path), storage=AtlasPlanPoolStorage(tmp_path))
    proposal, has_content = svc._build_proposal_from_output(
        {
            'summary': 'update heading',
            'target_files': ['index.html'],
            'edits': [{'old_string': '<h1>Old</h1>', 'new_string': '<h1>Ready</h1>'}],
            'risk_level': 'medium',
        },
        {
            'pool_id': 'p1',
            'item_id': 'i1',
            'item': {'target_files': ['index.html'], 'risk_level': 'medium', 'action_type': 'update'},
            'source_type': 'plan_item',
        },
    )

    assert has_content is True
    assert proposal.risk_level == 'low'
    assert 'single_static_html_medium_risk_normalized_to_low' in proposal.warnings


def test_patch_proposal_result_metadata_detects_file_changes_content(tmp_path):
    storage = AtlasPlanPoolStorage(tmp_path)
    journal = AtlasJournal(tmp_path)
    file_changes = [
        {'path': 'index.html', 'action_type': 'create', 'proposed_content': '<!doctype html>\n<link rel="stylesheet" href="style.css">\n'},
        {'path': 'style.css', 'action_type': 'create', 'proposed_content': 'body{}\n'},
    ]
    item = AtlasPlanItem(
        item_id='i1',
        pool_id='p1',
        title='Create HTML app with stylesheet',
        goal='Create index.html and style.css for a styled page',
        target_files=['index.html', 'style.css'],
        metadata={'action_type': 'create'},
    )
    pool = AtlasPlanPool(pool_id='p1', root_goal='g', items=[item])
    storage.save_pool(pool)
    journal.save_plan_pool(pool)

    def llm_json_fn(system_prompt, user_prompt, **kwargs):
        return {'summary': 'multi', 'file_changes': file_changes, 'risk_level': 'low'}

    svc = AtlasPatchProposalService(journal=journal, storage=storage, llm_json_fn=llm_json_fn)
    result = svc.propose_for_item(AtlasPatchProposalRequest(pool_id='p1', item_id='i1', run_id='r1', source_type='plan_item'))

    assert result.status == 'proposed'
    assert result.metadata['patch_content_available'] is True
    assert result.proposal.unified_diff_preview == ''
    assert 'proposed_content' not in result.proposal.metadata
    assert result.proposal.metadata['file_changes'] == file_changes


def test_patch_proposal_self_review_regenerates_invalid_or_incomplete_content(tmp_path):
    storage = AtlasPlanPoolStorage(tmp_path)
    journal = AtlasJournal(tmp_path)
    item = AtlasPlanItem(
        item_id='i1',
        pool_id='p1',
        title='Create greeting module',
        goal='Expose Hello World greeting',
        done_definition=['Hello World appears in the generated content'],
        target_files=['greeting.py'],
        metadata={'action_type': 'create'},
    )
    pool = AtlasPlanPool(pool_id='p1', root_goal='g', project_path=str(tmp_path), items=[item])
    storage.save_pool(pool)
    journal.save_plan_pool(pool)
    calls = []

    def llm_json_fn(system_prompt, user_prompt, **kwargs):
        calls.append(user_prompt)
        if len(calls) == 1:
            return {'target_files': ['greeting.py'], 'proposed_content': 'def greet(:\n    return "Hi"\n', 'risk_level': 'low'}
        assert 'self_review_feedback' in user_prompt
        return {'target_files': ['greeting.py'], 'proposed_content': 'def greet():\n    return "Hello World"\n', 'risk_level': 'low'}

    svc = AtlasPatchProposalService(journal=journal, storage=storage, llm_json_fn=llm_json_fn)
    result = svc.propose_for_item(AtlasPatchProposalRequest(pool_id='p1', item_id='i1', run_id='r1', source_type='plan_item'))

    assert result.status == 'proposed'
    assert len(calls) == 2
    assert result.proposal.metadata['self_review']['status'] == 'passed'
    assert result.proposal.metadata['self_review']['regenerated'] is True
    assert 'Hello World' in result.proposal.metadata['proposed_content']


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


def test_patch_proposal_planitem_draft_carries_surgical_edits(tmp_path):
    storage = AtlasPlanPoolStorage(tmp_path)
    journal = AtlasJournal(tmp_path)
    svc = AtlasPatchProposalPlanItemDraftService(journal=journal, storage=storage)
    edits = [
        {'old_string': '<h1>Atlas Existing Baseline</h1>', 'new_string': '<h1>Atlas Existing Project Ready</h1>'},
    ]
    item = AtlasPlanItem(
        item_id='i1',
        pool_id='p1',
        title='t',
        goal='g',
        target_files=['index.html'],
        metadata={
            'action_type': 'update',
            'patch_proposal': {
                'proposal_id': 'pp1',
                'target_files': ['index.html'],
                'risk_level': 'low',
                'metadata': {'edits': edits},
            },
        },
    )
    pool = AtlasPlanPool(pool_id='p1', root_goal='g', items=[item])
    draft = svc.build_draft_item(pool, item, SimpleNamespace(run_id='r1'))

    assert draft.metadata['edits'] == edits
    assert draft.metadata['patch_proposal']['edits'] == edits
    assert detect_executor_readable_content(draft) is True


def test_plan_item_file_change_helper_surfaces_planned_paths_warnings_and_content():
    item = AtlasPlanItem(
        item_id='i1',
        pool_id='p1',
        title='t',
        goal='g',
        target_files=['legacy.txt'],
        metadata={
            'action_type': 'create',
            'file_changes': [
                {'path': 'index.html', 'action_type': 'create', 'proposed_content': '<!doctype html>\n'},
                {'path': 'index.html', 'action_type': 'create', 'proposed_content': '<!doctype html>\n'},
            ],
        },
    )

    assert extract_planned_paths(item) == ['index.html']
    assert detect_duplicate_file_change_paths(item) == ['index.html']
    assert detect_executor_readable_content(item) is True
    assert 'target_file_without_file_change' in collect_normalization_warnings(item)
    assert 'target_file_without_file_change' in item.metadata['normalization_warnings']
