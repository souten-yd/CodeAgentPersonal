from tests.helpers.ui_contract import WEB_JS_ROOT, load_root_ui_html_text

RUNTIME_DIAGNOSTICS = WEB_JS_ROOT / "runtime_diagnostics.js"


def read(path):
    return path.read_text(encoding="utf-8")


def test_runtime_diagnostics_module_exists_and_exports_namespace():
    source = read(RUNTIME_DIAGNOSTICS)
    assert "window.RuntimeDiagnostics" in source or "root.RuntimeDiagnostics" in source
    assert "__kasaneModules" in source
    assert "runtimeDiagnostics" in source


def test_runtime_diagnostics_contains_expected_endpoints():
    source = read(RUNTIME_DIAGNOSTICS)
    expected = [
        "/health",
        "/system/summary",
        "/models/db/status",
        "/model/status",
        "/debug/model-startup",
        "/audio/runtime/debug",
        "/nexus/web/status",
        "/nexus/jobs/active?limit=20",
    ]
    for token in expected:
        assert token in source


def test_runtime_diagnostics_has_secret_masking():
    source = read(RUNTIME_DIAGNOSTICS)
    for token in ["maskSecrets", "token", "secret", "password", "api_key", "authorization"]:
        assert token in source


def test_runtime_diagnostics_has_safe_failure_behavior():
    source = read(RUNTIME_DIAGNOSTICS)
    assert "try" in source
    assert "catch" in source
    assert "ok: false" in source or "ok:false" in source


def test_runtime_diagnostics_does_not_use_es_modules():
    source = read(RUNTIME_DIAGNOSTICS)
    assert "import " not in source
    assert "export " not in source


def test_runtime_diagnostics_does_not_heavy_probe_or_modify_runtime():
    source = read(RUNTIME_DIAGNOSTICS)
    forbidden = [
        "POST",
        "/load",
        "/unload",
        "/start",
        "/stop",
        "MediaRecorder",
        "WebSocket",
        "localStorage",
    ]
    for token in forbidden:
        assert token not in source


def test_ui_html_has_runtime_diagnostics_copy_button_and_handler():
    html = load_root_ui_html_text()
    assert "runtime-diagnostics-copy-btn" in html
    assert "runtime-diagnostics-status" in html
    assert "copyRuntimeDiagnosticsBundle" in html
