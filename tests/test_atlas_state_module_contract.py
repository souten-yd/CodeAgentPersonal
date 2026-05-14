from tests.helpers.ui_contract import WEB_JS_ROOT, load_root_ui_html_text

ATLAS_STATE = WEB_JS_ROOT / "atlas_state.js"


def read(path):
    return path.read_text(encoding="utf-8")


def test_atlas_state_module_exists_and_exports_namespace():
    assert ATLAS_STATE.exists()
    source = read(ATLAS_STATE)
    assert "window.AtlasState" in source or "root.AtlasState" in source
    assert "__kasaneModules" in source
    assert "atlasState" in source


def test_atlas_state_preserves_storage_keys():
    source = read(ATLAS_STATE)
    assert "atlas:lastSubview" in source
    assert "atlas:lastRunId" in source
    assert "atlas:requirementInput" in source


def test_atlas_state_module_has_no_api_or_ui_side_effects():
    source = read(ATLAS_STATE)
    forbidden = [
        "fetch(",
        "document.getElementById",
        ".innerHTML",
        ".classList",
        "querySelector",
    ]
    for token in forbidden:
        assert token not in source


def test_atlas_state_module_does_not_use_es_modules():
    source = read(ATLAS_STATE)
    assert "import " not in source
    assert "export " not in source


def test_ui_html_loads_atlas_modules_in_order():
    html = load_root_ui_html_text()
    api = '<script src="/static/js/atlas_api.js"></script>'
    state = '<script src="/static/js/atlas_state.js"></script>'
    ui = '<script src="/static/js/atlas_ui.js"></script>'
    assert html.index(api) < html.index(state) < html.index(ui)
