from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from agent.plan_approval_schema import PlanApprovalRecord
from agent.plan_storage import PlanStorage


class PlanApprovalManager:
    def __init__(self, storage: PlanStorage) -> None:
        self.storage = storage

    def get_latest_approval(self, plan_id: str) -> dict:
        plan = self.storage.load_plan(plan_id)
        approval = self.storage.find_latest_approval_for_plan(plan_id)
        if approval is None:
            return {"plan_id": plan_id, "approval": None, "status": "pending", "execution_ready": False}
        return {
            "plan_id": plan_id,
            "approval": approval,
            "status": approval.get("status", "pending"),
            "execution_ready": bool(approval.get("execution_ready", False)),
        }

    def decide(
        self,
        plan_id: str,
        decision: str,
        user_comment: str = "",
        revision_request: str = "",
        risk_acknowledged: bool = False,
        destructive_change_acknowledged: bool = False,
        approved_by: str = "user",
    ) -> dict:
        if decision not in {"approve", "request_revision", "reject"}:
            raise ValueError("invalid decision")

        plan_payload = self.storage.load_plan(plan_id)
        plan_status = str(plan_payload.get("status", "planned"))
        review = plan_payload.get("review_result") or {}
        review_risk = str(review.get("overall_risk", "low")).lower()
        requires_confirmation = bool(review.get("requires_user_confirmation", False))
        destructive_change_detected = bool(plan_payload.get("destructive_change_detected", False))
        recommended_action = str(review.get("recommended_next_action", "proceed"))
        review_id = str(review.get("review_id", ""))

        if decision == "approve":
            if plan_status not in {"planned", "needs_confirmation"}:
                raise ValueError(f"plan status '{plan_status}' cannot be approved")
            if not review:
                raise ValueError("review_result is required for approve")
            if recommended_action == "reject_plan":
                raise ValueError("plan cannot be approved because review recommended reject_plan")
            if review_risk in {"high", "critical"} and not risk_acknowledged:
                raise ValueError("risk_acknowledged is required for high/critical risk plan")
            if destructive_change_detected and not destructive_change_acknowledged:
                raise ValueError("destructive_change_acknowledged is required for destructive change plan")
            approval_status = "approved"
            execution_ready = True
            approved_for_execution = True
            new_plan_status = "execution_ready"

        elif decision == "request_revision":
            if plan_status not in {"planned", "needs_confirmation", "needs_revision"}:
                raise ValueError(f"plan status '{plan_status}' cannot request revision")
            approval_status = "revision_requested"
            execution_ready = False
            approved_for_execution = False
            new_plan_status = "revision_requested"

        else:
            approval_status = "rejected"
            execution_ready = False
            approved_for_execution = False
            new_plan_status = "rejected"

        now = datetime.now(timezone.utc).isoformat()
        approval = PlanApprovalRecord(
            approval_id=f"approval_{uuid4().hex[:12]}",
            plan_id=plan_id,
            requirement_id=str(plan_payload.get("requirement_id", "")),
            review_id=review_id,
            created_at=now,
            updated_at=now,
            status=approval_status,
            decision=decision,
            approved_for_execution=approved_for_execution,
            approved_by=approved_by,
            user_comment=user_comment,
            revision_request=revision_request,
            risk_acknowledged=bool(risk_acknowledged),
            destructive_change_acknowledged=bool(destructive_change_acknowledged),
            review_overall_risk=review_risk,
            requires_user_confirmation=requires_confirmation,
            execution_ready=execution_ready,
            warnings=[],
            metadata={"phase": "phase5", "approved_but_not_executed": True},
        )
        self.storage.save_approval(approval)

        plan_payload["status"] = new_plan_status
        plan_payload["updated_at"] = now
        plan_payload["approval"] = approval.model_dump()
        self.storage.save_plan_payload(plan_payload)

        return {
            "plan_id": plan_id,
            "approval_id": approval.approval_id,
            "status": new_plan_status,
            "approval": approval.model_dump(),
            "plan": plan_payload,
            "message": "Plan approved and marked execution_ready. No implementation was executed in Phase 5."
            if decision == "approve"
            else "Plan decision saved. No implementation was executed in Phase 5.",
            "warnings": [],
        }
