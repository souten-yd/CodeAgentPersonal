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
