from __future__ import annotations

import sys
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from agent.atlas_playwright_smoke_verifier import (
    AtlasPlaywrightSmokeVerifier,
    _PLAYWRIGHT_AVAILABLE,
    _sample_interval_ms,
    _sample_max_wait_ms,
    _serve_artifact_dir,
    _is_browser_not_installed_error,
)

_VFY = AtlasPlaywrightSmokeVerifier()

_ANIM_HTML = """\
<!doctype html><html><body>
<canvas id="c"></canvas>
<script>
  let t=0;
  function loop(){
    document.getElementById('c').style.transform='translateY('+Math.sin(t)*50+'px)';
    document.getElementById('c').style.color='hsl('+(t*5%360)+',100%,50%)';
    t++;
    requestAnimationFrame(loop);
  }
  requestAnimationFrame(loop);
</script>
</body></html>
"""

_STATIC_HTML = """\
<!doctype html><html><body><h1>Hello World</h1></body></html>
"""

_JS_ERROR_HTML = """\
<!doctype html><html><body>
<script>undefinedFunction();</script>
</body></html>
"""

_MISSING_TEXT_HTML = """\
<!doctype html><html><body><p>other text</p></body></html>
"""


def test_playwright_unavailable_returns_skipped(tmp_path):
    """If playwright is not installed, result is browser_smoke_skipped."""
    f = tmp_path / 'index.html'
    f.write_text(_STATIC_HTML, encoding='utf-8')
    with patch('agent.atlas_playwright_smoke_verifier._PLAYWRIGHT_AVAILABLE', False):
        vfy = AtlasPlaywrightSmokeVerifier()
        result = vfy.verify(f, task_description='animate')
    assert result['status'] == 'browser_smoke_skipped'
    assert result['reason'] == 'playwright_not_installed'


def test_browser_not_installed_error_is_detected():
    # The python package is importable but the browser binary was never downloaded.
    # Playwright's real message on a fresh machine (stable across platforms).
    msg = (
        "BrowserType.launch: Executable doesn't exist at "
        "C:\\Users\\x\\AppData\\Local\\ms-playwright\\chromium-1208\\chrome-win\\chrome.exe\n"
        "Please run the following command to download new browsers:\n"
        "    playwright install"
    )
    assert _is_browser_not_installed_error(Exception(msg)) is True
    assert _is_browser_not_installed_error(Exception("Browser executable was not found. Run playwright install")) is True


def test_genuine_runtime_error_is_not_browser_not_installed():
    assert _is_browser_not_installed_error(Exception("Timeout 10000ms exceeded")) is False
    assert _is_browser_not_installed_error(Exception("net::ERR_CONNECTION_REFUSED")) is False


def test_browser_not_installed_maps_to_skipped(tmp_path):
    """A missing browser binary surfaces as a clear, install-guided skip — not a
    visual *failure* that would be mistaken for a product defect."""
    f = tmp_path / 'index.html'
    f.write_text(_STATIC_HTML, encoding='utf-8')
    vfy = AtlasPlaywrightSmokeVerifier()
    boom = Exception("BrowserType.launch: Executable doesn't exist ... playwright install")
    with patch('agent.atlas_playwright_smoke_verifier._PLAYWRIGHT_AVAILABLE', True), \
            patch('agent.atlas_playwright_smoke_verifier.sync_playwright', side_effect=boom, create=True):
        result = vfy.verify(f, task_description='animate color')
    assert result['status'] == 'browser_smoke_skipped'
    assert result['reason'].startswith('playwright_browser_not_installed')


def test_playwright_runtime_error_reason_includes_exception_type(tmp_path):
    f = tmp_path / 'index.html'
    f.write_text(_STATIC_HTML, encoding='utf-8')
    vfy = AtlasPlaywrightSmokeVerifier()
    with patch('agent.atlas_playwright_smoke_verifier._PLAYWRIGHT_AVAILABLE', True), \
            patch('agent.atlas_playwright_smoke_verifier.sync_playwright', side_effect=RuntimeError(), create=True):
        result = vfy.verify(f, task_description='animate color')
    assert result['status'] == 'browser_smoke_failed'
    assert result['reason'] == 'playwright_error: RuntimeError'


