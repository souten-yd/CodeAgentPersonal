from tests.helpers.ui_contract import WEB_JS_ROOT, load_root_ui_html_text

MODULES = [
    ("atlas_api.js", "/static/js/atlas_api.js"),
    ("atlas_state.js", "/static/js/atlas_state.js"),
    ("atlas_ui.js", "/static/js/atlas_ui.js"),
    ("echo_api.js", "/static/js/echo_api.js"),
    ("echo_stream.js", "/static/js/echo_stream.js"),
    ("echo_ui.js", "/static/js/echo_ui.js"),
    ("runtime_diagnostics.js", "/static/js/runtime_diagnostics.js"),
]


def test_new_ui_module_files_exist():
    for filename, _src in MODULES:
        assert (WEB_JS_ROOT / filename).exists()


def test_ui_html_loads_new_ui_modules_from_static_js():
    html = load_root_ui_html_text()
    for _filename, src in MODULES:
        assert f'<script src="{src}"></script>' in html


def test_new_ui_modules_are_loaded_in_dependency_order():
    html = load_root_ui_html_text()
    ordered_srcs = [
        "/static/js/atlas_api.js",
        "/static/js/atlas_state.js",
        "/static/js/atlas_ui.js",
        "/static/js/echo_api.js",
        "/static/js/echo_stream.js",
        "/static/js/echo_ui.js",
        "/static/js/runtime_diagnostics.js",
    ]
    positions = [html.index(f'<script src="{src}"></script>') for src in ordered_srcs]
    assert positions == sorted(positions)


def test_new_ui_modules_do_not_use_es_module_syntax():
    for filename, _src in MODULES:
        source = (WEB_JS_ROOT / filename).read_text(encoding="utf-8")
        assert "export " not in source
        assert "import " not in source


def test_new_ui_modules_register_safety_registry_only():
    expected = {
        "atlas_api.js": "atlasApi",
        "atlas_state.js": "atlasState",
        "atlas_ui.js": "atlasUi",
        "echo_api.js": "echoApi",
        "echo_stream.js": "echoStream",
        "echo_ui.js": "echoUi",
        "runtime_diagnostics.js": "runtimeDiagnostics",
    }
    for filename, key in expected.items():
        source = (WEB_JS_ROOT / filename).read_text(encoding="utf-8")
        assert "__kasaneModules" in source
        assert key in source
        assert "fetch(" not in source
        assert "localStorage" not in source
        assert "document.getElementById" not in source
