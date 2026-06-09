from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_JS = (ROOT / "web/js/app.js").read_text(encoding="utf-8")
API_JS = (ROOT / "web/js/atlas_pipeline_api.js").read_text(encoding="utf-8")
PLAY_JS = (ROOT / "web/js/atlas_play_workspace.js").read_text(encoding="utf-8")
CSS = (ROOT / "web/css/app.css").read_text(encoding="utf-8")
UI = (ROOT / "ui.html").read_text(encoding="utf-8")


def test_header_order_is_capsule_play_plan_history() -> None:
    capsule = APP_JS.index("actions.appendChild(capsuleBtn)")
    play = APP_JS.index("actions.appendChild(playBtn)")
    history = APP_JS.index("actions.appendChild(historyBtn)")

    assert capsule < play < history
    assert "aria-label', 'Capsule'" in APP_JS
    assert "aria-label', 'Play'" in APP_JS


def test_play_workspace_script_loads_after_api_before_dashboard() -> None:
    api = UI.index("atlas_pipeline_api.js")
    play = UI.index("atlas_play_workspace.js")
    dashboard = UI.index("atlas_dashboard.js")

    assert api < play < dashboard


def test_workspace_has_required_tabs_and_controls_without_host_shell() -> None:
    for token in [
        'data-tab="preview"',
        'data-tab="files"',
        'data-tab="logs"',
        'data-tab="console"',
        'data-action="run"',
        'data-action="restart"',
        'data-action="stop"',
        'data-action="reload"',
        'data-action="external"',
        'data-action="fullscreen"',
        'data-action="close"',
        'data-action="repair-handoff"',
        "Read-only session output",
    ]:
        assert token in PLAY_JS

    lowered = PLAY_JS.lower()
    assert "host shell" not in lowered
    assert "general shell" not in lowered
    assert "data-action=\"stdin\"" not in lowered


def test_play_workspace_uses_pr_ppc_api_surface() -> None:
    for token in [
        "resolvePlayEnvironment",
        "startPlaySession",
        "getPlaySession",
        "stopPlaySession",
        "restartPlaySession",
        "listPlayWorkspaceFiles",
        "readPlayWorkspaceFile",
        "writePlayWorkspaceFile",
    ]:
        assert token in API_JS

    assert "/api/atlas/play/workspace/files/write" in API_JS
    assert "/api/atlas/play/sessions/start" in API_JS


def test_mobile_css_compacts_header_and_uses_fullscreen_sheet() -> None:
    assert "@media(max-width:720px)" in CSS
    assert ".atlas-play-sheet{width:100vw;height:100dvh" in CSS
    assert ".atlas-claude-capsule-btn::after" in CSS
    assert ".atlas-claude-play-btn::after" in CSS
    assert ".atlas-claude-plan-history-btn::after" in CSS
