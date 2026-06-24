"""Contract tests for deterministic repair recipes (webgl_canvas_2d_context_conflict)."""
from __future__ import annotations

from agent.atlas_repair_recipes import (
    apply_known_bug_repairs,
    repair_webgl_2d_conflict,
)

_WEBGL = {"render_model": "webgl", "primary_canvas": "gameCanvas"}


def test_removes_dead_2d_context_declaration():
    # the exact live defect: a 2D renderer bound to an unused variable on the WebGL canvas
    content = (
        "function initGame(){\n"
        "  const canvas = document.getElementById('gameCanvas');\n"
        "  const renderer = new Renderer(canvas.getContext('2d'));\n"
        "  const engine = new GameEngine();\n"
        "  engine.init('gameCanvas');\n"
        "}\n"
    )
    res = repair_webgl_2d_conflict(content, "gameCanvas")
    assert res["applied"] is True
    assert res["recipe"] == "remove_dead_2d_context"
    assert "getContext('2d')" not in res["new_content"]
    assert "new GameEngine()" in res["new_content"]  # untouched
    assert "canvas.getContext('2d')" in res["removed"][0]


def test_direct_dead_2d_context_declaration():
    content = (
        "const ctx = document.getElementById('gameCanvas').getContext('2d');\n"
        "const engine = new GameEngine();\n"
    )
    res = repair_webgl_2d_conflict(content, "gameCanvas")
    assert res["applied"] is True
    assert "getContext('2d')" not in res["new_content"]


def test_does_not_remove_a_used_2d_context():
    # the 2D context IS used -> unsafe to delete -> recipe declines and returns options
    content = (
        "const canvas = document.getElementById('gameCanvas');\n"
        "const ctx = canvas.getContext('2d');\n"
        "ctx.fillRect(0, 0, 10, 10);\n"
    )
    res = repair_webgl_2d_conflict(content, "gameCanvas")
    assert res["applied"] is False
    assert res["reason"] == "2d_context_in_use"
    assert [o["id"] for o in res["options"]] == ["A", "B", "C"]


def test_no_conflict_returns_not_applied():
    content = "const canvas = document.getElementById('gameCanvas');\nnew THREE.WebGLRenderer({canvas});\n"
    res = repair_webgl_2d_conflict(content, "gameCanvas")
    assert res["applied"] is False
    assert res["reason"] == "no_conflict"


def test_2d_on_a_different_canvas_is_not_touched():
    content = (
        "const mini = document.getElementById('minimap');\n"
        "const mctx = mini.getContext('2d');\n"
        "mctx.fillRect(0,0,5,5);\n"
    )
    res = repair_webgl_2d_conflict(content, "gameCanvas")
    assert res["applied"] is False
    assert res["reason"] == "no_conflict"


def test_dispatch_only_for_webgl_contract():
    content = "const r = new Renderer(document.getElementById('gameCanvas').getContext('2d'));\n"
    assert apply_known_bug_repairs(content, _WEBGL)["applied"] is True
    assert apply_known_bug_repairs(content, {"render_model": "canvas_2d", "primary_canvas": "c"})["applied"] is False
    assert apply_known_bug_repairs(content, {})["applied"] is False
    assert apply_known_bug_repairs(content, None)["applied"] is False
