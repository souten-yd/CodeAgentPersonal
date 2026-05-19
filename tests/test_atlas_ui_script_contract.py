from pathlib import Path
import re


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_atlas_pipeline_api_is_classic_script_safe():
    js = _read("web/js/atlas_pipeline_api.js")
    assert re.search(r"^\s*export\s+", js, re.M) is None
    assert re.search(r"^\s*import\s+", js, re.M) is None
    assert "root.AtlasPipelineAPI = AtlasPipelineAPI" in js or "window.AtlasPipelineAPI" in js


def test_ui_loads_atlas_pipeline_api_as_classic_script():
    html = _read("ui.html")
    m = re.search(r"<script[^>]+atlas_pipeline_api\.js\?v=atlas-dashboard-16[^>]*>", html)
    assert m, "atlas_pipeline_api script tag missing"
    assert "type=\"module\"" not in m.group(0)
    js = _read("web/js/atlas_pipeline_api.js")
    assert re.search(r"^\s*export\s+", js, re.M) is None


def test_no_visible_dom_after_html_close():
    html = _read("ui.html")
    idx = html.rfind("</html>")
    assert idx != -1
    tail = html[idx + len("</html>"):].strip()
    assert tail == ""
    assert "atlas-supervised-item-status-note" not in tail


def test_pr54_note_not_visible_in_lumen_root():
    html = _read("ui.html")
    phrase = "This only finalizes item status and next action"
    if phrase in html:
        assert 'id="atlas-automation-extensions-panel"' in html
        assert 'id="atlas-supervised-item-status-panel"' in html
        body_close = html.rfind("</body>")
        assert body_close != -1
        assert phrase not in html[body_close:]


def test_atlas_create_plan_button_contract():
    html = _read("ui.html")
    assert 'id="atlas-create-plan-btn"' in html
    assert 'onclick="window.AtlasDashboard?.createPlanPool()"' in html

    dashboard_js = _read("web/js/atlas_dashboard.js")
    assert "root.AtlasDashboard" in dashboard_js
    assert "root.AtlasPipelineAPI" in dashboard_js
