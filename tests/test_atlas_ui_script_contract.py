from pathlib import Path
import re


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _ui_html_loaded_classic_script_names() -> list[str]:
    html = _read("ui.html")
    matches = re.findall(r"<script\b([^>]*?)\bsrc=[\"'](/static/js/[^\"']+)[\"']([^>]*)>", html, re.I)
    script_names: list[str] = []
    for before, src, after in matches:
        attrs = f"{before} {after}"
        if re.search(r"\btype\s*=\s*[\"']module[\"']", attrs, re.I):
            continue
        filename = src.split("?", 1)[0].rsplit("/", 1)[-1]
        script_names.append(filename)
    return script_names


def test_all_ui_html_loaded_static_js_are_classic_script_safe():
    loaded = _ui_html_loaded_classic_script_names()
    assert loaded, "No classic /static/js/*.js scripts were found in ui.html"

    required = {
        "app.js",
        "settings.js",
        "skills_memory.js",
        "panels.js",
        "lumen_api.js",
        "lumen_tools.js",
        "lumen.js",
        "nexus.js",
        "atlas_pipeline_api.js",
        "atlas_dashboard.js",
        "echo.js",
    }
    assert required.issubset(set(loaded)), f"Missing required scripts from ui.html: {sorted(required - set(loaded))}"

    for name in loaded:
        path = Path("web/js") / name
        assert path.exists(), f"Script loaded by ui.html is missing: {path}"
        js = path.read_text(encoding="utf-8")
        assert re.search(r"^\s*export\s+", js, re.M) is None, f"export found in classic script: {name}"
        assert re.search(r"^\s*import\s+[^('\"]", js, re.M) is None, f"static import found in classic script: {name}"


def test_required_global_objects_are_exposed():
    checks = [
        ("web/js/lumen_api.js", ["window.LumenAPI"]),
        ("web/js/lumen_tools.js", ["window.LumenTools"]),
        ("web/js/lumen.js", ["window.Lumen"]),
        ("web/js/atlas_pipeline_api.js", ["root.AtlasPipelineAPI = AtlasPipelineAPI"]),
        ("web/js/atlas_dashboard.js", ["root.AtlasDashboard", "window.AtlasDashboard"]),
        ("web/js/panels.js", ["window.switchTab = switchTab"]),
        ("web/js/echo.js", ["window.syncEchoTranslateUi", "window._echoSetStatus"]),
        ("web/js/nexus.js", ["window.renderNexusDocuments", "window.updateNexusJobBanner"]),
    ]
    for path, any_of in checks:
        js = _read(path)
        assert any(token in js for token in any_of), f"Missing global exposure in {path}: one of {any_of}"


def test_ui_script_order_contract():
    html = _read("ui.html")
    srcs = re.findall(r"<script\b[^>]*\bsrc=[\"'](/static/js/[^\"']+)[\"'][^>]*>", html, re.I)
    names = [src.split("?", 1)[0].rsplit("/", 1)[-1] for src in srcs]
    expected_order = [
        "app.js",
        "settings.js",
        "skills_memory.js",
        "panels.js",
        "lumen_api.js",
        "lumen_tools.js",
        "lumen.js",
        "nexus.js",
        "atlas_pipeline_api.js",
        "atlas_dashboard.js",
        "echo.js",
    ]
    for name in expected_order:
        assert name in names, f"{name} not found in ui.html scripts"
    indexes = [names.index(name) for name in expected_order]
    assert indexes == sorted(indexes), f"Script order mismatch: {list(zip(expected_order, indexes))}"


def test_atlas_pipeline_api_contains_expected_helpers_after_classic_conversion():
    js = _read("web/js/atlas_pipeline_api.js")
    expected_helpers = [
        "createPlanPool",
        "startPipelineDryRun",
        "getSymbolIndex",
        "getDependencyGraph",
        "getRelatedTests",
        "getBoundedRetryPolicies",
        "runBoundedRetry",
        "getPatchRegenPolicies",
        "runPatchRegen",
        "getPatchCandidateApprovalPolicies",
        "decidePatchCandidateApproval",
        "getSupervisedHandoffSafeApplyPolicies",
        "executeSupervisedHandoffSafeApply",
        "getSupervisedHandoffVerificationPolicies",
        "runSupervisedHandoffVerification",
        "getSupervisedHandoffRetryPolicies",
        "runSupervisedHandoffRetry",
        "getPatchRegenRecommendationPolicies",
        "runPatchRegenRecommendation",
        "getManualNextActionExecutorPolicies",
        "executeManualNextAction",
        "previewManualNextActionConfirmationToken",
        "getPostManualExecutionRefreshPolicies",
        "refreshAfterManualExecution",
    ]
    for helper in expected_helpers:
        assert helper in js, f"Missing atlas pipeline helper: {helper}"
    for forbidden in ["apiGet(", "apiPost(", "export async function", "import"]:
        assert forbidden not in js, f"Forbidden pattern found in atlas_pipeline_api.js: {forbidden}"


def test_ui_loads_atlas_pipeline_api_as_classic_script():
    html = _read("ui.html")
    m = re.search(r"<script[^>]+atlas_pipeline_api\.js\?v=atlas-dashboard-17[^>]*>", html)
    assert m, "atlas_pipeline_api script tag missing"
    assert "type=\"module\"" not in m.group(0)


def test_no_visible_dom_after_html_close():
    html = _read("ui.html")
    idx = html.rfind("</html>")
    assert idx != -1
    html_tail = html[idx + len("</html>"):]
    assert html_tail.strip() == ""

    body_close = html.rfind("</body>")
    assert body_close != -1
    after_body = html[body_close + len("</body>"):]
    stripped = re.sub(r"<!--.*?-->", "", after_body, flags=re.S).strip()
    stripped = stripped.replace("</html>", "").strip()
    assert stripped == "", "Visible DOM/content exists after </body>"
    assert "This only finalizes item status and next action" not in after_body
    assert "atlas-supervised-item-status-note" not in html


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
