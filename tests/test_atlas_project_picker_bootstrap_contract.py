from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_JS = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")


def _function_body(source: str, name: str) -> str:
    marker = f"function {name}"
    start = source.index(marker)
    paren = source.index("(", start)
    depth = 0
    close_paren = -1
    for pos in range(paren, len(source)):
        char = source[pos]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                close_paren = pos
                break
    assert close_paren > -1
    brace = source.index("{", close_paren)
    depth = 0
    for pos in range(brace, len(source)):
        char = source[pos]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[brace + 1:pos]
    raise AssertionError(f"{name} body not found")


def test_project_restore_cross_contamination_bootstrap_loads_selected_project_after_set_active():
    body = _function_body(APP_JS, "bootstrapProjects")
    assert "const chosen = (stored && list.find((p) => p.name === stored)) || list[0];" in body
    assert "setActiveProject(chosen)" in body
    assert "renderProjects()" in body
    assert "root.AtlasClaudePanel?.loadProject?.(chosen.name)" in body


def test_project_selection_loads_the_selected_panel_project():
    body = _function_body(APP_JS, "selectProject")
    assert "setActiveProject(found)" in body
    assert "root.AtlasClaudePanel?.loadProject?.(found.name)" in body


def test_project_creation_routes_through_select_project_for_panel_load():
    body = _function_body(APP_JS, "createProject")
    assert "await loadProjects()" in body
    assert "selectProject(created.name)" in body


def test_project_picker_bootstrap_must_load_selected_project_after_set_active():
    body = _function_body(APP_JS, "bootstrapProjects")
    assert "setActiveProject(chosen)" in body
    assert "root.AtlasClaudePanel?.loadProject?.(chosen.name)" in body
