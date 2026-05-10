from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB_JS = ROOT / "web" / "js"
UI_HTML = ROOT / "ui.html"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_lumen_ui_modules_exist_and_register_globals():
    lumen_api = WEB_JS / "lumen_api.js"
    lumen_tools = WEB_JS / "lumen_tools.js"
    lumen = WEB_JS / "lumen.js"

    assert lumen_api.exists()
    assert lumen_tools.exists()
    assert lumen.exists()

    assert "window.LumenAPI" in read(lumen_api)
    assert "window.LumenTools" in read(lumen_tools)
    assert "window.Lumen" in read(lumen)


def test_ui_loads_lumen_modules_in_dependency_order():
    html = read(UI_HTML)
    scripts = [
        '<script src="/static/js/lumen_api.js"></script>',
        '<script src="/static/js/lumen_tools.js"></script>',
        '<script src="/static/js/lumen.js"></script>',
    ]
    positions = [html.index(script) for script in scripts]
    assert positions == sorted(positions)
    assert html.index('/static/js/panels.js') < positions[0]
    assert positions[-1] < html.index('/static/js/nexus.js')


def test_lumen_api_uses_primary_lumen_submit_with_jobs_fallback():
    source = read(WEB_JS / "lumen_api.js")
    assert "'/lumen/submit'" in source or '"/lumen/submit"' in source
    assert "'/jobs/submit'" in source or '"/jobs/submit"' in source
    assert "status === 404" in source
    assert "status === 405" in source
    assert "TypeError" in source


def test_lumen_logic_is_not_in_app_js():
    app_source = read(WEB_JS / "app.js")
    forbidden = [
        "submitLumenMessage",
        "pollLumenJob",
        "/lumen/submit",
        "LumenAPI",
    ]
    for token in forbidden:
        assert token not in app_source
