from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


AtlasApprovalScope = Literal["pool", "item", "patch"]
AtlasApprovalStatus = Literal["pending", "approved", "rejected", "expired", "revoked"]
AtlasApprovalDecision = Literal["approve", "reject", "revoke"]


class AtlasApprovalRecord(BaseModel):
    approval_id: str
    scope: AtlasApprovalScope
    status: AtlasApprovalStatus = "pending"
    pool_id: str = ""
    item_id: str = ""
    patch_id: str = ""
    requested_by: str = "system"
    decided_by: str = ""
    reason: str = ""
    policy_decision: str = ""
    policy_reasons: list[str] = Field(default_factory=list)
    policy_categories: list[str] = Field(default_factory=list)
    expires_at: str = ""
    created_at: str = Field(default_factory=_utc_now_iso)
    updated_at: str = Field(default_factory=_utc_now_iso)
    decided_at: str = ""
    metadata: dict = Field(default_factory=dict)

    def is_approved(self) -> bool:
        return self.status == "approved"

    def is_pending(self) -> bool:
        return self.status == "pending"

    def is_rejected(self) -> bool:
        return self.status == "rejected"


class AtlasApprovalSnapshot(BaseModel):
    pool_id: str
    records: list[AtlasApprovalRecord] = Field(default_factory=list)
    approved_pool: bool = False
    approved_item_ids: list[str] = Field(default_factory=list)
    approved_patch_ids: list[str] = Field(default_factory=list)
    pending_item_ids: list[str] = Field(default_factory=list)
    rejected_item_ids: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
