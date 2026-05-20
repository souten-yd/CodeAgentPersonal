from pathlib import Path

def test_repo_index_required_dom_ids_exist():
    text=Path('ui.html').read_text(encoding='utf-8')
    for idv in ['atlas-repo-index-card','atlas-repo-index-project-path','atlas-repo-index-build-btn','atlas-repo-index-latest-btn','atlas-repo-index-changed-files','atlas-repo-index-impacts-btn','atlas-repo-index-related-tests-btn','atlas-repo-index-status','atlas-repo-index-summary','atlas-repo-index-result']:
        assert idv in text

def test_repo_index_cache_bust_20():
    assert 'atlas-dashboard-20' in Path('ui.html').read_text(encoding='utf-8')

def test_repo_index_uses_api_helpers():
    js=Path('web/js/atlas_pipeline_api.js').read_text(encoding='utf-8')
    assert 'getRepoIndexPolicies' in js and 'getRepoIndexResult' in js

def test_repo_index_buttons_bound_in_dashboard():
    js=Path('web/js/atlas_dashboard.js').read_text(encoding='utf-8')
    assert 'buildRepoIndexFromUI' in js and 'queryRepoIndexRelatedTestsFromUI' in js
