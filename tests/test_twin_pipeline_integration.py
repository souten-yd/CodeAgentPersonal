"""TFG-12 cut-over — Twin Control Plane live-pipeline integration seam tests.

Proves the seam is safe and reversible:

- mode resolves from config/env and defaults to OFF (unknown values are OFF too);
- OFF produces inert evidence and engages nothing;
- SHADOW assembles advisory evidence without engaging;
- ACTIVE engages only with shadow evidence and stays advisory (never execution authority);
- evidence building never raises.
"""
from __future__ import annotations

import pytest

from agent.twin_control_plane.active_integration import PipelineMode
from agent.twin_control_plane.pipeline_integration import (
    PIPELINE_MODE_ENV,
    build_twin_pipeline_evidence,
    resolve_pipeline_mode,
)


def test_mode_defaults_to_off(monkeypatch):
    monkeypatch.delenv(PIPELINE_MODE_ENV, raising=False)
    assert resolve_pipeline_mode() == PipelineMode.OFF


def test_mode_reads_env(monkeypatch):
    monkeypatch.setenv(PIPELINE_MODE_ENV, "active")
    assert resolve_pipeline_mode() == PipelineMode.ACTIVE
    monkeypatch.setenv(PIPELINE_MODE_ENV, "shadow")
    assert resolve_pipeline_mode() == PipelineMode.SHADOW


def test_unknown_mode_is_off(monkeypatch):
    monkeypatch.setenv(PIPELINE_MODE_ENV, "banana")
    assert resolve_pipeline_mode() == PipelineMode.OFF


def test_explicit_value_overrides_env(monkeypatch):
    monkeypatch.setenv(PIPELINE_MODE_ENV, "active")
    assert resolve_pipeline_mode("off") == PipelineMode.OFF


def test_off_mode_is_inert():
    ev = build_twin_pipeline_evidence(mode=PipelineMode.OFF, requirement="add feature",
                                      pool_id="p1", changed_refs=["a.py"])
    assert ev["engaged"] is False
    assert ev["available"] is False
    assert ev["mode"] == "off"
    assert "shadow_report" not in ev


def test_shadow_mode_assembles_advisory_evidence():
    ev = build_twin_pipeline_evidence(mode=PipelineMode.SHADOW, requirement="add feature",
                                      pool_id="p1", changed_refs=["a.py", "b.py"])
    assert ev["available"] is True
    assert ev["advisory"] is True
    assert ev["engaged"] is False  # shadow records, never engages
    assert ev["policy_id"]
    assert ev["brief_id"]
    assert ev["shadow_report"] is not None


def test_active_mode_engages_with_shadow_evidence_and_stays_advisory():
    ev = build_twin_pipeline_evidence(mode=PipelineMode.ACTIVE, requirement="add feature",
                                      pool_id="p1", changed_refs=["a.py"])
    assert ev["available"] is True
    assert ev["engaged"] is True  # shadow evidence was assembled
    assert ev["requires_shadow_evidence"] is False
    # Active never claims execution authority: it is advisory evidence only.
    assert ev["advisory"] is True
    assert ev["shadow_report"]["changes_execution"] is False
    assert ev["shadow_report"]["changes_production_routing"] is False


def test_build_never_raises_on_bad_input():
    # Garbage change_class still yields inert/available=False evidence, not an exception.
    ev = build_twin_pipeline_evidence(mode=PipelineMode.ACTIVE, change_class="not_a_class")
    assert ev["available"] is False
    assert ev["engaged"] is False
