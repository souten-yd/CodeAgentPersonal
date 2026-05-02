from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from agent.patch_approval_schema import PatchApprovalRecord
from agent.patch_storage import PatchStorage


class PatchApprovalManager:
    def __init__(self, patch_storage: PatchStorage) -> None:
        self.patch_storage = patch_storage

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def decide(
        self,
        run_id: str,
        patch_id: str,
        decision: str,
        user_comment: str = "",
        risk_acknowledged: bool = False,
        safety_warnings_acknowledged: bool = False,
        approved_by: str = "user",
    ) -> dict:
        patch = self.patch_storage.load_patch(run_id, patch_id)
        if bool(patch.get("applied", False)):
            raise ValueError("patch already applied")
        if decision not in {"approve", "reject"}:
            raise ValueError("decision must be approve or reject")
        latest = self.patch_storage.find_latest_patch_approval(run_id, patch_id)
        if latest is not None:
            if latest.status in {"rejected", "applied"}:
                raise ValueError(f"{latest.status} patch cannot be modified")
            if latest.status == "approved" and decision == "reject":
                raise ValueError("approved patch cannot be rejected; generate a new patch proposal")

        risk_level = str(patch.get("risk_level", "low")).lower()
        warnings = [str(x) for x in (patch.get("safety_warnings") or [])]
        apply_allowed = bool(patch.get("apply_allowed", False))

        if decision == "approve":
            if not apply_allowed:
                raise ValueError("apply_allowed=false patch cannot be approved")
            if warnings and not safety_warnings_acknowledged:
                raise ValueError("safety warnings acknowledgment is required")
            if risk_level in {"medium", "high"} and not risk_acknowledged:
                raise ValueError("risk acknowledgment is required for medium/high risk patch")

        status = "approved" if decision == "approve" else "rejected"
        record = PatchApprovalRecord(
            patch_approval_id=f"pa_{uuid4().hex[:12]}",
            patch_id=patch_id,
            run_id=run_id,
            plan_id=str(patch.get("plan_id", "")),
            step_id=str(patch.get("step_id", "")),
            target_file=str(patch.get("target_file", "")),
            updated_at=self._now(),
            status=status,
            decision=decision,
            approved_by=approved_by,
            user_comment=user_comment,
            risk_acknowledged=bool(risk_acknowledged),
            safety_warnings_acknowledged=bool(safety_warnings_acknowledged),
            apply_allowed_at_approval=apply_allowed,
            approved_for_apply=(decision == "approve"),
            applied=False,
            warnings=warnings,
            metadata={"risk_level": risk_level},
        )
        self.patch_storage.save_patch_approval(record)
        self.patch_storage.update_patch_payload(
            run_id,
            patch_id,
            {
                "approval_status": record.status,
                "approved_for_apply": record.approved_for_apply,
                "patch_approval_id": record.patch_approval_id,
            },
        )
        return {"run_id": run_id, "patch_id": patch_id, "approval": record.model_dump(), "message": f"patch {decision}d"}

    def require_approved_for_apply(self, run_id: str, patch_id: str) -> PatchApprovalRecord:
        latest = self.patch_storage.find_latest_patch_approval(run_id, patch_id)
        if latest is None:
            raise ValueError("patch approval is required before apply")
        if latest.status == "rejected":
            raise ValueError("rejected patch cannot be applied")
        if latest.status != "approved" or not latest.approved_for_apply:
            raise ValueError("approved patch approval is required before apply")
        return latest

    def mark_applied(self, run_id: str, patch_id: str, apply_result: dict, verification_id: str = "", verification_status: str = "", verification_summary: str = "") -> PatchApprovalRecord:
        latest = self.require_approved_for_apply(run_id, patch_id)
        latest.status = "applied"
        latest.applied = True
        latest.updated_at = self._now()
        latest.metadata = {
            **(latest.metadata or {}),
            "apply_result": apply_result,
            "verification_id": verification_id,
            "verification_status": verification_status,
            "verification_summary": verification_summary,
        }
        self.patch_storage.save_patch_approval(latest)
        self.patch_storage.update_patch_payload(
            run_id,
            patch_id,
            {
                "approval_status": latest.status,
                "approved_for_apply": latest.approved_for_apply,
                "patch_approval_id": latest.patch_approval_id,
                "applied": True,
                "status": "applied",
            },
        )
        return latest
