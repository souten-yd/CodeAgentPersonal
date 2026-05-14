from tests.helpers.ui_contract import WEB_JS_ROOT, load_root_ui_html_text

ECHO_STREAM = WEB_JS_ROOT / "echo_stream.js"


def read(path):
    return path.read_text(encoding="utf-8")


def test_echo_stream_module_exists_and_exports_namespace():
    source = read(ECHO_STREAM)
    assert "window.EchoStream" in source or "root.EchoStream" in source
    assert "__kasaneModules" in source
    assert "echoStream" in source


def test_echo_stream_module_is_not_api_or_ui_rendering():
    source = read(ECHO_STREAM)
    forbidden = [
        "fetch(",
        "requestJson",
        "EchoAPI.",
        "document.getElementById",
        ".innerHTML",
        ".classList",
        "localStorage",
        "/tts/synthesize",
        "/echo/sessions",
    ]
    for token in forbidden:
        assert token not in source


def test_echo_stream_module_does_not_directly_control_audio_playback():
    source = read(ECHO_STREAM)
    forbidden = [
        "new Audio",
        ".play(",
        ".pause(",
        "tts-audio",
    ]
    for token in forbidden:
        assert token not in source


def test_echo_stream_module_does_not_use_es_modules():
    source = read(ECHO_STREAM)
    assert "import " not in source
    assert "export " not in source


def test_ui_html_loads_echo_stream_after_echo_api_before_echo_ui():
    html = load_root_ui_html_text()
    api = '<script src="/static/js/echo_api.js"></script>'
    stream = '<script src="/static/js/echo_stream.js"></script>'
    ui = '<script src="/static/js/echo_ui.js"></script>'
    assert html.index(api) < html.index(stream) < html.index(ui)


def test_echo_stream_exposes_state_helpers():
    source = read(ECHO_STREAM)
    expected = [
        "getState",
        "setRecording",
        "setStoppingOrSaving",
        "setConnectionState",
        "setPlaybackState",
        "setMediaRecorder",
        "setMediaStream",
        "setWebSocket",
        "setLastError",
    ]
    for token in expected:
        assert token in source


def test_ui_html_uses_echo_stream_for_key_state_transitions():
    html = load_root_ui_html_text()
    expected = [
        "EchoStream.setRecording",
        "EchoStream.setConnectionState",
        "EchoStream.setPlaybackState",
    ]
    for token in expected:
        assert token in html