def test_sync_playwright_empty_launch_exception_has_nonempty_reason(tmp_path):
    f = tmp_path / 'index.html'
    f.write_text(_STATIC_HTML, encoding='utf-8')
    vfy = AtlasPlaywrightSmokeVerifier()
    with patch('agent.atlas_playwright_smoke_verifier._PLAYWRIGHT_AVAILABLE', True), \
            patch('agent.atlas_playwright_smoke_verifier.sync_playwright', side_effect=Exception(), create=True):
        result = vfy.verify(f, task_description='animate color')
    assert result['status'] == 'browser_smoke_failed'
    assert result['reason'] == 'playwright_error: Exception'


def test_smoke_ui_launch_browser_reports_missing_browser_and_typed_errors():
    smoke = _load_smoke_ui_module()

    async def run_missing():
        return await smoke.launch_browser_with_retry(
            _FakePlaywright(Exception("BrowserType.launch: executable was not found; run playwright install")),
            attempts=1,
        )

    async def run_empty():
        return await smoke.launch_browser_with_retry(_FakePlaywright(RuntimeError()), attempts=1)

    import asyncio
    with pytest.raises(AssertionError, match="playwright_browser_not_installed"):
        asyncio.run(run_missing())
    with pytest.raises(AssertionError, match="playwright_error: RuntimeError"):
        asyncio.run(run_empty())


def _load_smoke_ui_module():
    scripts_dir = Path(__file__).resolve().parents[1] / "scripts"
    sys.path.insert(0, str(scripts_dir))
    try:
        spec = importlib.util.spec_from_file_location("smoke_ui_modes_playwright_for_tests", scripts_dir / "smoke_ui_modes_playwright.py")
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        try:
            sys.path.remove(str(scripts_dir))
        except ValueError:
            pass


class _FakeChromium:
    def __init__(self, exc):
        self.exc = exc

    async def launch(self):
        raise self.exc


class _FakePlaywright:
    def __init__(self, exc):
        self.chromium = _FakeChromium(exc)


def test_missing_html_file_returns_failed(tmp_path):
    result = _VFY.verify(tmp_path / 'nonexistent.html', task_description='animate')
    assert result['status'] == 'browser_smoke_failed'
    assert result['reason'] == 'html_file_missing'


_pw_mark = pytest.mark.skipif(not _PLAYWRIGHT_AVAILABLE, reason='playwright not installed')


@_pw_mark
def test_console_reference_error_fails(tmp_path):
    f = tmp_path / 'index.html'
    f.write_text(_JS_ERROR_HTML, encoding='utf-8')
    result = _VFY.verify(f, task_description='show page')
    assert result['status'] == 'browser_smoke_failed'
    assert result['reason'] == 'js_error'


@_pw_mark
def test_missing_expected_text_fails(tmp_path):
    f = tmp_path / 'index.html'
    f.write_text(_MISSING_TEXT_HTML, encoding='utf-8')
    result = _VFY.verify(f, task_description='show page', expected_text='EXPECTED_TEXT_NOT_PRESENT')
    assert result['status'] == 'browser_smoke_failed'
    assert result['reason'] == 'expected_text_missing'


@_pw_mark
def test_static_html_no_animation_passes_for_non_animation_task(tmp_path):
    f = tmp_path / 'index.html'
    f.write_text(_STATIC_HTML, encoding='utf-8')
    result = _VFY.verify(f, task_description='show a static page')
    assert result['status'] == 'browser_smoke_passed'


@_pw_mark
def test_static_html_fails_for_animation_task(tmp_path):
    """Static HTML with no animation fails for animation task (no style changes detected)."""
    f = tmp_path / 'index.html'
    f.write_text(_STATIC_HTML, encoding='utf-8')
    result = _VFY.verify(f, task_description='animate color wave')
    assert result['status'] == 'browser_smoke_failed'
    assert result['reason'] == 'animation_not_detected'


