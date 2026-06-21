"""Arena radar overlays with/without assist (補助有無) when baseline data is present."""
from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from tests.test_forge_arena_ui import FORGE_JS, _NODE_TEMPLATE


def _render_radar(tmp_path, candidate: dict) -> str:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    script = tmp_path / "radar.js"
    script.write_text(_NODE_TEMPLATE.replace(
        "process.stdout.write(global.window.Forge._arenaHtml(JSON.parse(process.argv[3])));",
        "process.stdout.write(global.window.Forge._radarHtml(JSON.parse(process.argv[3]), 'All'));",
    ), encoding="utf-8")
    proc = subprocess.run([node, str(script), str(FORGE_JS), json.dumps(candidate)],
                          capture_output=True, text=True, timeout=30, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def test_radar_overlays_baseline_when_present(tmp_path):
    candidate = {"evaluator_score": {
        "radar_scores": {"structured_output_fidelity": 0.9, "edit_intent_quality": 0.8},
        "baseline_radar_scores": {"structured_output_fidelity": 0.4, "edit_intent_quality": 0.2},
    }}
    html = _render_radar(tmp_path, candidate)
    assert "forge-radar-shape--baseline" in html
    assert "forge-radar-shape--assisted" in html
    assert "with assist (補助あり)" in html
    assert "without assist (補助なし)" in html


def test_radar_single_series_without_baseline(tmp_path):
    candidate = {"evaluator_score": {
        "radar_scores": {"structured_output_fidelity": 0.9, "edit_intent_quality": 0.8},
    }}
    html = _render_radar(tmp_path, candidate)
    assert "forge-radar-shape--baseline" not in html
    assert "forge-radar-legend" not in html
    assert '<polygon class="forge-radar-shape"' in html
