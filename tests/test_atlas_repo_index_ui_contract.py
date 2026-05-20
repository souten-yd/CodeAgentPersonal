from pathlib import Path

def test_repo_index_dom_ids_exist():
    text=Path('ui.html').read_text(encoding='utf-8')
    for idv in ['atlas-repo-index-card','atlas-repo-index-project-path','atlas-repo-index-build-btn','atlas-repo-index-latest-btn','atlas-repo-index-changed-files','atlas-repo-index-impacts-btn','atlas-repo-index-related-tests-btn','atlas-repo-index-status','atlas-repo-index-summary','atlas-repo-index-result']:
        assert idv in text
