from pathlib import Path

DOCS = [
    'docs/atlas_scale_master_roadmap.md',
    'docs/atlas_development_handoff.md',
    'docs/atlas_autonomous_execution_readiness_policy.md',
    'docs/atlas_thinui_readiness.md',
    'docs/atlas_vue_migration_plan.md',
]


def test_docs_advance_to_scale_111_pointer_after_scale_110():
    for doc in DOCS:
        text = Path(doc).read_text(encoding='utf-8')
        assert 'Completed automation PR: PR-ATLAS-SCALE-111' in text
        assert 'Current automation track: PR-ATLAS-SCALE-112' in text
        assert 'Next automation track: PR-ATLAS-SCALE-112' in text
        assert 'Planned UI track: return to PR-ATLAS-SCALE-112 automation track' in text
        assert 'next work is PR-ATLAS-SCALE-112' in text
        assert 'next PR may add local-only diff label conflict resolution, not execution enable' in text


def test_scale_110_label_filtered_export_ui_is_local_only_and_non_execution():
    text = Path('web/atlas-next/src/components/Level1ReadinessPanel.vue').read_text(encoding='utf-8')
    required = [
        'Copy label-filtered diff JSON',
        'Export label-filtered diff JSON',
        'Copy label-filtered summary',
        'Export label-filtered summary',
        'local_diff_label_filter',
        'local_diff_label_filter_local_only: true',
        'local_diff_label_filter_summary',
        'local_diff_label_filtered_items',
        'local_diff_label_filtered_items_local_only: true',
        'navigator.clipboard.writeText',
        'JSON.stringify',
        'new Blob',
        'URL.createObjectURL',
    ]
    for token in required:
        assert token in text

    blocked = ['execute', 'approval', 'apply', 'verify', 'rollback', 'retry', 'continue', 'dry-run']
    actions = '\n'.join([line.lower() for line in text.splitlines() if 'label-filtered' in line.lower()])
    for token in blocked:
        assert token not in actions


def test_api_get_only_and_desktop_lumen_preserved():
    dashboard = Path('web/js/atlas_dashboard.js').read_text(encoding='utf-8')
    api = Path('web/js/atlas_pipeline_api.js').read_text(encoding='utf-8')
    debug = Path('scripts/run_debug_test_matrix.py').read_text(encoding='utf-8')
    css = Path('web/css/desktop_lumen.css').read_text(encoding='utf-8') if Path('web/css/desktop_lumen.css').exists() else ''
    assert 'fetchLevel1ReadinessDiagnostics' in Path('web/atlas-next/src/components/Level1ReadinessPanel.vue').read_text(encoding='utf-8')
    for forbidden in ['/api/level1/execute', '/api/level1/dry-run', '/api/level1/approval', '/api/level1/apply', '/api/level1/verify', '/api/level1/rollback', '/api/level1/retry', '/api/level1/continue']:
        assert forbidden not in dashboard
    assert 'desktop_lumen_input_visible' in debug
    if css:
        assert 'display' in css
