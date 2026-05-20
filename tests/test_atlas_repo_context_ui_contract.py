from pathlib import Path


def test_repo_context_dom_ids_exist():
    html = Path('ui.html').read_text(encoding='utf-8')
    assert 'atlas-repo-context-scope-btn' in html
    assert 'atlas-repo-context-snapshot-btn' in html


def test_repo_context_api_helpers_exist():
    js = Path('web/js/atlas_pipeline_api.js').read_text(encoding='utf-8')
    assert 'getRepoContextSnapshot' in js


def test_repo_context_cache_bust_25():
    html = Path('ui.html').read_text(encoding='utf-8')
    assert 'atlas-dashboard-27' in html


def test_impacted_tests_dom_ids_exist():
    html = open('ui.html', encoding='utf-8').read()
    assert 'atlas-repo-context-impacted-tests-btn' in html

def test_impacted_tests_api_helper_exists():
    js = open('web/js/atlas_pipeline_api.js', encoding='utf-8').read()
    assert 'getRepoContextImpactedTests' in js
