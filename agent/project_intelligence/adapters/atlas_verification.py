"""Atlas verification + resume bridge (PI-19).

Closes the loop: verification automatically ingests runtime observations, requests a
post-verification Convergence, and writes a restart-safe checkpoint. Replay is idempotent
(no duplicate apply/verification), external source changes are detected before continuation,
and the prior base revision remains available for rollback. It never replaces canonical
verification authority — it records evidence and drives bounded next steps.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agent.project_intelligence.checkpoint import Checkpoint, CheckpointController, ResumeDecision
from agent.project_intelligence.contracts import RuntimeObservationRecord
from agent.project_twin.runtime.reconciliation import RollupResult, summarize_rollup


@dataclass
class VerificationOutcome:
    rollup: RollupResult
    convergence_requested: bool
    checkpoint_id: str
    duplicate: bool
    rollback_base_revision: str | None
    last_successful_evidence: list[str] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)


class AtlasVerificationBridge:
    def __init__(self, checkpoints: CheckpointController | None = None) -> None:
        self._checkpoints = checkpoints or CheckpointController()

    @property
    def checkpoints(self) -> CheckpointController:
        return self._checkpoints

    def record_verification(
        self,
        *,
        checkpoint: Checkpoint,
        observations: list[RuntimeObservationRecord],
        idempotency_key: str,
    ) -> VerificationOutcome:
        """Ingest observations, request convergence, and persist an idempotent checkpoint."""
        rollup = summarize_rollup(observations)  # PI-8 truthful rollup
        # last successful evidence = ids of passed observations at this checkpoint.
        passed_evidence = [o.observation_id for o in observations if o.result == "passed"]
        cp = Checkpoint(
            project_id=checkpoint.project_id, workspace_id=checkpoint.workspace_id,
            plan_pool_id=checkpoint.plan_pool_id, plan_item_id=checkpoint.plan_item_id,
            requirement_revision=checkpoint.requirement_revision,
            blueprint_revision=checkpoint.blueprint_revision,
            actual_twin_revision=checkpoint.actual_twin_revision,
            convergence_report_id=checkpoint.convergence_report_id,
            plan_pool_revision=checkpoint.plan_pool_revision,
            last_successful_evidence=passed_evidence or list(checkpoint.last_successful_evidence),
            rollout_mode=checkpoint.rollout_mode, working_tree_hash=checkpoint.working_tree_hash,
        )
        cid, is_new = self._checkpoints.save(cp, idempotency_key=idempotency_key)
        diagnostics = [] if is_new else ["duplicate verification replay; no re-apply"]
        # Post-verification Convergence is requested whenever verification completed.
        convergence_requested = is_new
        return VerificationOutcome(
            rollup=rollup, convergence_requested=convergence_requested, checkpoint_id=cid,
            duplicate=not is_new, rollback_base_revision=cp.actual_twin_revision or cp.plan_pool_revision,
            last_successful_evidence=cp.last_successful_evidence, diagnostics=diagnostics,
        )

    def resume(
        self,
        *,
        project_id: str,
        workspace_id: str,
        plan_pool_id: str,
        plan_item_id: str,
        current_actual_revision: str | None,
        current_working_tree_hash: str,
    ) -> ResumeDecision | None:
        cp = self._checkpoints.load_latest(project_id, workspace_id, plan_pool_id, plan_item_id)
        if cp is None:
            return None
        return self._checkpoints.resume_decision(
            cp, current_actual_revision=current_actual_revision,
            current_working_tree_hash=current_working_tree_hash,
        )
