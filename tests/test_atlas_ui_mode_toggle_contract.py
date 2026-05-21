from pathlib import Path


def test_ui_mode_helpers_and_bindings_contract():
    js = Path('web/js/atlas_dashboard.js').read_text(encoding='utf-8')
    for token in ['setAtlasUiMode', 'getAtlasUiMode', 'renderAtlasUiMode', 'atlas:uiMode', 'data-atlas-ui-mode', 'atlas-workflow-advanced-toggle', 'atlas-workflow-diagnostics-toggle', 'atlas-diagnostics-status']:
        assert token in js
    end = js.rfind('})();')
    for token in ['setAtlasUiMode', 'getAtlasUiMode', 'renderAtlasUiMode', 'bindWorkflowShell']:
        assert js.find(token, 0, end) != -1
    banned = ['safe_apply', 'verification', 'patch generation', 'retry', 'rollback', 'fetch(', 'axios', '/api/']
    snippet = js[js.index('function setAtlasUiMode'):js.index('function bindOperatorLoop')]
    for b in banned:
        assert b not in snippet.lower()
    assert 'import ' not in js and 'export ' not in js
