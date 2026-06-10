"""Verification checkpoint and restart-safe resume (PI-19).

Captures the exact revision/state needed to resume long-running development after a restart
and detects external source changes before continuation. Checkpoints are immutable and
idempotent (replay does not create a duplicate), so apply/verification are never duplicated
on replay, and the prior base revision is always available for rollback.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from agent.project_intelligence._persistence import (
    ArtifactStore,
    apply_migrations,
    artifact_table_migration,
    connect,
    default_sqlite_path,
)

_TABLE = "pi_checkpoints"
_MIG = "pi_checkpoint_migrations"

# Resume actions.
RESUME = "resume"
REFRESH_NEEDED = "refresh_needed"
REPLAN_NEEDED = "replan_needed"


@dataclass(frozen=True)
class Checkpoint:
    project_id: str
    workspace_id: str
    plan_pool_id: str
    plan_item_id: str
    requirement_revision: str | None = None
    blueprint_revision: str | None = None
    actual_twin_revision: str | None = None
    convergence_report_id: str | None = None
    plan_pool_revision: str | None = None
    last_successful_evidence: list[str] = field(default_factory=list)
    rollout_mode: str = "off"
    working_tree_hash: str = ""


@dataclass
class ResumeDecision:
    action: str
    from_revisions: dict[str, str | None]
    reasons: list[str] = field(default_factory=list)
    rollback_base_revision: str | None = None


def _checkpoint_id(plan_pool_id: str, plan_item_id: str, idempotency_key: str) -> str:
    seed = f"{plan_pool_id}|{plan_item_id}|{idempotency_key}"
    return "ckpt:" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


class CheckpointController:
    """Immutable, idempotent checkpoint persistence + resume decisions."""

    def __init__(self, db_path: str | Path | None = None, *, now_fn: Callable[[], str] | None = None) -> None:
        self._conn = connect(db_path or default_sqlite_path("checkpoint"))
        apply_migrations(self._conn, [artifact_table_migration(_TABLE)], migration_table=_MIG)
        self._store = ArtifactStore(self._conn, _TABLE, now_fn=now_fn)

    def _group(self, checkpoint: Checkpoint) -> str:
        return f"{checkpoint.plan_pool_id}:{checkpoint.plan_item_id}"

    def save(self, checkpoint: Checkpoint, *, idempotency_key: str) -> tuple[str, bool]:
        """Persist a checkpoint. Returns (checkpoint_id, is_new); replay is a no-op (idempotent)."""
        cid = _checkpoint_id(checkpoint.plan_pool_id, checkpoint.plan_item_id, idempotency_key)
        if self._store.get(checkpoint.project_id, cid) is not None:
            return cid, False  # duplicate replay -> no new apply/verification
        self._store.put(
            project_id=checkpoint.project_id, workspace_id=checkpoint.workspace_id,
            group_id=self._group(checkpoint), artifact_id=cid, artifact_type="checkpoint",
            payload=asdict(checkpoint), idempotency_key=idempotency_key,
        )
        return cid, True

    def load_latest(self, project_id: str, workspace_id: str, plan_pool_id: str, plan_item_id: str) -> Checkpoint | None:
        head = self._store.get_head(project_id, workspace_id, f"{plan_pool_id}:{plan_item_id}")
        if head is None:
            return None
        return Checkpoint(**head["payload"])

    def detect_external_change(
        self, checkpoint: Checkpoint, *, current_actual_revision: str | None, current_working_tree_hash: str
    ) -> bool:
        """An external source change is when the live tree differs from the checkpoint."""
        if checkpoint.actual_twin_revision is not None and current_actual_revision is not None:
            if checkpoint.actual_twin_revision != current_actual_revision:
                return True
        if checkpoint.working_tree_hash and current_working_tree_hash:
            if checkpoint.working_tree_hash != current_working_tree_hash:
                return True
        return False

    def resume_decision(
        self, checkpoint: Checkpoint, *, current_actual_revision: str | None, current_working_tree_hash: str
    ) -> ResumeDecision:
        from_revisions = {
            "requirement_revision": checkpoint.requirement_revision,
            "blueprint_revision": checkpoint.blueprint_revision,
            "actual_twin_revision": checkpoint.actual_twin_revision,
            "convergence_report_id": checkpoint.convergence_report_id,
            "plan_pool_revision": checkpoint.plan_pool_revision,
        }
        rollback = checkpoint.actual_twin_revision or checkpoint.plan_pool_revision
        if self.detect_external_change(checkpoint, current_actual_revision=current_actual_revision,
                                       current_working_tree_hash=current_working_tree_hash):
            return ResumeDecision(action=REFRESH_NEEDED, from_revisions=from_revisions,
                                  reasons=["external source change detected before continuation"],
                                  rollback_base_revision=rollback)
        return ResumeDecision(action=RESUME, from_revisions=from_revisions,
                              reasons=["revisions match; resume from exact checkpoint"],
                              rollback_base_revision=rollback)

    def close(self) -> None:
        self._conn.close()
