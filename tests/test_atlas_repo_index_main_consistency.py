from pathlib import Path
import re

UI_HTML = Path("ui.html")
PIPELINE_API = Path("web/js/atlas_pipeline_api.js")
DASHBOARD = Path("web/js/atlas_dashboard.js")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_repo_index_pipeline_api_helpers_exist_in_real_main_file():
    js = _text(PIPELINE_API)
    for token in [
        "getRepoIndexPolicies()",
        "buildRepoIndex(payload)",
        "getRepoIndexImpacts(payload)",
        "getRepoIndexRelatedTests(payload)",
        "getLatestRepoIndex(payload)",
        "getRepoIndexResult(projectHash, indexRunId)",
    ]:
        assert token in js


def test_repo_index_pipeline_api_endpoint_strings_exist():
    js = _text(PIPELINE_API)
    for endpoint in [
        "/api/atlas/repo-index/policies",
        "/api/atlas/repo-index/build",
        "/api/atlas/repo-index/impacts",
        "/api/atlas/repo-index/related-tests",
        "/api/atlas/repo-index/latest",
        "/api/atlas/repo-index/results/",
    ]:
        assert endpoint in js


def test_repo_index_dashboard_bindings_exist_in_real_main_file():
    js = _text(DASHBOARD)
    for token in [
        "renderRepoIndexPanel",
        "buildRepoIndexFromUI",
        "loadLatestRepoIndexFromUI",
        "queryRepoIndexImpactsFromUI",
        "queryRepoIndexRelatedTestsFromUI",
        "atlas-repo-index-build-btn",
        "atlas-repo-index-latest-btn",
        "atlas-repo-index-impacts-btn",
        "atlas-repo-index-related-tests-btn",
        "addEventListener('click', buildRepoIndexFromUI)",
        "addEventListener('click', loadLatestRepoIndexFromUI)",
        "addEventListener('click', queryRepoIndexImpactsFromUI)",
        "addEventListener('click', queryRepoIndexRelatedTestsFromUI)",
    ]:
        assert token in js


def test_repo_index_card_exists_in_real_ui_html():
    html = _text(UI_HTML)
    for dom_id in [
        "atlas-repo-index-card",
        "atlas-repo-index-project-path",
        "atlas-repo-index-build-btn",
        "atlas-repo-index-latest-btn",
        "atlas-repo-index-changed-files",
        "atlas-repo-index-impacts-btn",
        "atlas-repo-index-related-tests-btn",
        "atlas-repo-index-status",
        "atlas-repo-index-summary",
        "atlas-repo-index-result",
    ]:
        assert dom_id in html
    panel_start = html.index('id="atlas-automation-extensions-panel"')
    panel_end = html.index('</section>', panel_start)
    panel_html = html[panel_start:panel_end]
    assert 'id="atlas-repo-index-card"' in panel_html

    html_end = html.rfind("</html>")
    assert html_end != -1
    assert html[html_end + len("</html>"):].strip() == ""


def test_repo_index_cache_bust_23():
    html = _text(UI_HTML)
    assert 'atlas-dashboard-23' in html
    assert 'atlas-dashboard-22' not in html


def test_repo_index_classic_script_contract():
    html = _text(UI_HTML)
    assert '/static/js/atlas_pipeline_api.js' in html
    assert '/static/js/atlas_dashboard.js' in html
    assert 'type="module"' not in html

    api_js = _text(PIPELINE_API)
    dash_js = _text(DASHBOARD)
    assert re.search(r'^\s*import\s+', api_js, re.M) is None
    assert re.search(r'^\s*export\s+', api_js, re.M) is None
    assert re.search(r'^\s*import\s+', dash_js, re.M) is None
    assert re.search(r'^\s*export\s+', dash_js, re.M) is None
