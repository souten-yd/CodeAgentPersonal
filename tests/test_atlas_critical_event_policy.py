from __future__ import annotations

from agent.atlas_approval_service import AtlasApprovalService
from agent.atlas_autopilot_policy_schema import AtlasPolicyEvaluation
from agent.atlas_critical_event_policy import lower_impact_alternative_plan, normalize_critical_event
from agent.atlas_full_auto_gate import relax_evaluation_for_full_auto
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_quality_gate import apply_plan_quality_gate


def _security_plan(severity="critical"):
    return {
        "requirement_summary": "handle auth tokens",
        "goal": "store credentials",
        "adversarial_critique": {
            "findings": [{"severity": severity, "category": "security", "title": "unsafe auth", "detail": "token handling may leak secrets"}],
            "consensus_risk": severity,
            "requires_revision": False,
        },
    }


def _eval(decision="require_approval", categories=None):
    return AtlasPolicyEvaluation(
        evaluation_id="e",
        scope="patch",
        decision=decision,
        categories=categories or ["security"],
        reasons=["security-sensitive change"],
        requires_user_confirmation=decision == "require_approval",
        blocked=decision == "block",
        metadata={"affected_files": ["agent/security.py"]},
    )


def test_safety_sensitive_critical_critique_waits_for_critical_decision():
    result = apply_plan_quality_gate(_security_plan(), preset_id="full_auto", critical_handling="auto")

    assert result["require_approval"] is True
    assert result["status"] == "waiting_for_critical_decision"
    assert result["critique_gate"]["gate_status"] == "waiting_for_critical_decision"
    assert result["critical_event"]["critical_event"] is True


def test_full_auto_and_critical_handling_auto_do_not_bypass_critical_events():
    out = relax_evaluation_for_full_auto(
        _eval("require_approval", ["security"]),
        preset_id="full_auto",
        critical_handling="auto",
    )

    assert out.decision == "require_approval"
    assert out.auto_execution_allowed is False
    assert out.metadata["status"] == "waiting_for_critical_decision"
    assert out.metadata["critical_event"]["critical_event"] is True


def test_non_critical_full_auto_continuation_still_works():
    out = relax_evaluation_for_full_auto(_eval("require_approval", ["dependency_change"]), preset_id="full_auto")

    assert out.decision == "allow"
    assert out.auto_execution_allowed is True


def test_user_ng_generates_lower_impact_alternative_payload():
    event = normalize_critical_event(category="data_loss", reason="destructive path")
    original = {"risk_level": "critical", "target_files": ["a.py", "b.py"], "metadata": {}}

    alternative = lower_impact_alternative_plan(original, event)

    assert alternative["metadata"]["original_critical_path_rejected"] is True
    assert alternative["metadata"]["lower_impact_alternative"] is True
    assert alternative["risk_level"] == "medium"
    assert alternative["target_files"] == ["a.py"]
    assert alternative["metadata"]["remaining_risk"] == "requires_gate_rerun"


def test_critical_event_ui_summary_strings_present():
    from pathlib import Path

    text = Path("web/js/atlas_dashboard.js").read_text(encoding="utf-8")
    assert "Critical event detected" in text
    assert "Original critical path rejected" in text
    assert "Generating lower-impact alternative" in text
    assert "Approve with explicit consent" in text
    assert "Reject / NG and request safer alternative" in text


class _Journal:
    def plan_pool_dir(self, pool_id: str) -> str:
        import tempfile
        from pathlib import Path

        path = Path(tempfile.mkdtemp()) / pool_id
        path.mkdir(parents=True, exist_ok=True)
        return str(path)


def test_user_approval_persists_bounded_scope_and_ng_blocks_original_path():
    event = normalize_critical_event(category="security", affected_files=["agent/security.py"], affected_capabilities=["security"])
    item = AtlasPlanItem(
        item_id="i1",
        pool_id="p1",
        title="Critical item",
        goal="Change auth",
        status="waiting_for_critical_decision",
        risk_level="critical",
        target_files=["agent/security.py"],
        metadata={"critical_event": event},
    )
    pool = AtlasPlanPool(pool_id="p1", root_goal="goal", items=[item])

    service = AtlasApprovalService(_Journal())
    service.decide(
        pool,
        item_id="i1",
        run_id="r1",
        decision="approved",
        reason="approve exact file only",
        approver="tester",
        metadata={"approved_files": ["agent/security.py"], "bounded_continuation": False},
    )
    assert item.status == "ready"
    assert item.metadata["approval"]["approved_files"] == ["agent/security.py"]
    assert item.metadata["approval"]["one_action_only"] is True

    item.status = "waiting_for_critical_decision"
    service.decide(pool, item_id="i1", run_id="r2", decision="rejected", reason="NG", approver="tester", metadata={})
    assert item.status == "needs_revision"
    assert item.metadata["lower_impact_alternative"]["metadata"]["original_critical_path_rejected"] is True
