from tests.helpers.ui_contract import WEB_JS_ROOT, load_root_ui_html_text

ECHO_API = WEB_JS_ROOT / "echo_api.js"


def read(path):
    return path.read_text(encoding="utf-8")


def test_echo_api_module_exists_and_exports_namespace():
    source = read(ECHO_API)
    assert "window.EchoAPI" in source or "root.EchoAPI" in source
    assert "__kasaneModules" in source
    assert "echoApi" in source


def test_echo_api_module_is_api_only():
    source = read(ECHO_API)
    forbidden = [
        "document.getElementById",
        ".innerHTML",
        ".classList",
        "localStorage",
        "querySelector",
        "WebSocket",
        "MediaRecorder",
        "Audio(",
        "audio.play",
        "audio.pause",
    ]
    for token in forbidden:
        assert token not in source


def test_echo_api_module_does_not_use_es_modules():
    source = read(ECHO_API)
    assert "import " not in source
    assert "export " not in source


def test_ui_html_loads_echo_api_before_echo_stream_echo_ui_and_echo_js():
    html = load_root_ui_html_text()
    api = '<script src="/static/js/echo_api.js"></script>'
    stream = '<script src="/static/js/echo_stream.js"></script>'
    ui = '<script src="/static/js/echo_ui.js"></script>'
    echo = '<script src="/static/js/echo.js"></script>'
    assert api in html
    assert stream in html
    assert ui in html
    assert echo in html
    assert html.index(api) < html.index(stream) < html.index(ui) < html.index(echo)


def test_echo_api_module_has_fetch_with_timeout_fallback():
    source = read(ECHO_API)
    assert "fetchWithTimeout" in source
    assert "root.fetch" in source


def test_echo_api_module_contains_known_echo_endpoints():
    source = read(ECHO_API)
    html = load_root_ui_html_text()
    expected = [
        "/voice/status",
        "/asr/config",
        "/audio/runtime/debug",
        "/tts/synthesize",
        "/tts/synthesize-batch",
        "/api/tts/style-bert-vits2/models",
        "/api/tts/style-bert-vits2/preview-normalization",
        "/echo/sessions",
        "/echo/save-status",
    ]
    for token in expected:
        if token in html:
            assert token in source
