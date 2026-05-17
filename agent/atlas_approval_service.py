from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from agent.atlas_approval_gate import AtlasApprovalGate
from agent.atlas_journal import AtlasJournal
from agent.atlas_plan_pool_schema import AtlasPlanPool


class AtlasApprovalService:
    def __init__(self, journal: AtlasJournal):
        self.journal = journal

    def list_pool_approvals(self, pool: AtlasPlanPool) -> dict:
        records = self._load_records(pool.pool_id)
        required_items: list[dict] = []
        safe_apply_candidate_items: list[dict] = []
        pending_count = 0
        approved_count = 0
        rejected_count = 0
        needs_revision_count = 0

        for item in pool.items:
            payload = self._item_payload(item)
            decision = str(((payload.get("metadata") or {}).get("approval") or {}).get("decision") or "").strip().lower()
            requires_approval = (
                item.status in {"approval_required", "paused"}
                or bool(item.requires_user_confirmation)
                or (item.status == "ready" and bool(item.requires_user_confirmation) and not decision)
            )
            if decision == "approved":
                approved_count += 1
            elif decision == "rejected":
                rejected_count += 1
            elif decision == "needs_revision":
                needs_revision_count += 1

            action = str(((payload.get("metadata") or {}).get("action_type") or "")).strip().lower()
            is_candidate = (
                decision == "approved"
                and str(item.risk_level or "").lower() == "low"
                and item.item_type in {"implementation", "documentation"}
                and action not in {"delete", "run_command"}
                and item.status not in {"completed"}
            )
            if is_candidate:
                safe_apply_candidate_items.append(payload)

            if not requires_approval:
                continue
            if decision in {"approved", "rejected", "needs_revision"}:
                continue
            required_items.append(payload)
            pending_count += 1

        decided_item_ids = {
            item.item_id
            for item in pool.items
            if str(((item.metadata or {}).get("approval") or {}).get("decision") or "").strip().lower()
            in {"approved", "rejected", "needs_revision"}
        }
        for r in records:
            item_id = r.get("item_id")
            if item_id in decided_item_ids:
                continue
            if r.get("status") == "approved":
                approved_count += 1
            elif r.get("status") == "rejected":
                if ((r.get("metadata") or {}).get("decision") == "needs_revision"):
                    needs_revision_count += 1
                else:
                    rejected_count += 1
            elif r.get("status") == "needs_revision":
                needs_revision_count += 1

        return {
            "approval_required_items": required_items,
            "approval_records": records,
            "safe_apply_candidate_items": safe_apply_candidate_items,
            "pending_count": pending_count,
            "approved_count": approved_count,
            "rejected_count": rejected_count,
            "needs_revision_count": needs_revision_count,
            "warnings": [],
            "errors": [],
        }

    def decide(self, pool: AtlasPlanPool, *, item_id: str, run_id: str, decision: str, reason: str, approver: str, metadata: dict) -> dict:
        item = pool.get_item(item_id)
        if item is None:
            raise ValueError("item not found")
        if decision not in {"approved", "rejected", "needs_revision"}:
            raise ValueError("invalid decision")

        gate = AtlasApprovalGate()
        record = gate.request_approval(scope="item", pool_id=pool.pool_id, item_id=item_id, reason=reason, metadata=dict(metadata or {}))
        if decision == "approved":
            gate.approve(record.approval_id, decided_by=approver, reason=reason)
            if item.status in {"approval_required", "paused"}:
                item.status = "ready"
        elif decision == "rejected":
            gate.reject(record.approval_id, decided_by=approver, reason=reason)
            item.status = "blocked"
        else:
            gate.reject(record.approval_id, decided_by=approver, reason=reason)
            item.status = "needs_revision"

        item.metadata.setdefault("approval", {})
        existing = dict(item.metadata.get("approval") or {})
        raw_source = str(existing.get("source") or (item.metadata or {}).get("source") or "")
        source = "patch_proposal_planitem_draft" if raw_source == "patch_proposal" else raw_source
        source_item_id = str(existing.get("source_item_id") or (item.metadata or {}).get("source_item_id") or "")
        source_proposal_id = str(existing.get("source_proposal_id") or (item.metadata or {}).get("source_proposal_id") or "")
        item.metadata["approval"] = {
            **existing,
            "decision": decision,
            "reason": reason,
            "approver": approver,
            "approval_id": record.approval_id,
            "decided_at": record.decided_at,
            "source": source,
            "source_item_id": source_item_id,
            "source_proposal_id": source_proposal_id,
            "manual_only": True,
            "auto_safe_apply": False,
            "auto_verification": False,
            "auto_debug_review": False,
        }
        payload = record.model_dump()
        payload["run_id"] = run_id
        if decision == "needs_revision":
            payload["status"] = "rejected"
            payload["metadata"] = {**payload.get("metadata", {}), "decision": "needs_revision"}
        self._save_record(pool.pool_id, payload, item_title=item.title, risk_level=item.risk_level, target_files=item.target_files)
        return payload

    def _approvals_dir(self, pool_id: str) -> Path:
        return Path(self.journal.plan_pool_dir(pool_id)) / "approvals"

    def _load_records(self, pool_id: str) -> list[dict]:
        approvals_dir = self._approvals_dir(pool_id)
        if not approvals_dir.exists():
            return []
        rows = []
        for path in sorted(approvals_dir.glob("*.json")):
            rows.append(json.loads(path.read_text(encoding="utf-8")))
        return rows

    def _save_record(self, pool_id: str, record: dict, *, item_title: str, risk_level: str, target_files: list[str]) -> None:
        approvals_dir = self._approvals_dir(pool_id)
        approvals_dir.mkdir(parents=True, exist_ok=True)
        approval_id = str(record.get("approval_id") or f"atlas_approval_{uuid4().hex}")
        record_path = approvals_dir / f"{approval_id}.json"
        record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        md = (
            f"# Atlas Approval\n\n- Approval ID: {approval_id}\n- Pool ID: {record.get('pool_id','')}\n"
            f"- Item ID: {record.get('item_id','')}\n- Run ID: {record.get('run_id','')}\n"
            f"- Decision: {record.get('status','')}\n- Reason: {record.get('reason','')}\n"
            f"- Approver: {record.get('decided_by','')}\n- Created at: {record.get('created_at','')}\n"
            f"- Item title: {item_title}\n- Risk level: {risk_level}\n- Target files: {', '.join(target_files or [])}\n"
        )
        (approvals_dir / f"{approval_id}.md").write_text(md, encoding="utf-8")

    @staticmethod
    def _item_payload(item) -> dict:
        return {
            "item_id": item.item_id,
            "title": item.title,
            "status": item.status,
            "risk_level": item.risk_level,
            "item_type": item.item_type,
            "expected_changes": item.expected_changes,
            "requires_user_confirmation": item.requires_user_confirmation,
            "done_definition": item.done_definition,
            "rollback_plan": item.rollback_plan,
            "target_files": list(item.target_files),
            "metadata": dict(item.metadata or {}),
        }
