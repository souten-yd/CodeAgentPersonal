"""Contract: the Claude panel renders a status-driven safety-block panel (reason + Approve &
continue / Revise / Cancel) for pool.status == 'blocked_safety_review', and stops the Patch spinner
instead of leaving it spinning. Derived purely from backend status so a reload stays consistent.
"""
from __future__ import annotations

from pathlib import Path

PANEL = Path("web/js/atlas_claude_panel.js").read_text(encoding="utf-8")
API = Path("web/js/atlas_pipeline_api.js").read_text(encoding="utf-8")


def test_panel_has_status_driven_safety_block_branch():
    # State-driven from pool.status (survives reload), not an in-memory flag.
    assert "poolStatus === 'blocked_safety_review'" in PANEL
    assert "function appendSafetyBlockPrompt" in PANEL


def test_panel_surfaces_block_reason_and_three_actions():
    assert "safety_gate_block_reason_after_clarification" in PANEL
    assert "Safety gate blocked" in PANEL
    assert "Approve & continue" in PANEL
    assert "Revise" in PANEL
    assert "Cancel" in PANEL


def test_panel_grants_override_via_backend_route():
    assert "grantSafetyOverride" in PANEL
    assert "grantSafetyOverride" in API
    assert "/safety-override" in API


def test_panel_stops_patch_spinner_on_safety_block():
    # The autonomous workflow renderer must not leave Patch/Apply 'running' on a safety block.
    assert "blocked_safety_review" in PANEL
    assert "safety gate blocked" in PANEL.lower()
    assert "updateStage(block, 'patch', 'failed'" in PANEL
