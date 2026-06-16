from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from agent.atlas_auto_policy_presets import atlas_auto_policy_presets
from agent.atlas_automation_gate_service import AtlasAutomationGateService
from agent.atlas_critical_event_policy import lower_impact_alternative_plan
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_quality_gate import apply_plan_quality_gate


from agent.atlas_time_utils import utc_now_iso as _utc_now_iso


class AtlasCriticalReplanningService:
    """Create lower-impact revisions after a rejected critical Atlas path."""

    def __init__(self, safety_gate: AtlasAutomationGateService | None = None):
        self.safety_gate = safety_gate or AtlasAutomationGateService()

    def create_lower_impact_revision(
        self,
        *,
        pool: AtlasPlanPool,
        original_item: AtlasPlanItem | None = None,
        critical_event: dict[str, Any] | None = None,
        user_decision_record: dict[str, Any] | None = None,
        lower_impact_alternative: dict[str, Any] | None = None,
        profile_context: dict[str, Any] | None = None,
        workflow_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if original_item is None and not pool.pool_id:
            raise ValueError("original_item_or_pool_required")

        event = dict(critical_event or {})
        context = dict(profile_context or {})
        alternative = dict(
            lower_impact_alternative
            or lower_impact_alternative_plan(self._item_payload(original_item), event)
        )
        revision_id = str(alternative.get("revision_id") or f"critical_replan_{uuid4().hex[:10]}")
        revised_item = self._build_revised_item(
            pool=pool,
            original_item=original_item,
            critical_event=event,
            alternative=alternative,
            revision_id=revision_id,
        )

        critique_gate = self._rerun_critique_gate(revised_item, alternative, context)
        safety_gate = self._rerun_safety_gate(pool, revised_item, context)
        rerun_status, next_action = self._resolve_rerun_status(
            critique_gate=critique_gate,
            safety_gate=safety_gate,
            profile_context=context,
        )

        if rerun_status == "waiting_for_critical_decision":
            revised_item.status = "waiting_for_critical_decision"
            revised_item.requires_user_confirmation = True
            critical = (
                critique_gate.get("critical_event")
                or ((safety_gate.get("metadata") or {}).get("critical_event") if isinstance(safety_gate, dict) else {})
                or {}
            )
            if critical:
                revised_item.metadata["critical_event"] = critical
        elif rerun_status == "ready":
            revised_item.status = "ready"
            revised_item.requires_user_confirmation = False
            revised_item.auto_execution_allowed = True
        else:
            revised_item.status = "approval_required"
            revised_item.requires_user_confirmation = True
            revised_item.auto_execution_allowed = False

        evidence = {
            "revision_id": revision_id,
            "created_at": _utc_now_iso(),
            "original_item_id": original_item.item_id if original_item else "",
            "original_pool_id": pool.pool_id,
            "original_path_blocked": True,
            "created_from_critical_event": True,
            "critical_event": event,
            "user_decision_record": dict(user_decision_record or {}),
            "lower_impact_alternative": alternative,
            "revised_item_id": revised_item.item_id,
            "revised_plan_snapshot": self._item_payload(revised_item),
            "gate_rerun_required": True,
            "gate_rerun_performed": True,
            "rerun_critique_gate": critique_gate,
            "rerun_safety_gate": safety_gate,
            "rerun_result_status": rerun_status,
            "next_required_user_action": next_action,
            "profile_context": context,
            "workflow_state": dict(workflow_state or {}),
        }

        revised_item.metadata.update(
            {
                "critical_replanning": evidence,
                "revision_id": revision_id,
                "original_item_id": evidence["original_item_id"],
                "original_pool_id": pool.pool_id,
                "original_path_blocked": True,
                "created_from_critical_event": True,
                "gate_rerun_required_bool": True,
                "gate_rerun_performed": True,
                "rerun_critique_gate": critique_gate,
                "rerun_safety_gate": safety_gate,
                "rerun_result_status": rerun_status,
                "next_required_user_action": next_action,
                "safe_apply_allowed_before_gate_rerun": False,
            }
        )

        if original_item is not None:
            original_item.status = "needs_revision"
            original_item.auto_execution_allowed = False
            original_item.requires_user_confirmation = True
            original_item.metadata.update(
                {
                    "original_critical_path_rejected": True,
                    "original_path_blocked": True,
                    "executable": False,
                    "superseded_by_lower_impact_revision": revised_item.item_id,
                    "lower_impact_revised_item_id": revised_item.item_id,
                    "lower_impact_alternative": {
                        **alternative,
                        "item_id": revised_item.item_id,
                        "pool_id": pool.pool_id,
                        "metadata": revised_item.metadata,
                    },
                    "critical_replanning": evidence,
                }
            )

        pool.items.append(revised_item)
        pool.status = rerun_status
        pool.metadata.setdefault("critical_replanning", {})
        pool.metadata["critical_replanning"].update(evidence)
        pool.updated_at = _utc_now_iso()
        return {"revised_item": revised_item, **evidence}

    def _build_revised_item(
        self,
        *,
        pool: AtlasPlanPool,
        original_item: AtlasPlanItem | None,
        critical_event: dict[str, Any],
        alternative: dict[str, Any],
        revision_id: str,
    ) -> AtlasPlanItem:
        original_id = original_item.item_id if original_item else "pool"
        requested_item_id = str(alternative.get("item_id") or "").strip()
        existing_ids = set(pool.item_ids())
        if requested_item_id and requested_item_id not in existing_ids:
            item_id = requested_item_id
        else:
            item_id = f"{original_id}_lower_impact_{uuid4().hex[:8]}"
        metadata = {
            **dict(alternative.get("metadata") or {}),
            "source": "critical_decision_lower_impact_replan",
            "source_item_id": original_id if original_item else "",
            "original_critical_item_id": original_id if original_item else "",
            "critical_event": dict(critical_event or {}),
            "requires_critique_gate_rerun": True,
            "requires_policy_gate_rerun": True,
            "requires_safe_apply_gate_rerun": True,
            "gate_rerun_required": ["plan_critique_gate", "policy_gate", "safe_apply_gate"],
            "safe_apply_allowed_before_gate_rerun": False,
            "auto_execution_allowed": False,
            "lower_impact_revised_candidate": True,
            "revision_id": revision_id,
        }
        return AtlasPlanItem(
            item_id=item_id,
            pool_id=pool.pool_id,
            title=str(alternative.get("title") or f"Lower-impact revision for {getattr(original_item, 'title', pool.root_goal)}"),
            goal=str(alternative.get("goal") or getattr(original_item, "goal", pool.root_goal)),
            parent_plan_id=getattr(original_item, "parent_plan_id", ""),
            description=str(
                alternative.get("description")
                or "User rejected/NG the original critical path; gates reran for this lower-impact candidate before any mutation."
            ),
            item_type=getattr(original_item, "item_type", "implementation"),
            status="approval_required",
            priority=getattr(original_item, "priority", "medium"),
            risk_level=str(alternative.get("risk_level") or "medium"),
            depends_on=[],
            target_files=list(alternative.get("target_files") or []),
            expected_changes=list(alternative.get("expected_changes") or []),
            test_commands=list(alternative.get("test_commands") or []),
            done_definition=list(alternative.get("done_definition") or getattr(original_item, "done_definition", []) or []),
            rollback_plan=list(alternative.get("rollback_plan") or getattr(original_item, "rollback_plan", []) or []),
            requires_user_confirmation=True,
            auto_execution_allowed=False,
            linked_requirement_id=getattr(original_item, "linked_requirement_id", ""),
            linked_plan_id=getattr(original_item, "linked_plan_id", ""),
            linked_run_id=getattr(original_item, "linked_run_id", ""),
            metadata=metadata,
        )

    @staticmethod
    def _rerun_critique_gate(item: AtlasPlanItem, alternative: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        plan = {
            "requirement_summary": str(alternative.get("requirement_summary") or item.goal),
            "goal": item.goal,
            "selected_architecture": str(alternative.get("selected_architecture") or item.description),
            "adversarial_critique": dict(alternative.get("adversarial_critique") or {}),
        }
        return apply_plan_quality_gate(
            plan,
            automation_level=str(context.get("automation_level") or ""),
            preset_id=str(context.get("preset_id") or ""),
            critical_handling=str(context.get("critical_handling") or "ask"),
        )

    def _rerun_safety_gate(self, pool: AtlasPlanPool, item: AtlasPlanItem, context: dict[str, Any]) -> dict[str, Any]:
        preset_id = str(context.get("preset_id") or "manual_only")
        preset = atlas_auto_policy_presets().get(preset_id) or atlas_auto_policy_presets()["manual_only"]
        decision = self.safety_gate.decide_pre_safe_apply(pool, item, preset)
        if hasattr(decision, "model_dump"):
            return decision.model_dump()
        return decision.dict()

    @staticmethod
    def _resolve_rerun_status(
        *,
        critique_gate: dict[str, Any],
        safety_gate: dict[str, Any],
        profile_context: dict[str, Any],
    ) -> tuple[str, str]:
        safety_metadata = dict(safety_gate.get("metadata") or {})
        if critique_gate.get("critical_event") or safety_metadata.get("critical_event"):
            return "waiting_for_critical_decision", "User decision required for revised critical event."
        if critique_gate.get("plan_revision_required"):
            return "approval_required", "Review revised plan critique before continuing."
        if safety_gate.get("decision") == "allow" and bool(profile_context.get("bounded_envelope_active")):
            return "ready", "Revised candidate is ready within active bounded envelope."
        return "approval_required", "Review lower-impact revised candidate before any mutation."

    @staticmethod
    def _item_payload(item: AtlasPlanItem | None) -> dict[str, Any]:
        if item is None:
            return {}
        return {
            "item_id": item.item_id,
            "title": item.title,
            "status": item.status,
            "risk_level": item.risk_level,
            "item_type": item.item_type,
            "expected_changes": list(item.expected_changes),
            "requires_user_confirmation": item.requires_user_confirmation,
            "done_definition": list(item.done_definition),
            "rollback_plan": list(item.rollback_plan),
            "target_files": list(item.target_files),
            "metadata": dict(item.metadata or {}),
        }
