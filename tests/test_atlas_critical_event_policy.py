from __future__ import annotations

from agent.atlas_approval_service import AtlasApprovalService
from agent.atlas_autopilot_policy_schema import AtlasPolicyEvaluation
from agent.atlas_critical_replanning_service import AtlasCriticalReplanningService
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
    assert "decideCriticalEvent" in text
    api_text = Path("web/js/atlas_pipeline_api.js").read_text(encoding="utf-8")
    assert "/api/atlas/critical-decisions/decide" in api_text


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


def test_rejected_ng_critical_event_creates_lower_impact_revised_item_and_rerun_markers():
    event = normalize_critical_event(category="security", affected_files=["agent/security.py"], affected_capabilities=["security"])
    item = AtlasPlanItem(
        item_id="i2",
        pool_id="p2",
        title="Critical item",
        goal="Change auth",
        status="waiting_for_critical_decision",
        risk_level="critical",
        target_files=["agent/security.py", "agent/extra.py"],
        metadata={"critical_event": event},
    )
    pool = AtlasPlanPool(pool_id="p2", root_goal="goal", items=[item])

    service = AtlasApprovalService(_Journal())
    service.decide(pool, item_id="i2", run_id="r1", decision="rejected", reason="NG", approver="tester", metadata={})

    assert item.status == "needs_revision"
    assert item.auto_execution_allowed is False
    assert item.metadata["executable"] is False
    revised_id = item.metadata["lower_impact_revised_item_id"]
    revised = pool.get_item(revised_id)
    assert revised is not None
    assert revised.status == "approval_required"
    assert revised.metadata["lower_impact_revised_candidate"] is True
    assert revised.metadata["requires_critique_gate_rerun"] is True
    assert revised.metadata["requires_policy_gate_rerun"] is True
    assert revised.metadata["requires_safe_apply_gate_rerun"] is True
    assert revised.metadata["gate_rerun_required"] == ["plan_critique_gate", "policy_gate", "safe_apply_gate"]
    assert revised.metadata["gate_rerun_performed"] is True
    assert revised.metadata["rerun_critique_gate"]["critique_gate"]["gate_status"] == "passed"
    assert revised.metadata["rerun_safety_gate"]["phase"] == "pre_safe_apply"
    assert revised.metadata["rerun_result_status"] == "approval_required"
    assert revised.metadata["next_required_user_action"] == "Review lower-impact revised candidate before any mutation."
    assert revised.metadata["safe_apply_allowed_before_gate_rerun"] is False
    assert revised.auto_execution_allowed is False
    assert revised.target_files == ["agent/security.py"]
    assert pool.metadata["critical_replanning"]["original_path_blocked"] is True
    assert pool.metadata["critical_replanning"]["revised_item_id"] == revised_id


def test_critical_replanning_rerun_critical_finding_waits_for_decision():
    event = normalize_critical_event(category="security", affected_files=["agent/security.py"], affected_capabilities=["security"])
    item = AtlasPlanItem(
        item_id="i4",
        pool_id="p4",
        title="Critical item",
        goal="Change auth",
        status="waiting_for_critical_decision",
        risk_level="critical",
        target_files=["agent/security.py"],
        metadata={"critical_event": event},
    )
    pool = AtlasPlanPool(pool_id="p4", root_goal="goal", items=[item])

    result = AtlasCriticalReplanningService().create_lower_impact_revision(
        pool=pool,
        original_item=item,
        critical_event=event,
        user_decision_record={"decision": "rejected_ng_safer_replan"},
        lower_impact_alternative={
            "goal": "Safer auth docs",
            "risk_level": "medium",
            "target_files": ["agent/security.py"],
            "adversarial_critique": {
                "findings": [
                    {
                        "severity": "critical",
                        "category": "security",
                        "title": "still unsafe",
                        "detail": "security decision remains critical",
                    }
                ],
                "consensus_risk": "critical",
            },
        },
        profile_context={"preset_id": "full_auto", "critical_handling": "auto"},
    )

    revised = result["revised_item"]
    assert revised.status == "waiting_for_critical_decision"
    assert revised.metadata["rerun_result_status"] == "waiting_for_critical_decision"
    assert revised.metadata["critical_event"]["critical_event"] is True
    assert item.metadata["original_path_blocked"] is True
    assert item.auto_execution_allowed is False


def test_critical_replanning_ready_only_inside_active_bounded_envelope():
    event = normalize_critical_event(category="security", affected_files=["docs/safer.md"], affected_capabilities=["security"])
    item = AtlasPlanItem(
        item_id="i5",
        pool_id="p5",
        title="Critical item",
        goal="Change docs",
        status="waiting_for_critical_decision",
        risk_level="critical",
        target_files=["docs/safer.md"],
        metadata={"critical_event": event},
    )
    pool = AtlasPlanPool(pool_id="p5", root_goal="goal", project_path=".", items=[item])

    result = AtlasCriticalReplanningService().create_lower_impact_revision(
        pool=pool,
        original_item=item,
        critical_event=event,
        user_decision_record={"decision": "rejected_ng_safer_replan"},
        lower_impact_alternative={
            "goal": "Safer docs",
            "risk_level": "low",
            "target_files": ["docs/safer.md"],
            "metadata": {"proposed_content": "safe docs update"},
        },
        profile_context={"preset_id": "full_auto", "bounded_envelope_active": True},
    )

    revised = result["revised_item"]
    assert revised.status == "ready"
    assert revised.auto_execution_allowed is True
    assert revised.metadata["rerun_result_status"] == "ready"
    assert revised.metadata["rerun_safety_gate"]["decision"] == "allow"


def test_waiting_for_critical_decision_items_are_listed_for_dedicated_decision():
    event = normalize_critical_event(category="security", affected_files=["agent/security.py"], affected_capabilities=["security"])
    item = AtlasPlanItem(
        item_id="i3",
        pool_id="p3",
        title="Critical item",
        goal="Change auth",
        status="waiting_for_critical_decision",
        risk_level="critical",
        target_files=["agent/security.py"],
        metadata={"critical_event": event},
    )
    pool = AtlasPlanPool(pool_id="p3", root_goal="goal", items=[item])

    data = AtlasApprovalService(_Journal()).list_pool_approvals(pool)

    assert data["pending_count"] == 1
    assert data["approval_required_items"][0]["item_id"] == "i3"