@_pw_mark
def test_animation_html_passes_for_animation_task(tmp_path):
    """HTML with requestAnimationFrame changing transform/color passes."""
    f = tmp_path / 'index.html'
    f.write_text(_ANIM_HTML, encoding='utf-8')
    result = _VFY.verify(f, task_description='animate wave')
    assert result['status'] == 'browser_smoke_passed'

class _FakeCanvasPage:
    def __init__(self, values):
        self.values = list(values)
    def evaluate(self, _script):
        if len(self.values) > 1:
            return self.values.pop(0)
        return self.values[0]


def test_canvas_pixel_change_detects_animation_without_style_change():
    page = _FakeCanvasPage([
        {"present": True, "samples": [{"pixels": "0,0,0,255", "dataHash": "a"}]},
        {"present": True, "samples": [{"pixels": "255,0,0,255", "dataHash": "b"}]},
    ])
    result = _VFY._check_canvas_changes_over_time(page)
    assert result["changed"] is True


def test_static_canvas_no_frame_changes_reports_not_detected(monkeypatch):
    monkeypatch.setenv("ATLAS_VISUAL_SAMPLE_MAX_MS", "1")
    monkeypatch.setenv("ATLAS_VISUAL_SAMPLE_INTERVAL_MS", "1")
    sample = {"present": True, "samples": [{"pixels": "0,0,0,255", "dataHash": "a"}]}
    page = _FakeCanvasPage([sample, sample])
    result = _VFY._check_canvas_changes_over_time(page)
    assert result["changed"] is False
    assert result["present"] is True


def test_sampling_waits_are_env_configurable(monkeypatch):
    monkeypatch.setenv("ATLAS_VISUAL_SAMPLE_MAX_MS", "7")
    monkeypatch.setenv("ATLAS_VISUAL_SAMPLE_INTERVAL_MS", "2")
    assert _sample_max_wait_ms() == 7
    assert _sample_interval_ms() == 2
    monkeypatch.setenv("ATLAS_VISUAL_SAMPLE_MAX_MS", "not-int")
    assert _sample_max_wait_ms() > 7


def test_canvas_inaccessible_reports_explicit_warning(monkeypatch):
    monkeypatch.setenv("ATLAS_VISUAL_SAMPLE_MAX_MS", "1")
    monkeypatch.setenv("ATLAS_VISUAL_SAMPLE_INTERVAL_MS", "1")

    class _ThrowingPage:
        def evaluate(self, _script):
            raise RuntimeError("canvas tainted")

    result = _VFY._check_canvas_changes_over_time(_ThrowingPage())
    assert result["warning"] == "canvas_inaccessible"
    assert "canvas tainted" in result["errors"][0]


def test_serve_artifact_bind_failure_records_diagnostic(tmp_path):
    diagnostics = []
    with patch("agent.atlas_playwright_smoke_verifier.ThreadingHTTPServer", side_effect=OSError("address unavailable")):
        with _serve_artifact_dir(tmp_path, diagnostics) as base_url:
            assert base_url is None
    assert diagnostics
    assert diagnostics[0].startswith("serve_artifact_bind_failed:OSError")


def test_non_module_script_with_exports_diagnoses_module_script_mismatch(tmp_path):
    (tmp_path / 'js').mkdir()
    (tmp_path / 'index.html').write_text('<!doctype html><script src="js/GameEngine.js"></script>', encoding='utf-8')
    (tmp_path / 'js' / 'GameEngine.js').write_text('export class GameEngine {}', encoding='utf-8')
    diagnostic = _VFY._diagnose_js_wiring(tmp_path / 'index.html', ["SyntaxError: Unexpected token 'export'"])
    assert diagnostic == 'module_script_mismatch'
    assert _VFY._js_error_reason(diagnostic) == 'js_error:module_script_mismatch'


