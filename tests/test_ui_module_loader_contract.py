from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULES = [
    "atlas_api.js",
    "atlas_state.js",
    "atlas_ui.js",
    "echo_api.js",
    "echo_stream.js",
    "echo_ui.js",
    "runtime_diagnostics.js",
]


def test_ui_html_loads_new_ui_modules_in_order():
    html = (ROOT / "ui.html").read_text(encoding="utf-8")
    positions = []
    for module in MODULES:
        script_path = f"/static/js/{module}"
        assert script_path in html
        positions.append(html.index(script_path))
    assert positions == sorted(positions)


def test_new_ui_module_files_exist():
    for module in MODULES:
        assert (ROOT / "web" / "js" / module).exists()


def test_new_ui_modules_do_not_use_es_module_syntax():
    for module in MODULES:
        text = (ROOT / "web" / "js" / module).read_text(encoding="utf-8")
        assert "export " not in text
        assert "import " not in text
