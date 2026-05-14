from tests.helpers.ui_contract import WEB_JS_ROOT, load_root_ui_html_text

ATLAS_API = WEB_JS_ROOT / "atlas_api.js"


def read(path):
    return path.read_text(encoding="utf-8")


def test_atlas_api_module_exists_and_exports_namespace():
    assert ATLAS_API.exists()
    source = read(ATLAS_API)
    assert "window.AtlasAPI" in source or "root.AtlasAPI" in source
    assert "__kasaneModules" in source
    assert "atlasApi" in source


def test_atlas_api_module_is_api_only():
    source = read(ATLAS_API)
    forbidden = [
        "document.getElementById",
        ".innerHTML",
        ".classList",
        "localStorage",
        "querySelector",
    ]
    for token in forbidden:
        assert token not in source


def test_atlas_api_module_does_not_use_es_modules():
    source = read(ATLAS_API)
    assert "import " not in source
    assert "export " not in source


def test_ui_html_loads_atlas_api_before_atlas_state_and_ui():
    html = load_root_ui_html_text()
    api = '<script src="/static/js/atlas_api.js"></script>'
    state = '<script src="/static/js/atlas_state.js"></script>'
    ui = '<script src="/static/js/atlas_ui.js"></script>'
    assert api in html
    assert state in html
    assert ui in html
    assert html.index(api) < html.index(state) < html.index(ui)


def test_atlas_api_module_has_fetch_with_timeout_fallback():
    source = read(ATLAS_API)
    assert "fetchWithTimeout" in source
    assert "root.fetch" in source
