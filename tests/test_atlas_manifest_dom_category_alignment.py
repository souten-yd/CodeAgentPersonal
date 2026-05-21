import json
from pathlib import Path


def _container_window(html: str, sid: str, radius: int = 4000):
    idx = html.index(f'id="{sid}"')
    return html[max(0, idx - radius): idx + radius]


def test_manifest_dom_category_alignment_container_aware():
    manifest = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text(encoding='utf-8'))
    html = Path('ui.html').read_text(encoding='utf-8')

    for s in manifest['surfaces']:
        sid = s['id']
        if f'id="{sid}"' not in html:
            continue
        window = _container_window(html, sid)
        category = s['category']
        if category == 'advanced_execution':
            assert 'atlas-surface-advanced' in window
        elif category == 'diagnostics':
            assert 'atlas-surface-diagnostics' in window
        elif category == 'safety_always_visible':
            assert s['default_visible'] is True
            assert s['can_hide'] is False


def test_forbidden_surfaces_not_classified_as_minimal():
    manifest = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text(encoding='utf-8'))
    by_id = {s['id']: s for s in manifest['surfaces']}
    for sid in [
        'atlas-plan-item-impact-map-btn',
        'atlas-context-refresh-v2-btn',
        'atlas-planner-packaging-v2-btn',
        'atlas-verification-recommendation-btn',
        'atlas-patch-regen-from-recommendation-panel',
        'atlas-supervised-handoff-retry-panel',
    ]:
        assert by_id[sid]['category'] != 'minimal_workflow'
