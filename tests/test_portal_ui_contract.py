from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UI = (ROOT / "ui.html").read_text(encoding="utf-8")
PORTAL_JS = (ROOT / "web" / "js" / "portal.js").read_text(encoding="utf-8")
API_JS = (ROOT / "web" / "js" / "atlas_pipeline_api.js").read_text(encoding="utf-8")


def test_portal_run_polling_does_not_reload_preview_iframe() -> None:
    assert "function replaceRunFrame" in PORTAL_JS
    assert "contentWindow?.stop?.()" in PORTAL_JS
    assert "dataset.portalPreviewUrl !== url" in PORTAL_JS
    assert "frame.src = url" in PORTAL_JS
    assert "dataset.bound" not in PORTAL_JS
    assert "delete frame.dataset" not in PORTAL_JS


def test_portal_stop_clears_preview_before_backend_stop() -> None:
    stop_fn = PORTAL_JS.index("async function stopRun()")
    stop_poll = PORTAL_JS.index("stopPolling();", stop_fn)
    clear_frame = PORTAL_JS.index("replaceRunFrame('about:blank')", stop_fn)
    stop_api = PORTAL_JS.index("stopPortalRun", stop_fn)

    assert stop_poll < stop_api
    assert clear_frame < stop_api


def test_portal_package_display_edit_is_wired_without_mutating_capsule_manifest() -> None:
    assert "function packageDisplay" in PORTAL_JS
    assert 'data-portal-act="edit-display"' in PORTAL_JS
    assert "async function editDisplay" in PORTAL_JS
    assert "updatePortalPackageDisplay" in PORTAL_JS
    assert "/display" in API_JS


def test_portal_script_cache_keys_are_bumped() -> None:
    assert "atlas_pipeline_api.js?v=atlas-ui-fix-14" in UI
    assert "portal.js?v=portal-2" in UI
