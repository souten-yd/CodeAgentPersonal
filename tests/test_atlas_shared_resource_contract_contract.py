"""Contract tests for the deterministic shared-RESOURCE contract.

This is the consistency-layer hardening: per-file units that are generated independently must agree
on cross-cutting platform facts (the canvas render model, real DOM ids, loaded libs, sibling
globals). The motivating defect: game.js drove #gameCanvas as a Three.js WebGL surface while main.js
called getContext('2d') on the SAME canvas, breaking WebGL. The contract makes that agreement
explicit and deterministic (no LLM).
"""
from __future__ import annotations

from agent.atlas_interface_contract import (
    build_shared_resource_contract,
    render_shared_resource_contract_for_prompt,
    webgl_canvas_2d_conflict,
)

_WEBGL_CONTRACT = {"render_model": "webgl", "render_lib": "three.js", "primary_canvas": "gameCanvas"}

INDEX_HTML = """<!DOCTYPE html><html><body>
  <div id="game-container">
    <canvas id="gameCanvas"></canvas>
    <div id="menu-overlay" class="active">
      <button id="start-btn">START</button>
    </div>
    <div id="hud"><div id="score-display">0</div></div>
  </div>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
  <script src="js/game.js"></script>
  <script src="js/main.js"></script>
</body></html>"""

GAME_JS = """class GameEngine {
  init(id) { this.canvas = document.getElementById(id);
    this.renderer = new THREE.WebGLRenderer({ canvas: this.canvas }); }
}
window.GameEngine = GameEngine;"""

MAIN_JS_BAD = """function initGame() {
  const canvas = document.getElementById('gameCanvas');
  const renderer = new Renderer(canvas.getContext('2d'));
  const gameEngine = new GameEngine();
}
class Renderer {}"""


def test_detects_webgl_render_model_and_primary_canvas():
    c = build_shared_resource_contract({"index.html": INDEX_HTML, "js/game.js": GAME_JS})
    assert c["render_model"] == "webgl"
    assert c["render_lib"] == "three.js"
    assert c["primary_canvas"] == "gameCanvas"


def test_detects_the_webgl_vs_2d_conflict():
    # game.js = WebGL, main.js = 2D on the same canvas -> the exact live defect
    c = build_shared_resource_contract(
        {"index.html": INDEX_HTML, "js/game.js": GAME_JS, "js/main.js": MAIN_JS_BAD}
    )
    assert c["render_model"] == "webgl"  # WebGL wins as the app model
    assert c["context_conflict"] is True


def test_extracts_dom_ids_and_external_libs():
    c = build_shared_resource_contract({"index.html": INDEX_HTML})
    assert "gameCanvas" in c["dom_ids"]
    assert "menu-overlay" in c["dom_ids"]
    assert "start-btn" in c["dom_ids"]
    assert any("three" in lib.lower() for lib in c["external_libs"])


def test_extracts_sibling_globals():
    c = build_shared_resource_contract({"index.html": INDEX_HTML, "js/game.js": GAME_JS})
    assert "js/game.js" in c["globals_by_file"]
    assert "GameEngine" in c["globals_by_file"]["js/game.js"]


def test_render_emits_the_no_2d_constraint_for_webgl_canvas():
    c = build_shared_resource_contract({"index.html": INDEX_HTML, "js/game.js": GAME_JS})
    text = render_shared_resource_contract_for_prompt(c)
    assert "gameCanvas" in text
    assert "getContext('2d')" in text  # the explicit prohibition the model must obey
    assert "WebGL" in text
    # DOM ids and globals are surfaced so files reference real names
    assert "#menu-overlay" in text
    assert "GameEngine" in text


def test_2d_canvas_app_gets_2d_model_no_conflict():
    html = "<canvas id='c'></canvas>"
    js = "const ctx = document.getElementById('c').getContext('2d');"
    c = build_shared_resource_contract({"index.html": html, "app.js": js})
    assert c["render_model"] == "canvas_2d"
    assert c["context_conflict"] is False


def test_non_app_files_yield_empty_contract():
    c = build_shared_resource_contract({"util.py": "def f(): pass", "README.md": "# hi"})
    assert c == {}
    assert render_shared_resource_contract_for_prompt(c) == ""


# ── Enforcement gate: reject 2D context on the WebGL canvas ──────────────────────────────────────

def test_gate_flags_2d_context_on_webgl_canvas_via_variable():
    # the exact live defect: const canvas = getElementById('gameCanvas'); new Renderer(canvas.getContext('2d'))
    bad = "const canvas = document.getElementById('gameCanvas');\nconst r = new Renderer(canvas.getContext('2d'));"
    assert webgl_canvas_2d_conflict(_WEBGL_CONTRACT, bad) == "webgl_canvas_2d_context_conflict:gameCanvas"


def test_gate_flags_2d_context_on_webgl_canvas_direct():
    bad = "const ctx = document.getElementById('gameCanvas').getContext('2d');"
    assert webgl_canvas_2d_conflict(_WEBGL_CONTRACT, bad) == "webgl_canvas_2d_context_conflict:gameCanvas"


def test_gate_allows_2d_on_a_different_canvas():
    # a separate minimap canvas legitimately uses 2D — must NOT be flagged
    ok = "const mini = document.getElementById('minimap');\nconst mctx = mini.getContext('2d');"
    assert webgl_canvas_2d_conflict(_WEBGL_CONTRACT, ok) is None


def test_gate_allows_webgl_usage_on_the_webgl_canvas():
    ok = "const c = document.getElementById('gameCanvas');\nconst r = new THREE.WebGLRenderer({canvas: c});"
    assert webgl_canvas_2d_conflict(_WEBGL_CONTRACT, ok) is None


def test_gate_noop_when_app_is_not_webgl():
    twod = {"render_model": "canvas_2d", "primary_canvas": "c"}
    code = "const ctx = document.getElementById('c').getContext('2d');"
    assert webgl_canvas_2d_conflict(twod, code) is None
    assert webgl_canvas_2d_conflict({}, code) is None
