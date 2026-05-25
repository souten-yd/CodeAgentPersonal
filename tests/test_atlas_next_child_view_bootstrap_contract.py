from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_main_shell_loads_child_view_bootstrap_without_default_redirect():
    ui = (ROOT / "ui.html").read_text(encoding="utf-8")
    bootstrap = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    main = (ROOT / "main.py").read_text(encoding="utf-8")

    assert '<script src="/static/js/app.js"></script>' in ui
    assert "KASANE_ATLAS_NEXT_CHILD_VIEW" in bootstrap
    assert "atlas-next-child-frame" in bootstrap
    assert "root.dataset.atlasNextChildView = 'enabled'" in bootstrap
    assert "frame.setAttribute('src', route)" in bootstrap
    assert "const route = '/atlas-next/'" in bootstrap
    assert 'location.href = "/atlas-next"' not in ui
    assert 'location.href = "/atlas-next"' not in bootstrap
    assert 'RedirectResponse("/atlas-next")' not in main


def test_child_view_hides_legacy_atlas_surfaces_but_keeps_root_shell():
    bootstrap = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    main = (ROOT / "main.py").read_text(encoding="utf-8")

    hidden_surfaces = [
        "#atlas-workflow-shell",
        ".atlas-goal-card",
        "#atlas-status-grid",
        "#atlas-details-drawer",
        ".atlas-legacy-compat",
    ]
    for selector in hidden_surfaces:
        assert selector in bootstrap
    assert "return serve_existing_ui_index()" in main
    assert "ATLAS_NEXT_DEFAULT_ENABLED = False" in main
