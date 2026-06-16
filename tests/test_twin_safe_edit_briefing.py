"""Twin Safe-Edit Briefing: turn an ImpactResult into "don't break these dependents" guidance.

Genuine tests with negative controls: an impact with dependents produces a briefing naming them; an
empty / leaf impact produces NO briefing (so it never adds noise); low-confidence links are reported
as uncertain, not as fact.
"""
from __future__ import annotations

from datetime import datetime, timezone

from agent.project_twin.contracts import ImpactItem, ImpactResult
from agent.project_twin.safe_edit_briefing import (
    build_safe_edit_briefing,
    render_safe_edit_briefing,
)


def _item(ref, kind="symbols", conf=0.9, reason=""):
    return ImpactItem(canonical_ref=ref, item_type=kind, status="observed", confidence=conf, reason=reason)


def _impact(**kw):
    return ImpactResult(project_id="p", generated_at=datetime.now(timezone.utc), **kw)


def test_briefing_names_callers_side_effects_and_tests():
    impact = _impact(
        direct_impacts=[_item("py://app/api.py#handler", conf=0.95, reason="calls target")],
        transitive_impacts=[_item("py://app/service.py#run", conf=0.8)],
        side_effects=[_item("py://app/db.py#write", kind="side_effect", conf=0.85)],
        recommended_tests=[_item("py://tests/test_api.py#test_handler", kind="recommended_test", conf=0.9)],
    )
    b = build_safe_edit_briefing(impact, target_refs=["py://app/core.py#target"])
    assert len(b.callers) == 2 and len(b.side_effects) == 1 and len(b.tests) == 1
    text = render_safe_edit_briefing(b)
    assert "Safe-Edit Briefing" in text
    assert "py://app/api.py#handler" in text
    assert "py://app/db.py#write" in text
    assert "py://tests/test_api.py#test_handler" in text
    assert "PUBLIC INTERFACE" in text


def test_empty_impact_produces_no_briefing():
    # Negative control: a leaf symbol nobody depends on must NOT get a briefing (no prompt noise).
    b = build_safe_edit_briefing(_impact(), target_refs=["py://app/new.py#fresh"])
    assert b.is_empty
    assert render_safe_edit_briefing(b) == ""


def test_none_impact_is_safe():
    b = build_safe_edit_briefing(None, target_refs=["x"])
    assert b.is_empty
    assert render_safe_edit_briefing(b) == ""


def test_low_confidence_links_are_reported_as_uncertain():
    impact = _impact(
        direct_impacts=[_item("py://strong.py#a", conf=0.9), _item("py://weak.py#b", conf=0.3)],
    )
    b = build_safe_edit_briefing(impact, uncertain_below=0.5)
    caller_refs = {c["ref"] for c in b.callers}
    uncertain_refs = {c["ref"] for c in b.uncertain}
    assert "py://strong.py#a" in caller_refs
    assert "py://weak.py#b" in uncertain_refs
    text = render_safe_edit_briefing(b)
    assert "Low-confidence" in text and "py://weak.py#b" in text


def test_sections_are_bounded():
    many = [_item(f"py://m.py#f{i}", conf=0.9) for i in range(50)]
    b = build_safe_edit_briefing(_impact(direct_impacts=many))
    assert len(b.callers) <= 12  # _MAX_PER_SECTION


def test_internal_variable_and_def_nodes_are_filtered():
    # Twin impact traversal can surface a caller's local variables / nested defs as var:// and def://
    # nodes. Those are noise in a "who depends on this" briefing (observed while evaluating the Twin
    # over this repo) and must be dropped — only real source symbols remain.
    impact = _impact(direct_impacts=[
        _item("py://capability_scoring.py#load_capability_profile", conf=0.9),
        _item("var://py://capability_scoring.py#load_capability_profile/mode", conf=0.9),
        _item("def://py://capability_scoring.py#load_capability_profile/L161:profile", conf=0.9),
    ])
    b = build_safe_edit_briefing(impact)
    refs = {c["ref"] for c in b.callers}
    assert refs == {"py://capability_scoring.py#load_capability_profile"}
    assert all(not r.startswith(("var://", "def://")) for r in refs)


def test_duplicate_refs_are_deduped():
    impact = _impact(
        direct_impacts=[_item("py://a.py#f", conf=0.9)],
        transitive_impacts=[_item("py://a.py#f", conf=0.7)],
    )
    b = build_safe_edit_briefing(impact)
    assert [c["ref"] for c in b.callers] == ["py://a.py#f"]


def test_callers_sorted_by_confidence():
    impact = _impact(direct_impacts=[
        _item("py://low.py#a", conf=0.6),
        _item("py://high.py#b", conf=0.99),
    ])
    b = build_safe_edit_briefing(impact)
    assert b.callers[0]["ref"] == "py://high.py#b"
