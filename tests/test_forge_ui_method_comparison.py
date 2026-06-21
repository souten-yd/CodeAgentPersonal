from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from tests.test_forge_arena_ui import FORGE_JS, _NODE_TEMPLATE, _render


def _render_helper(tmp_path, helper: str, payload: dict) -> str:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    script = tmp_path / "method_ui.js"
    script.write_text(
        _NODE_TEMPLATE.replace(
            "process.stdout.write(global.window.Forge._arenaHtml(JSON.parse(process.argv[3])));",
            f"process.stdout.write(global.window.Forge.{helper}(JSON.parse(process.argv[3])));",
        ),
        encoding="utf-8",
    )
    proc = subprocess.run(
        [node, str(script), str(FORGE_JS), json.dumps(payload)],
        capture_output=True,
        text=True,
        timeout=30,
        encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def _candidate() -> dict:
    return {
        "candidate_id": "c-method",
        "model_id": "weak-local",
        "route_id": "patch_dsl",
        "method_variant": "structured_patch_json",
        "method_fallbacks": ["edit_intent_list", "anchored_edit_block"],
        "result": {"contract_valid": True, "fallback_attempts": ["edit_intent_list"]},
        "evaluator_score": {"final_score": 0.73},
        "adoption_state": "not_applied",
    }


def test_fallback_graph_marks_primary_attempted_and_available(tmp_path):
    html = _render_helper(tmp_path, "_fallbackGraphHtml", _candidate())
    assert "Fallback graph" in html
    assert "structured_patch_json" in html and "primary" in html
    assert "edit_intent_list" in html and "attempted" in html
    assert "anchored_edit_block" in html and "available" in html
    assert "does not execute or apply" in html


def test_benchmark_method_comparison_uses_arena_evidence(tmp_path):
    html = _render_helper(tmp_path, "_methodComparisonHtml", {"arena": {"candidates": [_candidate()]}})
    assert "Method comparison" in html
    assert "weak-local" in html
    assert "structured_patch_json" in html
    assert "edit_intent_list → anchored_edit_block" in html
    assert "valid" in html and "0.73" in html


def test_policy_recommendation_is_advisory_and_safe_apply_gated(tmp_path):
    html = _render_helper(tmp_path, "_policyRecommendationHtml", _candidate())
    assert "advisory_not_applied" in html
    assert "eligible_for_proposal_review" in html
    assert "cannot change routing" in html
    assert "Proposal, Safe Apply, and Verification remain required" in html


def test_arena_exposes_policy_drawer_action(tmp_path):
    html = _render(tmp_path, {"arena": {"arena_run_id": "run", "candidates": [_candidate()]}})
    assert 'data-policy-recommendation="c-method"' in html
    assert ">Policy</button>" in html
