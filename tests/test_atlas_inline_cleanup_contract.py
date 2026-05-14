from tests.helpers.ui_contract import WEB_JS_ROOT, load_root_ui_html_text

ATLAS_API = WEB_JS_ROOT / "atlas_api.js"
ATLAS_STATE = WEB_JS_ROOT / "atlas_state.js"
ATLAS_UI = WEB_JS_ROOT / "atlas_ui.js"


def test_atlas_modules_exist():
    assert ATLAS_API.exists()
    assert ATLAS_STATE.exists()
    assert ATLAS_UI.exists()


def test_ui_html_loads_atlas_modules():
    html = load_root_ui_html_text()
    assert '<script src="/static/js/atlas_api.js"></script>' in html
    assert '<script src="/static/js/atlas_state.js"></script>' in html
    assert '<script src="/static/js/atlas_ui.js"></script>' in html


def test_atlas_compatibility_shims_remain_in_ui_html():
    html = load_root_ui_html_text()
    required = [
        "function setAtlasSubview",
        "function normalizeAtlasSubview",
        "function updateAtlasRequirementCharCount",
        "function setAtlasRequirementStatus",
        "function toggleAtlasWorkbenchCollapse",
        "function _atlasLsGet",
        "function _atlasLsSet",
        "function _atlasLsRemove",
    ]
    for token in required:
        assert token in html


def test_atlas_modules_own_extracted_responsibilities():
    api = ATLAS_API.read_text(encoding="utf-8")
    state = ATLAS_STATE.read_text(encoding="utf-8")
    ui = ATLAS_UI.read_text(encoding="utf-8")
    for token in [
        "createAutopilotPreview",
        "generateAutopilotTaskPlan",
        "prepareAutopilotExecutionPreview",
        "listAtlasRuns",
        "getRunPatches",
        "getRunReport",
        "getRunLog",
    ]:
        assert token in api
    for token in [
        "safeGet",
        "safeSet",
        "safeRemove",
        "getLastSubview",
        "setLastSubview",
        "getLastRunId",
        "setLastRunId",
        "getRequirementInput",
        "setRequirementInput",
    ]:
        assert token in state
    for token in [
        "applySubview",
        "normalizeSubview",
        "updateRequirementCharCount",
        "setRequirementStatus",
        "toggleWorkbenchCollapse",
        "updateWorkbenchSummary",
    ]:
        assert token in ui


def test_ui_html_prefers_atlas_api_for_extracted_endpoints():
    html = load_root_ui_html_text()
    assert "window.AtlasAPI.createAutopilotPreview" in html
    assert "window.AtlasAPI.generateAutopilotTaskPlan" in html
    assert "window.AtlasAPI.prepareAutopilotExecutionPreview" in html
    assert "window.AtlasAPI.listAtlasRuns" in html
    assert "window.AtlasAPI.getRunPatches" in html
    assert "window.AtlasAPI.getRunReport" in html
    assert "window.AtlasAPI.getRunLog" in html


def test_atlas_modules_keep_boundaries():
    api = ATLAS_API.read_text(encoding="utf-8")
    state = ATLAS_STATE.read_text(encoding="utf-8")
    ui = ATLAS_UI.read_text(encoding="utf-8")
    for token in ["document.getElementById", ".innerHTML", ".classList", "localStorage"]:
        assert token not in api
    for token in ["fetch(", "document.getElementById", ".innerHTML", ".classList"]:
        assert token not in state
    for token in ["fetch(", "localStorage", "AtlasAPI.", "requestJson"]:
        assert token not in ui


def test_ui_html_uses_response_helper_when_checking_dashboard_status():
    html = load_root_ui_html_text()
    if ".status === 404" in html and "patch-dashboard" in html:
        assert "getRunPatchDashboardResponse" in html
