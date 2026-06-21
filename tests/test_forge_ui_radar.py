from __future__ import annotations

from tests.test_forge_arena_ui import _render


def test_arena_candidate_has_detail_drawer_action(tmp_path):
    html = _render(tmp_path, {"arena": {"arena_run_id": "run", "candidates": [{
        "candidate_id": "c1", "model_id": "m1", "route_id": "patch_dsl",
        "adoption_state": "not_applied", "result": {"contract_valid": True, "latency_ms": 10},
    }]}})
    assert 'data-candidate-detail="c1"' in html
    assert "Details" in html
    assert "requires Safe Apply" in html


def test_radar_renders_filters_svg_and_unavailable_distinct_from_zero(tmp_path):
    from tests.test_forge_arena_ui import FORGE_JS, _NODE_TEMPLATE
    import json, shutil, subprocess
    import pytest
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    script = tmp_path / "radar.js"
    script.write_text(_NODE_TEMPLATE.replace(
        "process.stdout.write(global.window.Forge._arenaHtml(JSON.parse(process.argv[3])));",
        "process.stdout.write(global.window.Forge._radarHtml(JSON.parse(process.argv[3]), 'All'));",
    ), encoding="utf-8")
    candidate = {"evaluator_score": {
        "radar_scores": {"structured_output_fidelity": 0.0, "fallback_recovery": None},
        "unavailable_dimensions": ["fallback_recovery"],
    }}
    proc = subprocess.run([node, str(script), str(FORGE_JS), json.dumps(candidate)],
                          capture_output=True, text=True, timeout=30, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    html = proc.stdout
    for name in ("Capability", "Method", "Safety", "Speed", "All"):
        assert f'data-radar-filter="{name}"' in html
    assert '<svg class="forge-radar-svg"' in html
    assert "structured_output_fidelity · 0%" in html
    assert "fallback_recovery · unavailable" in html
    assert "missing evidence, not a zero score" in html
