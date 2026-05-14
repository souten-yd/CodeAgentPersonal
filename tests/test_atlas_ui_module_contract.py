from tests.helpers.ui_contract import WEB_JS_ROOT, load_root_ui_html_text

ATLAS_UI = WEB_JS_ROOT / "atlas_ui.js"


def read(path):
    return path.read_text(encoding="utf-8")


def test_atlas_ui_module_exists_and_exports_namespace():
    source = read(ATLAS_UI)
    assert "window.AtlasUI" in source or "root.AtlasUI" in source
    assert "__kasaneModules" in source
    assert "atlasUi" in source


def test_atlas_ui_module_allows_dom_but_not_api_or_storage():
    source = read(ATLAS_UI)
    assert "document.getElementById" in source or "byId" in source
    forbidden = ["fetch(", "localStorage", "requestJson", "AtlasAPI."]
    for token in forbidden:
        assert token not in source


def test_atlas_ui_module_does_not_use_es_modules():
    source = read(ATLAS_UI)
    assert "import " not in source
    assert "export " not in source


def test_atlas_ui_module_does_not_weaken_execution_gates():
    source = read(ATLAS_UI)
    forbidden = ["autoApprove", "autoExecute", "autoApply", "approvePlan(", "applyPatch("]
    for token in forbidden:
        assert token not in source


def test_ui_html_loads_atlas_modules_in_order():
    html = load_root_ui_html_text()
    api = '<script src="/static/js/atlas_api.js"></script>'
    state = '<script src="/static/js/atlas_state.js"></script>'
    ui = '<script src="/static/js/atlas_ui.js"></script>'
    assert html.index(api) < html.index(state) < html.index(ui)


def test_atlas_compatibility_functions_remain_available():
    combined = load_root_ui_html_text() + "\n" + read(ATLAS_UI)
    required_tokens = [
        "setAtlasSubview",
        "normalizeAtlasSubview",
        "updateAtlasRequirementCharCount",
        "setAtlasRequirementStatus",
        "toggleAtlasWorkbenchCollapse",
    ]
    for token in required_tokens:
        assert token in combined
