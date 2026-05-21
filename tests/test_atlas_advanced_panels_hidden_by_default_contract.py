from pathlib import Path
import json


def test_ui_mode_and_shell_visibility_contract():
    html = Path('ui.html').read_text(encoding='utf-8')
    assert 'id="atlas-dashboard"' in html and 'data-atlas-ui-mode="minimal"' in html
    assert 'id="atlas-workflow-shell"' in html
    assert 'id="atlas-workflow-advanced-toggle"' in html
    assert 'id="atlas-workflow-diagnostics-toggle"' in html
    assert 'atlas-dashboard-41' in html


def test_advanced_and_diagnostics_markers_present_without_id_removal():
    html = Path('ui.html').read_text(encoding='utf-8')
    advanced_ids = [
        'atlas-operator-loop-card',
        'atlas-next-action-orchestrator-panel',
        'atlas-multi-item-supervised-status-panel',
        'atlas-handoff-safe-apply-panel',
        'atlas-supervised-handoff-retry-panel',
        'atlas-patch-regen-from-recommendation-panel',
    ]
    diagnostics_ids = [
        'atlas-plan-item-impact-map-btn',
        'atlas-context-refresh-v2-btn',
        'atlas-planner-packaging-v2-btn',
        'atlas-verification-recommendation-btn',
        'atlas-verification-recommendation-handoff-btn',
    ]
    for sid in advanced_ids:
        ix = html.index(f'id="{sid}"')
        assert 'atlas-surface-advanced' in html[max(0, ix-180):ix+220]
    for sid in diagnostics_ids:
        ix = html.index(f'id="{sid}"')
        assert 'atlas-surface-diagnostics' in html[max(0, ix-180):ix+220]

    manifest = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text(encoding='utf-8'))
    for sid in [s['id'] for s in manifest['surfaces']]:
        assert f'id="{sid}"' in html or sid.startswith('atlas-workflow-') or sid in {'atlas-operator-loop-dry-run-btn','atlas-operator-loop-execute-btn','atlas-operator-loop-execute-refresh-btn'}
