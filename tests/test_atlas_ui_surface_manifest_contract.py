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
    assert 'frontend_simplification' in m['thinui_role']
    assert 'replacement' not in m['thinui_role']
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
