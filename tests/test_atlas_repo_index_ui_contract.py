from pathlib import Path

UI_PATH = Path('ui.html')
API_PATH = Path('web/js/atlas_pipeline_api.js')
DASHBOARD_PATH = Path('web/js/atlas_dashboard.js')

REPO_INDEX_DOM_IDS = [
    'atlas-repo-index-card',
    'atlas-repo-index-project-path',
    'atlas-repo-index-build-btn',
    'atlas-repo-index-latest-btn',
    'atlas-repo-index-changed-files',
    'atlas-repo-index-impacts-btn',
    'atlas-repo-index-related-tests-btn',
    'atlas-repo-index-status',
    'atlas-repo-index-summary',
    'atlas-repo-index-result',
]


def test_repo_index_required_dom_ids_exist():
    text = UI_PATH.read_text(encoding='utf-8')
    for dom_id in REPO_INDEX_DOM_IDS:
        assert dom_id in text


def test_repo_index_dom_inside_automation_extensions_panel():
    text = UI_PATH.read_text(encoding='utf-8')
    panel_start = text.index('id="atlas-automation-extensions-panel"')
    panel_end = text.index('</section>', panel_start)
    panel_html = text[panel_start:panel_end]
    assert 'id="atlas-repo-index-card"' in panel_html


def test_repo_index_copy_is_atlas_only():
    text = UI_PATH.read_text(encoding='utf-8')
    assert 'Builds a read-only symbol index and dependency graph.' in text
    assert 'This does not modify files.' in text
    assert 'This does not run shell commands or remote git.' in text


def test_repo_index_cache_bust_21():
    text = UI_PATH.read_text(encoding='utf-8')
    assert 'atlas-dashboard-24' in text


def test_repo_index_helpers_exist_in_pipeline_api():
    js = API_PATH.read_text(encoding='utf-8')
    required = [
        'getRepoIndexPolicies',
        'buildRepoIndex(payload)',
        'getRepoIndexImpacts(payload)',
        'getRepoIndexRelatedTests(payload)',
        'getLatestRepoIndex(payload)',
        'getRepoIndexResult(projectHash, indexRunId)',
    ]
    for helper in required:
        assert helper in js

    for endpoint in [
        '/api/atlas/repo-index/policies',
        '/api/atlas/repo-index/build',
        '/api/atlas/repo-index/impacts',
        '/api/atlas/repo-index/related-tests',
        '/api/atlas/repo-index/latest',
        '/api/atlas/repo-index/results/',
    ]:
        assert endpoint in js


def test_repo_index_dashboard_bindings_exist():
    js = DASHBOARD_PATH.read_text(encoding='utf-8')
    required = [
        'renderRepoIndexPanel',
        'buildRepoIndexFromUI',
        'loadLatestRepoIndexFromUI',
        'queryRepoIndexImpactsFromUI',
        'queryRepoIndexRelatedTestsFromUI',
        "addEventListener('click', buildRepoIndexFromUI)",
        "addEventListener('click', loadLatestRepoIndexFromUI)",
        "addEventListener('click', queryRepoIndexImpactsFromUI)",
        "addEventListener('click', queryRepoIndexRelatedTestsFromUI)",
    ]
    for marker in required:
        assert marker in js


def test_classic_script_contract_is_maintained():
    text = UI_PATH.read_text(encoding='utf-8')
    assert '/static/js/atlas_pipeline_api.js' in text
    assert '/static/js/atlas_dashboard.js' in text
    assert 'type="module"' not in text
