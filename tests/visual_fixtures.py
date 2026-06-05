from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StaticCase:
    name: str
    task_description: str
    expect_status: str
    must_pass_checks: tuple[str, ...] = ()
    must_miss_checks: tuple[str, ...] = ()


@dataclass(frozen=True)
class AutoVerifyCase:
    name: str
    task_description: str
    smoke: dict
    expect_status: str
    expect_verify_level: str | None = None
    must_have_warnings: tuple[str, ...] = ()
    must_not_have_warnings: tuple[str, ...] = ()


FIXTURES: dict[str, str] = {
    "color_named_keyframes": """\
<!doctype html><html><head><style>
.hello { animation: rainbow 2s linear infinite; }
@keyframes rainbow {
  0% { color: red; }
  25% { color: orange; }
  50% { color: yellow; }
  75% { color: blue; }
  100% { color: purple; }
}
</style></head><body><h1 class="hello">Hello World</h1></body></html>
""",
    "color_hsl_keyframes": """\
<!doctype html><html><head><style>
.hello { animation: hueShift 2s linear infinite; }
@keyframes hueShift {
  from { color: hsl(0, 100%, 50%); }
  to { color: hsl(300, 100%, 50%); }
}
</style></head><body><h1 class="hello">Hello World</h1></body></html>
""",
    "css_variable_hue_js": """\
<!doctype html><html><head><style>
:root { --hue: 0; }
.hello { color: hsl(var(--hue), 100%, 50%); }
</style></head><body><h1 class="hello">Hello World</h1><script>
let hue = 0;
function tick() {
  hue = (hue + 8) % 360;
  document.documentElement.style.setProperty('--hue', String(hue));
  requestAnimationFrame(tick);
}
requestAnimationFrame(tick);
</script></body></html>
""",
    "svg_smil": """\
<!doctype html><html><body>
<svg width="120" height="120" viewBox="0 0 120 120">
  <rect x="45" y="45" width="30" height="30" fill="red">
    <animateTransform attributeName="transform" type="rotate"
      from="0 60 60" to="360 60 60" dur="2s" repeatCount="indefinite" />
  </rect>
</svg>
</body></html>
""",
    "rotate_only": """\
<!doctype html><html><body><div id="cube">Cube</div><script>
let angle = 0;
function spin() {
  angle += 4;
  document.getElementById('cube').style.transform = `rotate(${angle}deg)`;
  requestAnimationFrame(spin);
}
requestAnimationFrame(spin);
</script></body></html>
""",
    "canvas_game": """\
<!doctype html><html><body><canvas id="game" width="200" height="120"></canvas><script>
const canvas = document.getElementById('game');
const ctx = canvas.getContext('2d');
let x = 0;
function draw() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = 'hsl(' + (x % 360) + ', 100%, 50%)';
  ctx.fillRect(x % 180, 40, 20, 20);
  x += 3;
  requestAnimationFrame(draw);
}
requestAnimationFrame(draw);
</script></body></html>
""",
    "static_plain": "<!doctype html><html><body><h1>Hello</h1></body></html>",
    "js_reference_error": """\
<!doctype html><html><body><script>undefinedFn();</script></body></html>
""",
    "module_mismatch": """\
<!doctype html><html><body><script>export const value = 1;</script></body></html>
""",
    "missing_script": """\
<!doctype html><html><body><script src="js/missing.js"></script></body></html>
""",
    "expected_text_missing": "<!doctype html><html><body><p>Other text</p></body></html>",
    "transition_color": """\
<!doctype html><html><head><style>
.hello { color: red; transition: color 0.2s linear; }
.hello.ready { color: purple; }
</style></head><body><h1 class="hello">Hello World</h1><script>
requestAnimationFrame(() => document.querySelector('.hello').classList.add('ready'));
</script></body></html>
""",
}


STATIC_EXPECTATIONS: list[StaticCase] = [
    StaticCase("color_named_keyframes", "rainbow color text", "passed", ("animation_signal", "color_mutation_signal")),
    StaticCase("color_hsl_keyframes", "color animation", "passed", ("animation_signal", "color_mutation_signal")),
    StaticCase("css_variable_hue_js", "hue color animation", "passed", ("animation_signal", "color_mutation_signal")),
    StaticCase("rotate_only", "spin a cube", "passed", ("animation_signal", "motion_signal")),
    StaticCase("canvas_game", "canvas game", "passed", ("animation_signal", "color_mutation_signal", "motion_signal")),
    StaticCase("static_plain", "animate colors", "failed", (), ("animation_signal", "color_mutation_signal")),
    StaticCase("missing_script", "game animation", "failed", (), ("animation_signal",)),
    StaticCase("multifile_external", "animate color motion", "passed", ("animation_signal", "color_mutation_signal", "motion_signal")),
    StaticCase("multifile_empty", "animate color motion", "failed", (), ("animation_signal", "color_mutation_signal", "motion_signal")),
    StaticCase("color_named_keyframes", "rainbow text", "passed", ("animation_signal", "color_mutation_signal")),
    StaticCase("color_named_keyframes", "make it move around", "failed", (), ("motion_signal",)),
    StaticCase("transition_color", "color change on load", "passed", ("animation_signal", "color_mutation_signal")),
]


