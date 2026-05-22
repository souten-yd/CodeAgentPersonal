import json
from pathlib import Path


ALLOWED = {'minimal_workflow', 'advanced_execution', 'diagnostics', 'safety_always_visible', 'deprecated', 'removed_after_migration'}


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


def test_pr80_manifest_vue_checkpoint_contract():
    m = _manifest()
    assert m['automation_first'] is True
    assert m['cli_compatible_target'] is True
    assert m['replaceable_ui_target'] is True
    assert m['workflow_state_owner'] == 'backend'
    assert m['vue_migration_checkpoint'] == 'PR-ATLAS-SCALE-80'
    assert 'Vue 3' in m['vue_target']
    assert m['vue_entry_strategy'] == 'parallel_ui_first'
    assert m['legacy_ui_policy'] == 'keep_until_vue_parity'
    assert m['ui_cleanup_policy_doc'] == 'docs/atlas_autonomous_first_ui_policy.md'
    assert m['vue_migration_plan_doc'] == 'docs/atlas_vue_migration_plan.md'
    assert m['workflow_state_machine_ui'] is True
    assert m['primary_cta_policy'] == 'single_existing_manual_action_only'


def test_scale77_workflow_state_machine_surfaces():
    m = _manifest()
    by_id = {s['id']: s for s in m['surfaces']}
    for sid in ['atlas-workflow-primary-action-reason', 'atlas-workflow-safety-summary']:
        assert sid in by_id
        assert by_id[sid]['category'] == 'minimal_workflow'
        assert by_id[sid]['default_visible'] is True
        assert by_id[sid]['can_hide'] is False


def test_pr80_surface_categories_and_safety_constraints():
    m = _manifest()
    surfaces = m['surfaces']
    cats = {s['category'] for s in surfaces}
    for required in ['minimal_workflow','safety_always_visible','advanced_execution','diagnostics','deprecated','removed_after_migration']:
        assert required in ALLOWED
    for s in surfaces:
        if s['category'] == 'safety_always_visible':
            assert s['default_visible'] is True
            assert s['category'] != 'deprecated'


def test_vue_next_manifest_flags():
    m = _manifest()
    assert m['vue_next_allowed_after_pr92'] is True
    assert m['vue_next_foundation'] is True
    assert m['vue_next_runtime_gate'] == 'parallel_read_only'
    assert m['vue_next_adapter'] == 'read_only_workflow_state'
    assert m['vue_next_mutation_endpoints_enabled'] is False
    assert m['vue_next_action_buttons_enabled'] is False
    assert m['vue_next_route_mounted'] is False
    assert m['vue_next_default_enabled'] is False
    assert m['vue_next_execution_enabled'] is False
    assert m['vue_next_source_of_truth'] is False
    assert m['vue_next_backend_authoritative'] is True
    assert m['vue_next_read_only_shell'] is True


def test_vue_next_v04_manifest_decision_flags():
    m = _manifest()
    assert m['vue_next_get_adapter_decision'] in {'deferred_no_stable_get_contract', 'connected_safe_get'}
    assert m['vue_next_static_mount_decision'] in {'deferred_no_dist_strategy', 'mounted_static_dist'}
    assert m['vue_next_available_actions_metadata_only'] is True
    assert m['vue_next_backend_state_parity_hardened'] is True
    assert m['vue_next_policy'] == 'docs/atlas_vue_migration_plan.md'
