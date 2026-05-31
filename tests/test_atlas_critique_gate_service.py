from __future__ import annotations

from agent.atlas_critique_gate_service import AtlasCritiqueGateService

_GATE = AtlasCritiqueGateService()


def _critique(findings=None, consensus_risk="low", requires_revision=False):
    return {
        "findings": findings or [],
        "consensus_risk": consensus_risk,
        "requires_revision": requires_revision,
    }


def _finding(severity="info", title="test"):
    return {"severity": severity, "title": title, "detail": "", "recommendation": ""}


def test_no_critique_passes():
    result = _GATE.evaluate(None)
    assert result['gate_status'] == 'passed'
    assert result['blocked'] is False


def test_empty_critique_passes():
    result = _GATE.evaluate(_critique())
    assert result['gate_status'] == 'passed'


def test_info_and_warning_findings_pass():
    result = _GATE.evaluate(_critique(findings=[_finding("info"), _finding("warning")]))
    assert result['gate_status'] == 'passed'
    assert result['blocked'] is False


def test_high_finding_blocks():
    result = _GATE.evaluate(_critique(findings=[_finding("high", "security issue")]))
    assert result['gate_status'] == 'blocked'
    assert result['blocked'] is True
    assert len(result['blocking_findings']) == 1


def test_critical_finding_blocks():
    result = _GATE.evaluate(_critique(findings=[_finding("critical")]))
    assert result['blocked'] is True


def test_high_consensus_risk_blocks():
    result = _GATE.evaluate(_critique(consensus_risk="high"))
    assert result['blocked'] is True


def test_requires_revision_blocks():
    result = _GATE.evaluate(_critique(requires_revision=True))
    assert result['blocked'] is True


def test_high_finding_with_override_reason_allows():
    result = _GATE.evaluate(
        _critique(findings=[_finding("high")]),
        override_reason="user explicitly accepted this risk",
    )
    assert result['gate_status'] == 'overridden'
    assert result['blocked'] is False
    assert result['override_applied'] is True
    assert result['override_reason'] == "user explicitly accepted this risk"


def test_high_finding_without_override_reason_blocks():
    result = _GATE.evaluate(_critique(findings=[_finding("high")]), override_reason="")
    assert result['blocked'] is True
    assert result['override_applied'] is False


def test_blocking_findings_list_populated():
    result = _GATE.evaluate(_critique(findings=[_finding("info"), _finding("high"), _finding("critical")]))
    assert result['blocked'] is True
    assert len(result['blocking_findings']) == 2
