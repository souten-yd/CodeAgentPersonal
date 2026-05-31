from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from agent.atlas_playwright_smoke_verifier import AtlasPlaywrightSmokeVerifier, _PLAYWRIGHT_AVAILABLE

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


def test_missing_html_file_returns_failed(tmp_path):
    result = _VFY.verify(tmp_path / 'nonexistent.html', task_description='animate')
    assert result['status'] == 'browser_smoke_failed'
    assert result['reason'] == 'html_file_missing'


# The following tests only run if Playwright is actually available in the environment.
import pytest

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
    assert result['reason'] == 'animation_not_detected_no_style_change'


@_pw_mark
def test_animation_html_passes_for_animation_task(tmp_path):
    """HTML with requestAnimationFrame changing transform/color passes."""
    f = tmp_path / 'index.html'
    f.write_text(_ANIM_HTML, encoding='utf-8')
    result = _VFY.verify(f, task_description='animate wave')
    assert result['status'] == 'browser_smoke_passed'
