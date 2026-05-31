from __future__ import annotations

from types import SimpleNamespace

from agent.atlas_plan_item_patchability import classify_plan_item_patchability
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool


def _item(*, item_type='implementation', action_type='create', target_files=None, metadata=None):
    return AtlasPlanItem(
        item_id='i1',
        pool_id='p1',
        title='t',
        goal='g',
        item_type=item_type,
        risk_level='low',
        status='ready',
        target_files=target_files if target_files is not None else ['a.txt'],
        metadata={'action_type': action_type, **(metadata or {})},
    )


def _raw_item(*, item_type='implementation', action_type='create', target_files=None, metadata=None):
    """Create a duck-typed item for testing with non-schema item_type strings."""
    return SimpleNamespace(
        item_type=item_type,
        risk_level='low',
        target_files=target_files if target_files is not None else ['a.txt'],
        metadata={'action_type': action_type, **(metadata or {})},
    )


# ── Non-patch item types ──────────────────────────────────────────────────────

def test_research_item_not_patchable():
    result = classify_plan_item_patchability(_item(item_type='research'))
    assert result['patchable'] is False
    assert result['reason'] == 'non_patch_plan_item'


def test_planning_item_not_patchable():
    result = classify_plan_item_patchability(_item(item_type='planning'))
    assert result['patchable'] is False
    assert result['reason'] == 'non_patch_plan_item'


def test_verification_item_not_patchable():
    result = classify_plan_item_patchability(_item(item_type='verification'))
    assert result['patchable'] is False
    assert result['reason'] == 'non_patch_plan_item'


def test_nexus_save_item_not_patchable():
    result = classify_plan_item_patchability(_item(item_type='nexus_save'))
    assert result['patchable'] is False
    assert result['reason'] == 'non_patch_plan_item'


def test_clarification_item_type_string_not_patchable():
    result = classify_plan_item_patchability(_raw_item(item_type='clarification'))
    assert result['patchable'] is False
    assert result['reason'] == 'non_patch_plan_item'


def test_manual_confirmation_item_type_not_patchable():
    result = classify_plan_item_patchability(_raw_item(item_type='manual_confirmation'))
    assert result['patchable'] is False
    assert result['reason'] == 'non_patch_plan_item'


def test_inspect_item_type_not_patchable():
    result = classify_plan_item_patchability(_raw_item(item_type='inspect'))
    assert result['patchable'] is False
    assert result['reason'] == 'non_patch_plan_item'


# ── run_command action ────────────────────────────────────────────────────────

def test_run_command_action_blocked_before_patch_apply():
    result = classify_plan_item_patchability(_item(action_type='run_command'))
    assert result['patchable'] is False
    assert result['reason'] == 'run_command_clarification'


def test_delete_action_blocked():
    result = classify_plan_item_patchability(_item(action_type='delete'))
    assert result['patchable'] is False
    assert result['reason'] == 'forbidden_action_type'


# ── Missing concrete target ───────────────────────────────────────────────────

def test_create_without_target_files_and_file_changes_blocked():
    item = _item(target_files=[], metadata={'proposed_content': 'x\n'})
    result = classify_plan_item_patchability(item)
    assert result['patchable'] is False
    assert result['reason'] == 'no_concrete_target'


def test_create_with_file_changes_is_eligible():
    item = _item(
        target_files=[],
        metadata={
            'file_changes': [{'path': 'a.txt', 'action_type': 'create', 'proposed_content': 'x\n'}],
        },
    )
    result = classify_plan_item_patchability(item)
    assert result['patchable'] is True


def test_create_with_target_files_and_patch_content_is_eligible():
    item = _item(metadata={'proposed_content': 'hello\n'})
    result = classify_plan_item_patchability(item)
    assert result['patchable'] is True


# ── Missing patch content ─────────────────────────────────────────────────────

def test_create_without_any_patch_content_blocked():
    item = _item(metadata={})
    result = classify_plan_item_patchability(item)
    assert result['patchable'] is False
    assert result['reason'] == 'patch_content_missing'


def test_create_with_edits_list_is_eligible():
    item = _item(metadata={'edits': [{'old_string': 'a', 'new_string': 'b'}]})
    result = classify_plan_item_patchability(item)
    assert result['patchable'] is True


def test_create_with_append_content_is_eligible():
    item = _item(metadata={'append_content': 'extra\n'})
    result = classify_plan_item_patchability(item)
    assert result['patchable'] is True


def test_create_with_unified_diff_preview_is_eligible():
    item = _item(metadata={'unified_diff_preview': '@@ -1 +1 @@\n-old\n+new\n'})
    result = classify_plan_item_patchability(item)
    assert result['patchable'] is True


# ── Documentation item (also patchable) ──────────────────────────────────────

def test_documentation_item_with_content_is_patchable():
    item = _item(item_type='documentation', metadata={'proposed_content': '# Docs\n'})
    result = classify_plan_item_patchability(item)
    assert result['patchable'] is True


# ── Repair intent: implementation update should be required ──────────────────

def test_implementation_item_for_index_html_repair_is_eligible():
    """Repair prompt targeting index.html should require an update item for index.html."""
    item = _item(
        action_type='update',
        target_files=['index.html'],
        metadata={'proposed_content': '<!doctype html><html><body>fixed</body></html>\n'},
    )
    result = classify_plan_item_patchability(item)
    assert result['patchable'] is True
