from agent.atlas_repair_recipe_registry import (
    apply_repair_for_violation,
    repair_options_for_violation,
)


_VIOLATION = {
    "code": "webgl_canvas_2d_context_conflict",
    "contract_type": "resource",
    "path": "main.js",
    "evidence": {"primary_canvas": "gameCanvas"},
}
_CONTEXT = {
    "resource_contract": {"render_model": "webgl", "primary_canvas": "gameCanvas"},
    "content_by_path": {
        "main.js": (
            "const canvas = document.getElementById('gameCanvas');\n"
            "const renderer = new Renderer(canvas.getContext('2d'));\n"
            "const engine = new GameEngine();\n"
        )
    },
}


def test_registry_returns_webgl_repair_options():
    out = repair_options_for_violation(_VIOLATION, _CONTEXT)

    assert out["available"] is True
    assert out["recipe"] == "webgl_canvas_2d_context_conflict"
    assert [option["id"] for option in out["options"]] == ["A", "B", "C"]


def test_registry_applies_dead_context_repair_without_guessing_semantics():
    out = apply_repair_for_violation(violation=_VIOLATION, context=_CONTEXT)

    assert out["applied"] is True
    assert out["path"] == "main.js"
    assert "getContext('2d')" not in out["new_content"]
    assert "new GameEngine()" in out["new_content"]


def test_registry_selected_unimplemented_option_declines_bounded():
    context = {
        "resource_contract": {"render_model": "webgl", "primary_canvas": "gameCanvas"},
        "content_by_path": {
            "main.js": (
                "const canvas = document.getElementById('gameCanvas');\n"
                "const ctx = canvas.getContext('2d');\n"
                "ctx.fillRect(0, 0, 10, 10);\n"
            )
        },
    }

    out = apply_repair_for_violation(violation=_VIOLATION, context=context, selected_option_id="B")

    assert out["applied"] is False
    assert out["reason"] == "selected_option_not_implemented"
    assert out["selected_option_id"] == "B"


def test_unknown_violation_has_no_recipe():
    out = repair_options_for_violation({"code": "env_key_mismatch", "contract_type": "resource"}, {})

    assert out == {"available": False, "reason": "no_recipe", "options": []}

