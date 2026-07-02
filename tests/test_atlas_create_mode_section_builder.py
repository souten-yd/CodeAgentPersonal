"""Deterministic tests for the create-mode within-file section builder.

A stub llm_json_fn (a plain 2-arg callable, the historical interface call_llm_json falls back to)
returns a skeleton with `// __SECTION__` markers and then a body per section, so the whole
skeleton→sections→splice→assemble flow is exercised with no real model. Covers the success path,
the bounded `capability_ceiling` (no infinite loop) when a section stays empty, and the pure
enumerate/splice/placeholder helpers.
"""
from __future__ import annotations

import json

from agent.atlas_create_mode_section_builder import (
    body_is_placeholder,
    build_file_by_sections,
    enumerate_sections,
    splice_section,
)


_SKELETON = """\
class Renderer {
    constructor(canvas) {
        this.canvas = canvas;
        this.ctx = canvas.getContext('2d');
    }

    castRays(player, map) {
        // __SECTION__: cast_rays
    }

    drawFrame(player, map) {
        // __SECTION__: draw_frame
    }
}
"""


def _stub(section_bodies: dict[str, str], skeleton: str = _SKELETON):
    """Return a 2-arg llm_json_fn stub. Skeleton call -> {proposed_content}; section call (has
    'section_name') -> {body} from `section_bodies` (missing name => empty body)."""
    def fn(_system: str, user: str) -> dict:
        u = json.loads(user)
        name = u.get("section_name")
        if name is not None:
            return {"body": section_bodies.get(name, "")}
        return {"proposed_content": skeleton}
    return fn


# ── pure helpers ──────────────────────────────────────────────────────────────

def test_enumerate_sections_finds_ordered_unique_markers():
    names = [s["name"] for s in enumerate_sections(_SKELETON)]
    assert names == ["cast_rays", "draw_frame"]


def test_splice_section_replaces_marker_with_indented_body():
    out, ok = splice_section(_SKELETON, "cast_rays", "const a = 1;\nreturn a;", "        ")
    assert ok
    assert "// __SECTION__: cast_rays" not in out
    assert "        const a = 1;" in out  # body indented to the marker's indent
    assert "// __SECTION__: draw_frame" in out  # other marker untouched


def test_body_is_placeholder():
    assert body_is_placeholder("") is True
    assert body_is_placeholder("   ") is True
    assert body_is_placeholder("// just a comment") is True
    assert body_is_placeholder("// __SECTION__: x") is True
    assert body_is_placeholder("pass") is True
    assert body_is_placeholder("const a = 1; return a;") is False


# ── build_file_by_sections ──────────────────────────────────────────────────────

def test_build_succeeds_when_all_sections_filled():
    stub = _stub({
        "cast_rays": "const rays = []; return rays;",
        "draw_frame": "this.ctx.clearRect(0,0,10,10);",
    })
    result = build_file_by_sections(
        llm_json_fn=stub, target_path="js/renderer.js",
        item={"title": "Implement raycasting renderer", "acceptance_criteria": ["renders"]},
    )
    assert result["status"] == "ok"
    assert set(result["sections_done"]) == {"cast_rays", "draw_frame"}
    assert result["sections_failed"] == []
    content = result["proposed_content"]
    assert "__SECTION__" not in content  # no markers left
    assert "class Renderer" in content and "castRays(player, map)" in content  # signatures preserved
    assert "const rays = []" in content and "clearRect" in content  # bodies spliced in


def test_unfillable_section_ends_as_capability_ceiling_not_loop():
    # cast_rays keeps coming back empty -> bounded retries -> capability_ceiling naming it.
    stub = _stub({"draw_frame": "this.ctx.clearRect(0,0,10,10);"})  # cast_rays missing => empty
    result = build_file_by_sections(
        llm_json_fn=stub, target_path="js/renderer.js",
        item={"title": "Implement raycasting renderer"},
        section_retries=2,
    )
    assert result["status"] == "capability_ceiling"
    assert "cast_rays" in result["sections_failed"]
    assert "draw_frame" in result["sections_done"]  # the fillable one still got done


def test_skeleton_no_content_returns_no_content():
    def fn(_s, _u):
        return {"proposed_content": ""}
    result = build_file_by_sections(llm_json_fn=fn, target_path="js/x.js", item={"title": "x"})
    assert result["status"] == "no_content"


def test_skeleton_without_markers_is_accepted_as_complete():
    complete = "const answer = 42;\nexport default answer;\n"
    def fn(_s, _u):
        return {"proposed_content": complete}
    result = build_file_by_sections(llm_json_fn=fn, target_path="js/x.js", item={"title": "x"})
    assert result["status"] == "ok"
    assert result["proposed_content"].strip() == complete.strip()
    assert result["sections_done"] == []
