from __future__ import annotations

from typing import Any
from uuid import uuid4

from agent.atlas_approval_schema import (
    AtlasApprovalRecord,
    AtlasApprovalScope,
    AtlasApprovalSnapshot,
    AtlasApprovalStatus,
    _utc_now_iso,
)


class AtlasApprovalGate:
    def __init__(self, records: list[AtlasApprovalRecord] | None = None):
        self.records: list[AtlasApprovalRecord] = list(records or [])

    def request_approval(
        self,
        scope: AtlasApprovalScope,
        pool_id: str = "",
        item_id: str = "",
        patch_id: str = "",
        policy_evaluation: Any | None = None,
        reason: str = "",
        metadata: dict | None = None,
    ) -> AtlasApprovalRecord:
        self._validate_scope_target(scope=scope, pool_id=pool_id, item_id=item_id, patch_id=patch_id)

        policy_decision = self._policy_attr(policy_evaluation, "decision", "")
        policy_reasons = list(self._policy_attr(policy_evaluation, "reasons", []) or [])
        policy_categories = list(self._policy_attr(policy_evaluation, "categories", []) or [])
        resolved_reason = reason or "; ".join(str(value) for value in policy_reasons)
        record_metadata = dict(metadata or {})
        if policy_evaluation is not None:
            record_metadata["policy_evaluation"] = self._policy_metadata(policy_evaluation)

        record = AtlasApprovalRecord(
            approval_id=f"atlas_approval_{uuid4().hex}",
            scope=scope,
            status="pending",
            pool_id=pool_id,
            item_id=item_id,
            patch_id=patch_id,
            reason=resolved_reason,
            policy_decision=str(policy_decision or ""),
            policy_reasons=[str(value) for value in policy_reasons],
            policy_categories=[str(value) for value in policy_categories],
            metadata=record_metadata,
        )
        self.records.append(record)
        return record

    def approve(self, approval_id: str, decided_by: str = "user", reason: str = "") -> AtlasApprovalRecord:
        return self._decide(approval_id=approval_id, status="approved", decided_by=decided_by, reason=reason)

    def reject(self, approval_id: str, decided_by: str = "user", reason: str = "") -> AtlasApprovalRecord:
        return self._decide(approval_id=approval_id, status="rejected", decided_by=decided_by, reason=reason)

    def revoke(self, approval_id: str, decided_by: str = "user", reason: str = "") -> AtlasApprovalRecord:
        return self._decide(approval_id=approval_id, status="revoked", decided_by=decided_by, reason=reason)

    def get_record(self, approval_id: str) -> AtlasApprovalRecord | None:
        for record in self.records:
            if record.approval_id == approval_id:
                return record
        return None

    def find_records(
        self,
        scope: AtlasApprovalScope | None = None,
        pool_id: str = "",
        item_id: str = "",
        patch_id: str = "",
        status: AtlasApprovalStatus | None = None,
    ) -> list[AtlasApprovalRecord]:
        matched: list[AtlasApprovalRecord] = []
        for record in self.records:
            if scope is not None and record.scope != scope:
                continue
            if pool_id and record.pool_id != pool_id:
                continue
            if item_id and record.item_id != item_id:
                continue
            if patch_id and record.patch_id != patch_id:
                continue
            if status is not None and record.status != status:
                continue
            matched.append(record)
        return matched

    def is_pool_approved(self, pool_id: str) -> bool:
        return any(
            record.status == "approved"
            for record in self.find_records(scope="pool", pool_id=pool_id, status="approved")
        )

    def is_item_approved(self, pool_id: str, item_id: str) -> bool:
        return any(
            record.status == "approved"
            for record in self.find_records(scope="item", pool_id=pool_id, item_id=item_id, status="approved")
        )

    def is_patch_approved(self, pool_id: str, item_id: str, patch_id: str) -> bool:
        return any(
            record.status == "approved"
            for record in self.find_records(
                scope="patch",
                pool_id=pool_id,
                item_id=item_id,
                patch_id=patch_id,
                status="approved",
            )
        )

    def snapshot(self, pool_id: str) -> AtlasApprovalSnapshot:
        records = self.find_records(pool_id=pool_id)
        return AtlasApprovalSnapshot(
            pool_id=pool_id,
            records=records,
            approved_pool=any(record.scope == "pool" and record.status == "approved" for record in records),
            approved_item_ids=self._dedupe(
                [record.item_id for record in records if record.scope == "item" and record.status == "approved"]
            ),
            approved_patch_ids=self._dedupe(
                [record.patch_id for record in records if record.scope == "patch" and record.status == "approved"]
            ),
            pending_item_ids=self._dedupe(
                [record.item_id for record in records if record.scope == "item" and record.status == "pending"]
            ),
            rejected_item_ids=self._dedupe(
                [record.item_id for record in records if record.scope == "item" and record.status == "rejected"]
            ),
            metadata={
                "total_records": len(records),
                "pending_count": self._count_status(records, "pending"),
                "approved_count": self._count_status(records, "approved"),
                "rejected_count": self._count_status(records, "rejected"),
                "revoked_count": self._count_status(records, "revoked"),
            },
        )

    def _decide(
        self,
        approval_id: str,
        status: AtlasApprovalStatus,
        decided_by: str,
        reason: str,
    ) -> AtlasApprovalRecord:
        record = self.get_record(approval_id)
        if record is None:
            raise KeyError(f"approval_id not found: {approval_id}")
        now = _utc_now_iso()
        record.status = status
        record.decided_by = decided_by
        record.decided_at = now
        record.updated_at = now
        if reason:
            record.reason = reason
        return record

    @staticmethod
    def _validate_scope_target(scope: AtlasApprovalScope, pool_id: str, item_id: str, patch_id: str) -> None:
        if scope == "pool" and not pool_id:
            raise ValueError("pool approval requires pool_id")
        if scope == "item" and (not pool_id or not item_id):
            raise ValueError("item approval requires pool_id and item_id")
        if scope == "patch" and (not pool_id or not item_id or not patch_id):
            raise ValueError("patch approval requires pool_id, item_id, and patch_id")

    @staticmethod
    def _policy_attr(policy_evaluation: Any | None, field_name: str, default: Any) -> Any:
        if policy_evaluation is None:
            return default
        if isinstance(policy_evaluation, dict):
            return policy_evaluation.get(field_name, default)
        return getattr(policy_evaluation, field_name, default)

    def _policy_metadata(self, policy_evaluation: Any) -> dict[str, Any]:
        if isinstance(policy_evaluation, dict):
            return dict(policy_evaluation)
        if hasattr(policy_evaluation, "model_dump"):
            return policy_evaluation.model_dump()
        if hasattr(policy_evaluation, "dict"):
            return policy_evaluation.dict()
        return {
            "decision": self._policy_attr(policy_evaluation, "decision", ""),
            "reasons": list(self._policy_attr(policy_evaluation, "reasons", []) or []),
            "categories": list(self._policy_attr(policy_evaluation, "categories", []) or []),
        }

    @staticmethod
    def _count_status(records: list[AtlasApprovalRecord], status: AtlasApprovalStatus) -> int:
        return sum(1 for record in records if record.status == status)

    @staticmethod
    def _dedupe(values: list[str]) -> list[str]:
        deduped: list[str] = []
        for value in values:
            if value and value not in deduped:
                deduped.append(value)
        return deduped
