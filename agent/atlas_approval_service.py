from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from agent.atlas_approval_gate import AtlasApprovalGate
from agent.atlas_critical_replanning_service import AtlasCriticalReplanningService
from agent.atlas_critical_event_policy import lower_impact_alternative_plan
from agent.atlas_journal import AtlasJournal
from agent.atlas_plan_pool_schema import AtlasPlanPool

POOL_CRITICAL_DECISION_ITEM_ID = "__pool_critical_decision__"


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

        pool_critical_event = dict((pool.metadata or {}).get("critical_event") or {})
        pool_decision = str(((pool.metadata or {}).get("critical_decision") or {}).get("decision") or "").strip().lower()
        pool_requires_decision = (
            pool.status == "waiting_for_critical_decision"
            or bool(pool_critical_event.get("critical_event"))
        ) and pool_decision not in {"approved", "rejected_ng_safer_replan", "cancelled", "edit_scope_requested"}
        if pool_requires_decision:
            required_items.append(self._pool_critical_payload(pool, pool_critical_event))
            pending_count += 1

        for item in pool.items:
            payload = self._item_payload(item)
            decision = str(((payload.get("metadata") or {}).get("approval") or {}).get("decision") or "").strip().lower()
            requires_approval = (
                item.status in {"approval_required", "paused", "waiting_for_critical_decision"}
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

    def decide_pool_critical(self, pool: AtlasPlanPool, *, run_id: str, decision: str, reason: str, approver: str, metadata: dict) -> dict:
        if decision not in {"approved", "rejected", "needs_revision", "cancelled"}:
            raise ValueError("invalid decision")
        critical_event = dict((pool.metadata or {}).get("critical_event") or (metadata or {}).get("critical_event") or {})
        if not critical_event.get("critical_event"):
            raise ValueError("pool critical event not found")

        gate = AtlasApprovalGate()
        record = gate.request_approval(
            scope="pool",
            pool_id=pool.pool_id,
            item_id="",
            reason=reason,
            metadata={**dict(metadata or {}), "critical_event": critical_event},
        )
        if decision == "approved":
            gate.approve(record.approval_id, decided_by=approver, reason=reason)
            pool.status = "approval_required"
            normalized_decision = "approved"
        elif decision == "rejected":
            gate.reject(record.approval_id, decided_by=approver, reason=reason)
            normalized_decision = "rejected_ng_safer_replan"
            alternative = lower_impact_alternative_plan(
                {
                    "title": f"Lower-impact revision for {pool.root_goal}",
                    "goal": pool.root_goal,
                    "risk_level": "critical",
                    "target_files": list(critical_event.get("affected_files") or [])[:1],
                    "metadata": {},
                },
                critical_event,
            )
            profile_context = {
                **dict((pool.metadata or {}).get("automation_features") or {}),
                **dict((metadata or {}).get("profile_context") or {}),
                "preset_id": (metadata or {}).get("preset_id") or (pool.metadata or {}).get("preset_id") or "",
                "automation_level": (metadata or {}).get("automation_level") or getattr(pool, "automation_level", ""),
                "bounded_envelope_active": bool(
                    (metadata or {}).get("bounded_envelope_active")
                    or ((pool.metadata or {}).get("pre_authorized_envelope") or {}).get("envelope_active")
                ),
            }
            replanning = AtlasCriticalReplanningService().create_lower_impact_revision(
                pool=pool,
                original_item=None,
                critical_event=critical_event,
                user_decision_record={
                    "decision": normalized_decision,
                    "reason": reason,
                    "approver": approver,
                    "approval_id": record.approval_id,
                },
                lower_impact_alternative=alternative,
                profile_context=profile_context,
                workflow_state=dict((pool.metadata or {}).get("workflow_state") or {}),
            )
            pool.metadata["critical_replanning"] = {
                key: value for key, value in replanning.items() if key != "revised_item"
            }
        elif decision == "cancelled":
            gate.revoke(record.approval_id, decided_by=approver, reason=reason)
            pool.status = "cancelled"
            normalized_decision = "cancelled"
        else:
            gate.reject(record.approval_id, decided_by=approver, reason=reason)
            pool.status = "approval_required"
            normalized_decision = "edit_scope_requested"

        approved_files = self._approved_files_for_pool_critical(critical_event, metadata)
        approved_item_ids = [
            str(item_id)
            for item_id in (
                (metadata or {}).get("approved_item_ids")
                or (metadata or {}).get("approved_items")
                or []
            )
            if str(item_id).strip()
        ]
        approved_capabilities = [
            str(capability)
            for capability in (
                (metadata or {}).get("approved_capabilities")
                or critical_event.get("affected_capabilities")
                or []
            )
            if str(capability).strip()
        ]
        bounded_continuation = normalized_decision == "approved"
        pool.metadata["critical_decision"] = {
            "scope": "pool",
            "decision": normalized_decision,
            "reason": reason,
            "approver": approver,
            "approval_id": record.approval_id,
            "critical_event": critical_event,
            "original_path_blocked": normalized_decision == "rejected_ng_safer_replan",
            "approved_scope": approved_files if bounded_continuation else [],
            "approved_files": approved_files if bounded_continuation else [],
            "approved_paths": approved_files if bounded_continuation else [],
            "approved_item_ids": approved_item_ids if bounded_continuation else [],
            "approved_capabilities": approved_capabilities if bounded_continuation else [],
            "bounded_continuation": bounded_continuation,
            "one_action_only": not bounded_continuation,
            "next_required_user_action": self._pool_next_action(normalized_decision),
        }
        payload = record.model_dump()
        payload["run_id"] = run_id
        payload["item_id"] = POOL_CRITICAL_DECISION_ITEM_ID
        payload["metadata"] = {
            **payload.get("metadata", {}),
            "scope": "pool",
            "decision": normalized_decision,
            "critical_event": critical_event,
            "critical_replanning": pool.metadata.get("critical_replanning") or {},
            "approved_scope": pool.metadata["critical_decision"]["approved_scope"],
            "approved_files": pool.metadata["critical_decision"]["approved_files"],
            "approved_paths": pool.metadata["critical_decision"]["approved_paths"],
            "approved_item_ids": pool.metadata["critical_decision"]["approved_item_ids"],
            "approved_capabilities": pool.metadata["critical_decision"]["approved_capabilities"],
            "bounded_continuation": pool.metadata["critical_decision"]["bounded_continuation"],
            "one_action_only": pool.metadata["critical_decision"]["one_action_only"],
            "next_required_user_action": pool.metadata["critical_decision"]["next_required_user_action"],
        }
        self._save_record(
            pool.pool_id,
            payload,
            item_title=f"Pool critical decision: {pool.root_goal}",
            risk_level=str(critical_event.get("severity") or "critical"),
            target_files=list(critical_event.get("affected_files") or []),
        )
        return payload

    def decide(self, pool: AtlasPlanPool, *, item_id: str, run_id: str, decision: str, reason: str, approver: str, metadata: dict) -> dict:
        item = pool.get_item(item_id)
        if item is None:
            raise ValueError("item not found")
        if decision not in {"approved", "rejected", "needs_revision", "cancelled"}:
            raise ValueError("invalid decision")

        gate = AtlasApprovalGate()
        record = gate.request_approval(scope="item", pool_id=pool.pool_id, item_id=item_id, reason=reason, metadata=dict(metadata or {}))
        critical_event = dict((item.metadata or {}).get("critical_event") or (metadata or {}).get("critical_event") or {})
        if decision == "approved":
            gate.approve(record.approval_id, decided_by=approver, reason=reason)
            if item.status in {"approval_required", "paused", "waiting_for_critical_decision"}:
                item.status = "ready"
        elif decision == "rejected":
            gate.reject(record.approval_id, decided_by=approver, reason=reason)
            if critical_event.get("critical_event"):
                item.status = "needs_revision"
                item.auto_execution_allowed = False
                item.metadata["original_critical_path_rejected"] = True
                item.metadata["executable"] = False
                item.metadata["lower_impact_alternative"] = lower_impact_alternative_plan(self._item_payload(item), critical_event)
                profile_context = {
                    **dict((pool.metadata or {}).get("automation_features") or {}),
                    **dict((metadata or {}).get("profile_context") or {}),
                    "preset_id": (metadata or {}).get("preset_id") or (pool.metadata or {}).get("preset_id") or "",
                    "automation_level": (metadata or {}).get("automation_level") or getattr(pool, "automation_level", ""),
                    "bounded_envelope_active": bool(
                        (metadata or {}).get("bounded_envelope_active")
                        or ((pool.metadata or {}).get("pre_authorized_envelope") or {}).get("envelope_active")
                    ),
                }
                replanning = AtlasCriticalReplanningService().create_lower_impact_revision(
                    pool=pool,
                    original_item=item,
                    critical_event=critical_event,
                    user_decision_record={
                        "decision": "rejected_ng_safer_replan",
                        "reason": reason,
                        "approver": approver,
                        "approval_id": record.approval_id,
                    },
                    lower_impact_alternative=item.metadata["lower_impact_alternative"],
                    profile_context=profile_context,
                    workflow_state=dict((pool.metadata or {}).get("workflow_state") or {}),
                )
                item.metadata["critical_replanning"] = {
                    key: value for key, value in replanning.items() if key != "revised_item"
                }
            else:
                item.status = "blocked"
        elif decision == "cancelled":
            # User cancelled the plan/item: revoke the approval request and stop the item.
            gate.revoke(record.approval_id, decided_by=approver, reason=reason)
            item.status = "cancelled"
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
            "critical_event": critical_event or existing.get("critical_event") or {},
            "approved_scope": list((metadata or {}).get("approved_scope") or item.target_files or []),
            "approved_files": list((metadata or {}).get("approved_files") or item.target_files or []),
            "approved_capabilities": list((metadata or {}).get("approved_capabilities") or (critical_event.get("affected_capabilities") if critical_event else []) or []),
            "bounded_continuation": bool((metadata or {}).get("bounded_continuation", False)),
            "one_action_only": not bool((metadata or {}).get("bounded_continuation", False)),
            "auto_safe_apply": False,
            "auto_verification": False,
            "auto_debug_review": False,
        }
        payload = record.model_dump()
        payload["run_id"] = run_id
        if decision == "needs_revision" or (decision == "rejected" and critical_event.get("critical_event")):
            payload["status"] = "rejected"
            payload["metadata"] = {
                **payload.get("metadata", {}),
                "decision": "needs_revision" if decision == "needs_revision" else "rejected_ng_safer_replan",
                "critical_event": critical_event,
                "lower_impact_alternative": item.metadata.get("lower_impact_alternative") or {},
                "critical_replanning": item.metadata.get("critical_replanning") or {},
            }
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

    @staticmethod
    def _pool_critical_payload(pool: AtlasPlanPool, critical_event: dict) -> dict:
        return {
            "scope": "pool",
            "item_id": POOL_CRITICAL_DECISION_ITEM_ID,
            "pool_id": pool.pool_id,
            "title": "Pool-level critical event",
            "status": "waiting_for_critical_decision",
            "risk_level": str(critical_event.get("severity") or "critical"),
            "item_type": "planning",
            "target_files": list(critical_event.get("affected_files") or []),
            "requires_user_confirmation": True,
            "metadata": {
                "scope": "pool",
                "critical_event": critical_event,
                "required_options": list(critical_event.get("required_options") or []),
                "safer_alternatives": list(critical_event.get("safer_alternatives") or []),
                "recommended_decision": str(critical_event.get("recommended_decision") or ""),
                "next_required_user_action": "Decide pool-level critical event before continuing.",
            },
        }

    @staticmethod
    def _approved_files_for_pool_critical(critical_event: dict, metadata: dict) -> list[str]:
        raw = (
            (metadata or {}).get("approved_files")
            or (metadata or {}).get("approved_scope")
            or (metadata or {}).get("approved_paths")
            or critical_event.get("affected_files")
            or []
        )
        out: list[str] = []
        for path in raw:
            text = str(path or "").replace("\\", "/")
            if text and text not in out:
                out.append(text)
        return out

    @staticmethod
    def _pool_next_action(decision: str) -> str:
        if decision == "approved":
            return "Continue only inside the approved bounded pool scope."
        if decision == "rejected_ng_safer_replan":
            return "Review lower-impact pool revision before any mutation."
        if decision == "edit_scope_requested":
            return "Edit requirement or scope, then rerun plan gates."
        if decision == "cancelled":
            return "Pool critical path cancelled."
        return "Decide pool-level critical event before continuing."
