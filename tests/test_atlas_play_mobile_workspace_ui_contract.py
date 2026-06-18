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
    assert "atlas_play_workspace.js?v=atlas-play-workspace-2" in UI


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


def test_play_workspace_stop_does_not_refetch_stopped_preview_or_reload_iframe() -> None:
    stop_fn = PLAY_JS.index("async function stopSession()")
    stop_poll = PLAY_JS.index("stopPolling();", stop_fn)
    clear = PLAY_JS.index("clearPreviewFrame('Stopping preview')", stop_fn)
    stop_api = PLAY_JS.index("stopPlaySession", stop_fn)
    assert stop_poll < stop_api
    assert clear < stop_api
    assert "function replacePreviewFrame" in PLAY_JS
    assert "contentWindow?.stop?.()" in PLAY_JS
    assert "clearPreviewFrame('Preview stopped')" in PLAY_JS
    assert "stopPolling();" in PLAY_JS
    assert "dom.frame.dataset.atlasPreviewUrl !== url" in PLAY_JS
    assert "session.state === 'stopped' ? 'Preview stopped'" in PLAY_JS


def test_capsule_builder_treats_user_stopped_preview_as_normal_build_candidate() -> None:
    assert "function isCapsuleBuildEligible" in PLAY_JS
    assert "session.stop_reason === 'user_stop'" in PLAY_JS
    assert "project_id: sessionProjectId(session)" in PLAY_JS
    assert "profileFromSession(session)" in PLAY_JS
    assert "session.launch_kind === 'static_web' ? 'index.html'" in PLAY_JS
    assert "function safePackageId" in PLAY_JS
    assert "package_id: packageId" in PLAY_JS
    assert "package_id: name || undefined" not in PLAY_JS


def test_capsule_builder_surfaces_api_error_reason_not_generic_error() -> None:
    assert "function apiErrorReason" in PLAY_JS
    assert "resp?.reason" in PLAY_JS
    assert "resp?.error" in PLAY_JS
    assert "Build failed: ${apiErrorReason(resp, 'error')}" in PLAY_JS
    assert "resp?.data?.error || resp?.code || 'error'" not in PLAY_JS


def test_mobile_css_compacts_header_and_uses_fullscreen_sheet() -> None:
    assert "@media(max-width:720px)" in CSS
    assert ".atlas-play-sheet{width:100vw;height:100dvh" in CSS
    assert ".atlas-claude-capsule-btn::after" in CSS
    assert ".atlas-claude-play-btn::after" in CSS
    assert ".atlas-claude-plan-history-btn::after" in CSS
