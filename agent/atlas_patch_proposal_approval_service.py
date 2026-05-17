from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agent.atlas_journal import AtlasJournal
from agent.atlas_patch_proposal_approval_schema import (
    AtlasPatchProposalApprovalRecord,
    AtlasPatchProposalApprovalRequest,
    AtlasPatchProposalApprovalResult,
)
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage


class AtlasPatchProposalApprovalService:
    ALLOWED_DECISIONS = {"approved", "rejected", "needs_revision"}

    def __init__(self, *, journal: AtlasJournal, storage: AtlasPlanPoolStorage):
        self.journal = journal
        self.storage = storage

    def decide(self, request: AtlasPatchProposalApprovalRequest) -> AtlasPatchProposalApprovalResult:
        pool = self.storage.load_pool(request.pool_id)
        item = pool.get_item(request.item_id)
        self._append_event(pool.pool_id, request.run_id, "patch_proposal_approval_manual_started", request.item_id, "started")
        if item is None:
            warnings = ["item_not_found"]
            self._append_event(pool.pool_id, request.run_id, "patch_proposal_approval_manual_blocked", request.item_id, "blocked", warnings=warnings)
            return AtlasPatchProposalApprovalResult(pool_id=pool.pool_id, item_id=request.item_id, proposal_id=request.proposal_id, status="blocked", warnings=warnings, plan_pool=pool.model_dump())
        ok, warnings = self.validate_patch_proposal_decision(pool, item, request)
        if not ok:
            self._append_event(pool.pool_id, request.run_id, "patch_proposal_approval_manual_blocked", item.item_id, "blocked", warnings=warnings)
            return AtlasPatchProposalApprovalResult(pool_id=pool.pool_id, item_id=item.item_id, proposal_id=request.proposal_id, status="blocked", warnings=warnings, plan_pool=pool.model_dump())
        try:
            record = self.build_approval_record(pool, item, request)
            json_path, md_path = self.save_approval_record(pool.pool_id, item.item_id, record)
            result = AtlasPatchProposalApprovalResult(pool_id=pool.pool_id, item_id=item.item_id, proposal_id=record.proposal_id, status=request.decision, approval_record=record, metadata={"approval_json_path": json_path, "approval_md_path": md_path})
            self.mark_item_from_approval(pool, item, result)
            self.storage.save_pool(pool)
            self.journal.save_plan_pool(pool)
            self._append_event(pool.pool_id, request.run_id, "patch_proposal_approval_manual_decided", item.item_id, request.decision)
            result.plan_pool = pool.model_dump()
            return result
        except Exception as exc:
            errors = [str(exc) or exc.__class__.__name__]
            self._append_event(pool.pool_id, request.run_id, "patch_proposal_approval_manual_failed", item.item_id, "failed", errors=errors)
            return AtlasPatchProposalApprovalResult(pool_id=pool.pool_id, item_id=item.item_id, proposal_id=request.proposal_id, status="failed", errors=errors, plan_pool=pool.model_dump())

    def validate_patch_proposal_decision(self, pool, item, request) -> tuple[bool, list[str]]:
        warnings: list[str] = []
        patch = dict((item.metadata or {}).get("patch_proposal") or {})
        if not patch:
            warnings.append("patch_proposal_not_found")
            return False, warnings
        if request.decision not in self.ALLOWED_DECISIONS:
            warnings.append("decision_not_allowed")
        status = str(patch.get("status") or "").lower()
        if status != "proposed":
            if status in {"approved", "applied"} and request.decision == "needs_revision":
                pass
            elif status in {"approved", "applied"}:
                warnings.append("patch_proposal_approval_blocked")
            else:
                warnings.append("patch_proposal_not_proposed")
        req_pid = str(request.proposal_id or "").strip()
        item_pid = str(patch.get("proposal_id") or "").strip()
        if req_pid and req_pid != item_pid:
            warnings.append("proposal_id_mismatch")
        if not str(patch.get("proposal_md_path") or "") and not str(patch.get("proposal_json_path") or ""):
            warnings.append("patch_proposal_approval_blocked")
        return len(warnings) == 0, warnings

    def build_approval_record(self, pool, item, request) -> AtlasPatchProposalApprovalRecord:
        patch = dict((item.metadata or {}).get("patch_proposal") or {})
        return AtlasPatchProposalApprovalRecord(
            approval_id=f"patch_proposal_approval_{uuid4().hex}",
            pool_id=pool.pool_id,
            item_id=item.item_id,
            proposal_id=str(patch.get("proposal_id") or request.proposal_id or ""),
            run_id=request.run_id,
            decision=request.decision,
            reason=request.reason,
            approver=request.approver,
            decided_at=datetime.now(timezone.utc).isoformat(),
            proposal_summary=str(patch.get("summary") or ""),
            proposal_risk_level=str(patch.get("risk_level") or ""),
            proposal_md_path=str(patch.get("proposal_md_path") or ""),
            metadata=dict(request.metadata or {}),
        )

    def save_approval_record(self, pool_id, item_id, record) -> tuple[str, str]:
        ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        out_dir = Path(self.journal.paths(pool_id=pool_id).plan_pool_json).parent / "patch_proposal_approvals"
        out_dir.mkdir(parents=True, exist_ok=True)
        json_path = out_dir / f"{item_id}_{ts}.json"
        md_path = out_dir / f"{item_id}_{ts}.md"
        json_path.write_text(json.dumps(record.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
        md = f"# Atlas Patch Proposal Approval\n\n- Approval ID: {record.approval_id}\n- Pool ID: {record.pool_id}\n- Item ID: {record.item_id}\n- Proposal ID: {record.proposal_id}\n- Decision: {record.decision}\n- Reason: {record.reason}\n- Approver: {record.approver}\n- Proposal summary: {record.proposal_summary}\n- Proposal risk level: {record.proposal_risk_level}\n- Proposal MD path: {record.proposal_md_path}\n\n- No patch was applied.\n- No safe_apply was run.\n- No verification rerun was performed.\n"
        md_path.write_text(md, encoding="utf-8")
        return str(json_path), str(md_path)

    def mark_item_from_approval(self, pool, item, result) -> None:
        patch = (item.metadata or {}).setdefault("patch_proposal", {})
        appr = (item.metadata or {}).setdefault("patch_proposal_approval", {})
        appr.update({
            "decision": result.status,
            "reason": result.approval_record.reason if result.approval_record else "",
            "approver": result.approval_record.approver if result.approval_record else "",
            "approval_id": result.approval_record.approval_id if result.approval_record else "",
            "decided_at": result.approval_record.decided_at if result.approval_record else "",
            "approval_md_path": str((result.metadata or {}).get("approval_md_path") or ""),
        })
        patch["status"] = result.status

    def _append_event(self, pool_id: str, run_id: str, event_type: str, item_id: str, status: str, warnings: list[str] | None = None, errors: list[str] | None = None) -> None:
        if not run_id:
            return
        self.journal.append_event(pool_id, run_id, {"event_type": event_type, "pool_id": pool_id, "run_id": run_id, "item_id": item_id, "status": status, "warnings": list(warnings or []), "errors": list(errors or []), "created_at": datetime.now(timezone.utc).isoformat()})
