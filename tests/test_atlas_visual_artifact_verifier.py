from __future__ import annotations

from pathlib import Path

from agent.atlas_visual_artifact_verifier import AtlasVisualArtifactVerifier

_VFY = AtlasVisualArtifactVerifier()

_VALID_ANIMATION_HTML = """\
<!doctype html>
<html>
<head>
<style>
  :root { --hue: 0; }
  @keyframes colorShift { from { background-color: hsl(0,100%,50%); } to { background-color: hsl(360,100%,50%); } }
  canvas { transform: translateY(0); }
</style>
</head>
<body>
<canvas id="c"></canvas>
<script>
  const amplitude = 50;
  const frequency = 0.02;
  let phase = 0;
  function loop(t) {
    const y = amplitude * Math.sin(frequency * t + phase);
    document.getElementById('c').style.transform = 'translateY(' + y + 'px)';
    document.getElementById('c').style.color = 'hsl(' + (phase * 10 % 360) + ',100%,50%)';
    phase += 0.01;
    requestAnimationFrame(loop);
  }
  requestAnimationFrame(loop);
</script>
</body>
</html>
"""

_STATIC_HTML = """\
<!doctype html><html><body><h1>Hello World</h1></body></html>
"""

_HTML_WITH_TEXT_NO_COLOR = """\
<!doctype html>
<html><body>
<h1>Demo</h1>
<script>requestAnimationFrame(function f(){requestAnimationFrame(f);});</script>
</body></html>
"""

_HTML_WITH_COLOR_NO_MOTION = """\
<!doctype html>
<html><body>
<div style="color: hsl(0,100%,50%)">Hello</div>
<script>requestAnimationFrame(function f(){document.body.style.color='rgb(255,0,0)';requestAnimationFrame(f);});</script>
</body></html>
"""

_RAINBOW_NAMED_COLORS_HTML = """\
<!doctype html><html><head><style>
.hello-world { animation: rainbow 3s infinite; }
@keyframes rainbow { 0%{color:red} 20%{color:orange} 40%{color:yellow}
 60%{color:green} 80%{color:blue} 100%{color:purple} }
</style></head><body><div class="hello-world">Hello World</div></body></html>
"""


def test_missing_html_file_fails(tmp_path):
    result = _VFY.verify_static(tmp_path / 'nonexistent.html', task_description='animation')
    assert result['status'] == 'failed'
    assert 'html_file_missing' in result['missing']


def test_html_file_existence_alone_fails_for_animation_task(tmp_path):
    f = tmp_path / 'index.html'
    f.write_text(_STATIC_HTML, encoding='utf-8')
    result = _VFY.verify_static(f, task_description='animate color wave')
    assert result['status'] == 'failed'
    assert len(result['missing']) > 0


def test_html_with_text_but_no_color_mutation_fails_animation_task(tmp_path):
    f = tmp_path / 'index.html'
    f.write_text(_HTML_WITH_TEXT_NO_COLOR, encoding='utf-8')
    result = _VFY.verify_static(f, task_description='animate colors')
    assert result['status'] == 'failed'
    assert 'color_mutation_signal' in result['missing']


def test_html_with_color_but_no_motion_fails_animation_task(tmp_path):
    f = tmp_path / 'index.html'
    f.write_text(_HTML_WITH_COLOR_NO_MOTION, encoding='utf-8')
    result = _VFY.verify_static(f, task_description='animate movement')
    assert result['status'] == 'failed'
    assert 'motion_signal' in result['missing']


def test_named_color_keyframes_satisfy_color_mutation(tmp_path):
    f = tmp_path / 'index.html'
    f.write_text(_RAINBOW_NAMED_COLORS_HTML, encoding='utf-8')
    result = _VFY.verify_static(f, task_description='display text that cycles through rainbow colors')
    assert result['status'] == 'passed', result
    assert 'color_mutation_signal' not in result['missing']
    assert 'motion_signal' not in result['missing']


def test_color_task_does_not_require_motion(tmp_path):
    f = tmp_path / 'index.html'
    f.write_text(_RAINBOW_NAMED_COLORS_HTML, encoding='utf-8')
    result = _VFY.verify_static(f, task_description='rainbow color animation')
    assert result['status'] == 'passed'


def test_movement_task_still_requires_motion(tmp_path):
    f = tmp_path / 'index.html'
    f.write_text(_RAINBOW_NAMED_COLORS_HTML, encoding='utf-8')
    result = _VFY.verify_static(f, task_description='make the text bounce and move around')
    assert result['status'] == 'failed'
    assert 'motion_signal' in result['missing']


def test_html_with_no_wave_phase_warns_for_wave_task(tmp_path):
    f = tmp_path / 'index.html'
    # Has animation + color + motion but no Math.sin/phase
    content = """\
<!doctype html><html><body>
<canvas></canvas>
<script>
let t=0;
function loop(){
  ctx.fillStyle = 'hsl('+t+',100%,50%)';
  ctx.fillRect(Math.random()*100,Math.random()*100,10,10);
  t++;
  requestAnimationFrame(loop);
}
requestAnimationFrame(loop);
</script>
</body></html>
"""
    f.write_text(content, encoding='utf-8')
    result = _VFY.verify_static(f, task_description='linear sine wave animation')
    assert result['status'] == 'failed'
    assert 'wave_phase_signal' in result['missing']


