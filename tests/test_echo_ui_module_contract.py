from tests.helpers.ui_contract import WEB_JS_ROOT, load_root_ui_html_text

ECHO_UI = WEB_JS_ROOT / "echo_ui.js"


def read(path):
    return path.read_text(encoding="utf-8")


def test_echo_ui_module_exists_and_exports_namespace():
    source = read(ECHO_UI)
    assert "window.EchoUI" in source or "root.EchoUI" in source
    assert "__kasaneModules" in source
    assert "echoUi" in source


def test_echo_ui_module_is_ui_only_not_api_or_stream():
    source = read(ECHO_UI)
    forbidden = [
        "fetch(",
        "requestJson",
        "EchoAPI.",
        "WebSocket",
        "MediaRecorder",
        "navigator.mediaDevices",
        "getUserMedia",
        "new Audio",
        ".play(",
        ".pause(",
        "localStorage",
    ]
    for token in forbidden:
        assert token not in source


def test_echo_ui_module_allows_dom_rendering():
    source = read(ECHO_UI)
    assert "document.getElementById" in source or "byId" in source
    assert ".textContent" in source or "setText" in source
    assert ".innerHTML" in source or "setHtml" in source


def test_echo_ui_module_does_not_use_es_modules():
    source = read(ECHO_UI)
    assert "import " not in source
    assert "export " not in source


def test_ui_html_loads_echo_ui_after_echo_stream_before_echo_js():
    html = load_root_ui_html_text()
    stream = '<script src="/static/js/echo_stream.js"></script>'
    ui = '<script src="/static/js/echo_ui.js"></script>'
    echo = '<script src="/static/js/echo.js"></script>'
    assert html.index(stream) < html.index(ui) < html.index(echo)


def test_echo_ui_exposes_expected_helpers():
    source = read(ECHO_UI)
    expected = [
        "setEchoStatus",
        "setEchoConnectionState",
        "setEchoVaultInfo",
        "renderEchoVaultSessions",
        "renderStyleBertVits2Models",
    ]
    for token in expected:
        assert token in source


def test_ui_html_uses_echo_ui_for_key_rendering_paths():
    html = load_root_ui_html_text()
    expected = [
        "EchoUI.setEchoStatus",
        "EchoUI.setEchoConnectionState",
    ]
    for token in expected:
        assert token in html