AUTOVERIFY_EXPECTATIONS: list[AutoVerifyCase] = [
    AutoVerifyCase("color_named_keyframes", "rainbow color text", {"status": "browser_smoke_passed"}, "passed", "runtime_smoke_checked", ("visual_contract_passed",)),
    AutoVerifyCase("color_hsl_keyframes", "color animation", {"status": "browser_smoke_passed"}, "passed", "runtime_smoke_checked", ("visual_contract_passed",)),
    AutoVerifyCase("css_variable_hue_js", "hue color animation", {"status": "browser_smoke_passed"}, "passed", "runtime_smoke_checked", ("visual_contract_passed",)),
    AutoVerifyCase("rotate_only", "spin a cube", {"status": "browser_smoke_passed"}, "passed", "runtime_smoke_checked", ("visual_contract_passed",)),
    AutoVerifyCase("canvas_game", "canvas game", {"status": "browser_smoke_passed"}, "passed", "runtime_smoke_checked", ("visual_contract_passed",)),
    AutoVerifyCase("static_plain", "animate colors", {"status": "browser_smoke_failed", "reason": "animation_not_detected"}, "failed", None, ("visual_contract_failed", "visual_missing:animation_signal")),
    AutoVerifyCase("js_reference_error", "show page", {"status": "browser_smoke_failed", "reason": "js_error", "console_errors": ["ReferenceError: undefinedFn is not defined"]}, "failed", None, ("browser_smoke_failed:js_error",)),
    AutoVerifyCase("module_mismatch", "game", {"status": "browser_smoke_failed", "reason": "js_error:module_script_mismatch"}, "failed", None, ("browser_smoke_failed:js_error:module_script_mismatch",)),
    AutoVerifyCase("missing_script", "game", {"status": "browser_smoke_failed", "reason": "js_error:missing_script_src"}, "failed", None, ("browser_smoke_failed:js_error:missing_script_src",)),
    AutoVerifyCase("multifile_external", "animate color motion", {"status": "browser_smoke_passed"}, "passed", "runtime_smoke_checked", ("visual_contract_passed",)),
    AutoVerifyCase("multifile_empty", "animate", {"status": "browser_smoke_failed", "reason": "animation_not_detected"}, "failed", None, ("visual_contract_failed",)),
    AutoVerifyCase("expected_text_missing", "show page", {"status": "browser_smoke_failed", "reason": "expected_text_missing"}, "failed", None, ("browser_smoke_failed:expected_text_missing",)),
    AutoVerifyCase("color_named_keyframes", "rainbow text", {"status": "browser_smoke_passed"}, "passed", "runtime_smoke_checked", ("visual_contract_passed",)),
    AutoVerifyCase("color_named_keyframes", "make it move around", {"status": "browser_smoke_failed", "reason": "animation_not_detected"}, "failed", None, ("visual_contract_failed", "visual_missing:motion_signal")),
    AutoVerifyCase("transition_color", "color change on load", {"status": "browser_smoke_passed"}, "passed", "runtime_smoke_checked", ("visual_contract_passed",)),
]


def write_fixture(tmp_path: Path, name: str) -> Path:
    if name.startswith("multifile_"):
        return write_multifile(tmp_path, name)
    path = tmp_path / "index.html"
    path.write_text(FIXTURES[name], encoding="utf-8")
    return path


def write_multifile(tmp_path: Path, name: str) -> Path:
    (tmp_path / "css").mkdir(parents=True, exist_ok=True)
    (tmp_path / "js").mkdir(parents=True, exist_ok=True)
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><head><link rel="stylesheet" href="css/style.css"></head>'
        '<body><canvas id="game"></canvas><script src="js/game.js"></script></body></html>',
        encoding="utf-8",
    )
    if name == "multifile_external":
        (tmp_path / "css" / "style.css").write_text(
            ":root { --hue: 0; }\n"
            "@keyframes hueShift { from { background-color: red; } to { background-color: purple; } }\n"
            "canvas { animation: hueShift 1s infinite; transform: translateX(0); }\n",
            encoding="utf-8",
        )
        (tmp_path / "js" / "game.js").write_text(
            "const canvas = document.getElementById('game');\n"
            "const ctx = canvas.getContext('2d');\n"
            "let t = 0;\n"
            "function loop(){ ctx.fillStyle = `hsl(${t % 360},100%,50%)`; t += 1; requestAnimationFrame(loop); }\n"
            "requestAnimationFrame(loop);\n",
            encoding="utf-8",
        )
    elif name == "multifile_empty":
        (tmp_path / "css" / "style.css").write_text("body { margin: 0; }\n", encoding="utf-8")
        (tmp_path / "js" / "game.js").write_text("// no animation\n", encoding="utf-8")
    else:
        raise KeyError(name)
    return tmp_path / "index.html"