def test_valid_animation_html_passes_static_contract(tmp_path):
    f = tmp_path / 'index.html'
    f.write_text(_VALID_ANIMATION_HTML, encoding='utf-8')
    result = _VFY.verify_static(f, task_description='animate color wave with sine oscillation')
    assert result['status'] == 'passed'
    assert result['missing'] == []
    passed_checks = [c['check'] for c in result['checks'] if c['status'] == 'passed']
    assert 'animation_signal' in passed_checks
    assert 'color_mutation_signal' in passed_checks
    assert 'motion_signal' in passed_checks
    assert 'wave_phase_signal' in passed_checks


def test_non_animation_task_treats_missing_signals_as_advisory(tmp_path):
    f = tmp_path / 'index.html'
    f.write_text(_STATIC_HTML, encoding='utf-8')
    # Not an animation task — should not fail for missing animation signals
    result = _VFY.verify_static(f, task_description='show a static page')
    # No animation task keywords → advisory only, no missing
    assert result['status'] == 'passed'
    assert result['missing'] == []


def test_checks_list_contains_all_expected_keys(tmp_path):
    f = tmp_path / 'index.html'
    f.write_text(_VALID_ANIMATION_HTML, encoding='utf-8')
    result = _VFY.verify_static(f, task_description='animate sine wave')
    for check in result['checks']:
        assert 'check' in check
        assert 'status' in check


# ── Regression: multi-file artifacts (index.html + external css/js) ────────────────
# The RunPod failure was a false-negative visual_contract_failed for the common layout
# where animation/color/motion code lives in external js/game.js + css/style.css and the
# entry HTML only links to them. The static contract must scan the linked assets too.

_SHELL_HTML = """\
<!doctype html>
<html>
<head><link rel="stylesheet" href="css/style.css"></head>
<body><canvas id="c"></canvas><script src="js/game.js"></script></body>
</html>
"""
_EXTERNAL_CSS = """\
:root { --hue: 0; }
@keyframes colorShift { from { background-color: hsl(0,100%,50%); } to { background-color: hsl(360,100%,50%); } }
canvas { transform: translateY(0); }
"""
_EXTERNAL_JS = """\
const ctx = document.getElementById('c').getContext('2d');
let phase = 0;
function loop(t) {
  ctx.fillStyle = 'hsl(' + (phase * 10 % 360) + ',100%,50%)';
  phase += 0.01;
  requestAnimationFrame(loop);
}
requestAnimationFrame(loop);
"""


def _write_multifile_artifact(tmp_path):
    (tmp_path / 'css').mkdir()
    (tmp_path / 'js').mkdir()
    (tmp_path / 'index.html').write_text(_SHELL_HTML, encoding='utf-8')
    (tmp_path / 'css' / 'style.css').write_text(_EXTERNAL_CSS, encoding='utf-8')
    (tmp_path / 'js' / 'game.js').write_text(_EXTERNAL_JS, encoding='utf-8')
    return tmp_path / 'index.html'


def test_multifile_artifact_signals_in_external_assets_pass(tmp_path):
    """index.html links to external css/js holding the animation/color/motion code.
    Scanning only the HTML would false-negative; the verifier must read linked assets."""
    f = _write_multifile_artifact(tmp_path)
    result = _VFY.verify_static(f, task_description='animate color motion game')
    assert result['status'] == 'passed', result
    assert result['missing'] == []
    passed = [c['check'] for c in result['checks'] if c['status'] == 'passed']
    assert 'animation_signal' in passed
    assert 'color_mutation_signal' in passed
    assert 'motion_signal' in passed


def test_multifile_shell_without_real_logic_still_fails(tmp_path):
    """A genuinely empty external file must still fail — we are not weakening the contract."""
    (tmp_path / 'js').mkdir()
    (tmp_path / 'index.html').write_text(
        '<!doctype html><html><body><h1>Hi</h1><script src="js/game.js"></script></body></html>',
        encoding='utf-8',
    )
    (tmp_path / 'js' / 'game.js').write_text('// nothing animated here\n', encoding='utf-8')
    result = _VFY.verify_static(tmp_path / 'index.html', task_description='animate color motion')
    assert result['status'] == 'failed'
    assert 'animation_signal' in result['missing']


def test_external_asset_traversal_outside_dir_is_ignored(tmp_path):
    """A linked path escaping the artifact dir must not be read (sandboxed to parent)."""
    outside = tmp_path / 'secret.js'
    outside.write_text('requestAnimationFrame(()=>{}); getContext(); hsl(0,0,0);', encoding='utf-8')
    art = tmp_path / 'app'
    art.mkdir()
    (art / 'index.html').write_text(
        '<!doctype html><html><body><script src="../secret.js"></script></body></html>',
        encoding='utf-8',
    )
    result = _VFY.verify_static(art / 'index.html', task_description='animate color motion')
    # The traversal target is ignored, so the animation signals remain missing → failed.
    assert result['status'] == 'failed'
    assert 'animation_signal' in result['missing']