def test_missing_module_import_target_diagnosed(tmp_path):
    (tmp_path / 'js').mkdir()
    (tmp_path / 'index.html').write_text('<!doctype html><script type="module" src="js/GameEngine.js"></script>', encoding='utf-8')
    (tmp_path / 'js' / 'GameEngine.js').write_text('import { Player } from "./Player.js";\nnew Player();', encoding='utf-8')
    diagnostic = _VFY._diagnose_js_wiring(tmp_path / 'index.html', ['TypeError: Failed to fetch dynamically imported module'])
    assert diagnostic == 'missing_import_target'


def test_import_path_case_mismatch_diagnosed(tmp_path):
    (tmp_path / 'js').mkdir()
    (tmp_path / 'index.html').write_text('<!doctype html><script type="module" src="js/GameEngine.js"></script>', encoding='utf-8')
    (tmp_path / 'js' / 'GameEngine.js').write_text('import { Player } from "./player.js";\nnew Player();', encoding='utf-8')
    (tmp_path / 'js' / 'Player.js').write_text('export class Player {}', encoding='utf-8')
    diagnostic = _VFY._diagnose_js_wiring(tmp_path / 'index.html', ['Failed to resolve module specifier'])
    assert diagnostic == 'import_path_case_mismatch'


def test_planned_but_not_yet_created_script_is_tolerated(tmp_path):
    # Incremental build: step_1 writes index.html referencing script.js, which a LATER step creates.
    (tmp_path / 'index.html').write_text('<!doctype html><script src="script.js"></script>', encoding='utf-8')
    # script.js does not exist yet, but it is in the plan -> not a missing_script_src failure.
    assert _VFY._missing_script_src(tmp_path / 'index.html', ['script.js'], {'script.js'}) is False
    assert _VFY._diagnose_js_wiring(tmp_path / 'index.html', [], {'script.js', 'styles.css'}) == ''


def test_unplanned_missing_script_still_fails(tmp_path):
    # A reference no plan step produces (typo: game.js when the plan creates script.js) still fails.
    (tmp_path / 'index.html').write_text('<!doctype html><script src="game.js"></script>', encoding='utf-8')
    assert _VFY._missing_script_src(tmp_path / 'index.html', ['game.js'], {'script.js'}) is True
    assert _VFY._diagnose_js_wiring(tmp_path / 'index.html', [], {'script.js'}) == 'missing_script_src'


def test_canvas_grid_hash_detects_motion_that_fixed_points_miss():
    page = _FakeCanvasPage([
        {"present": True, "samples": [{"pixels": "same-five-fixed-points", "dataHash": "same", "gridHash": "123"}]},
        {"present": True, "samples": [{"pixels": "same-five-fixed-points", "dataHash": "same", "gridHash": "456"}]},
    ])
    result = _VFY._check_canvas_changes_over_time(page)
    assert result["changed"] is True


def test_favicon_resource_404_is_not_hard_js_failure(tmp_path):
    html = tmp_path / 'index.html'
    html.write_text('<!doctype html><link rel="icon" href="favicon.ico"><script src="js/GameEngine.js"></script>', encoding='utf-8')
    (tmp_path / 'js').mkdir()
    (tmp_path / 'js' / 'GameEngine.js').write_text('window.gameReady = true;', encoding='utf-8')
    errors = ['Failed to load resource: net::ERR_FILE_NOT_FOUND file:///tmp/game/favicon.ico']
    assert _VFY._hard_js_errors(errors, html) == []
    assert _VFY._diagnose_js_wiring(html, errors) == ''


def test_missing_js_entry_script_is_hard_failure(tmp_path):
    html = tmp_path / 'index.html'
    html.write_text('<!doctype html><script src="js/MissingGame.js"></script>', encoding='utf-8')
    diagnostic = _VFY._diagnose_js_wiring(html, ['Failed to load resource: net::ERR_FILE_NOT_FOUND js/MissingGame.js'])
    assert diagnostic == 'missing_script_src'
    assert _VFY._js_error_reason(diagnostic) == 'js_error:missing_script_src'
