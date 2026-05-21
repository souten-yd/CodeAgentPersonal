import json
from pathlib import Path


ALLOWED = {'minimal_workflow', 'advanced_execution', 'diagnostics', 'safety_always_visible'}


def _manifest():
    p = Path('web/atlas_ui_surface_manifest.json')
    assert p.exists()
    return json.loads(p.read_text(encoding='utf-8'))


def test_manifest_contract():
    m = _manifest()
    assert m['version'] == 1
    assert m['final_goal'] == 'fully_autonomous_code_agent'
    assert m['thinui_role'] == 'frontend_simplification_for_autonomous_agent'
    assert 'replacement' not in m['thinui_role']
    if 'self_improvement_scope' in m:
        assert m['self_improvement_scope'] == 'self_improving_codeagentpersonal_kasanecore'
    surfaces = m['surfaces']
    assert isinstance(surfaces, list) and surfaces
    for s in surfaces:
        for k in ['id', 'label', 'category', 'default_visible', 'reason', 'can_hide', 'safety_notes']:
            assert k in s
        assert s['category'] in ALLOWED


def test_safety_and_classification_rules():
    m = _manifest()
    by_id = {s['id']: s for s in m['surfaces']}
    for sid in ['atlas-operator-loop-execute-btn', 'atlas-operator-loop-dry-run-btn', 'atlas-operator-loop-execute-refresh-btn']:
        assert by_id[sid]['can_hide'] is False
        assert by_id[sid]['category'] in {'safety_always_visible', 'minimal_workflow'}

    for sid in ['atlas-next-action-orchestrator-panel', 'atlas-multi-item-supervised-status-panel', 'atlas-handoff-safe-apply-panel', 'atlas-supervised-handoff-retry-panel', 'atlas-patch-regen-from-recommendation-panel']:
        assert by_id[sid]['category'] == 'advanced_execution'

    for sid in ['atlas-plan-item-impact-map-btn', 'atlas-context-refresh-v2-btn', 'atlas-planner-packaging-v2-btn', 'atlas-verification-recommendation-btn', 'atlas-verification-recommendation-handoff-btn']:
        assert by_id[sid]['category'] == 'diagnostics'

    for sid in ['atlas-next-action-orchestrator-panel', 'atlas-plan-item-impact-map-btn', 'atlas-verification-recommendation-btn']:
        assert by_id[sid]['category'] != 'minimal_workflow'


def test_scale74_manifest_flags_and_workflow_shell_surfaces():
    m = _manifest()
    assert m['automation_first'] is True
    assert m['cli_compatible_target'] is True
    assert m['replaceable_ui_target'] is True
    assert m['workflow_state_owner'] == 'backend'
    assert m['self_improvement_scope'] == 'self_improving_codeagentpersonal_kasanecore'
    by_id={s['id']:s for s in m['surfaces']}
    for sid in ['atlas-workflow-shell','atlas-workflow-goal','atlas-workflow-project-path','atlas-workflow-mode','atlas-workflow-status','atlas-workflow-phase','atlas-workflow-primary-action-btn','atlas-workflow-stop-btn','atlas-workflow-approval-summary','atlas-workflow-artifacts-summary','atlas-workflow-advanced-toggle','atlas-workflow-diagnostics-toggle']:
        assert sid in by_id
    assert by_id['atlas-workflow-stop-btn']['category'] == 'safety_always_visible'
    assert by_id['atlas-workflow-stop-btn']['can_hide'] is False


def test_scale75_manifest_mode_visibility_contract():
    m = _manifest()
    assert m['default_mode'] == 'minimal'
    assert m['automation_first'] is True
    assert m['cli_compatible_target'] is True
    assert m['replaceable_ui_target'] is True
    assert m['workflow_state_owner'] == 'backend'
    by_id = {s['id']: s for s in m['surfaces']}
    assert by_id['atlas-workflow-shell']['default_visible'] is True
    for sid in ['atlas-next-action-orchestrator-panel','atlas-multi-item-supervised-status-panel','atlas-handoff-safe-apply-panel','atlas-supervised-handoff-retry-panel','atlas-patch-regen-from-recommendation-panel','atlas-operator-loop-card']:
        assert by_id[sid]['category'] == 'advanced_execution'
        assert by_id[sid]['default_visible'] is False
    for sid in ['atlas-plan-item-impact-map-btn','atlas-context-refresh-v2-btn','atlas-planner-packaging-v2-btn','atlas-verification-recommendation-btn','atlas-verification-recommendation-handoff-btn']:
        assert by_id[sid]['category'] == 'diagnostics'
        assert by_id[sid]['default_visible'] is False
    assert by_id['atlas-workflow-stop-btn']['category'] == 'safety_always_visible'
    assert by_id['atlas-workflow-stop-btn']['can_hide'] is False
