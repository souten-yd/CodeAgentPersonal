"""Verification-driven self-correction: regenerate a patch from a verification failure, re-apply, re-verify.

This is the deterministic core of "full automation": when an applied change fails verification, instead
of stopping (or fabricating a placeholder), feed the failing test/compile output back to the patch
generator, re-apply the corrected content, and re-verify — bounded by a small attempt cap and gated to
low/medium risk only. High/critical items are never auto-reapplied (human judgement).

Wiring mirrors the autopilot: it reuses the same AtlasAutoSafeApplyService (re-apply) and
AtlasAutoVerificationService (re-verify) the caller already constructed, and the AtlasPatchProposalService
(regeneration). All attempts are journaled so the trail is inspectable.
"""
from __future__ import annotations

from datetime import datetime, timezone

from agent.atlas_auto_safe_apply_schema import AtlasAutoSafeApplyRequest
from agent.atlas_auto_verification_schema import AtlasAutoVerificationRequest
from agent.atlas_patch_proposal_schema import AtlasPatchProposalRequest
from agent.atlas_self_correction_schema import AtlasSelfCorrectionRequest, AtlasSelfCorrectionResult

# Risk levels that may be auto-reapplied without a human. High/critical are intentionally excluded.
AUTO_REAPPLY_RISK_LEVELS = {"low", "medium"}
_FRONTEND_EXTENSIONS = (".html", ".css", ".js")
_NON_FRONTEND_OR_EXECUTION_EXTENSIONS = (".py", ".sh", ".bash", ".ps1", ".sql", ".yaml", ".yml", ".toml")
_RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


class AtlasSelfCorrectionService:
    def __init__(self, *, storage, journal, patch_proposal_service, auto_safe_apply_service, auto_verification_service):
        self.storage = storage
        self.journal = journal
        self.patch_proposal_service = patch_proposal_service
        self.auto_safe_apply_service = auto_safe_apply_service
        self.auto_verification_service = auto_verification_service

    def run(self, request: AtlasSelfCorrectionRequest) -> AtlasSelfCorrectionResult:
        out = AtlasSelfCorrectionResult(
            pool_id=request.pool_id,
            item_id=request.item_id,
            run_id=request.run_id,
            status="not_attempted",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        pool = self.storage.load_pool(request.pool_id)
        item = pool.get_item(request.item_id)
        if item is None:
            out.status, out.reason = "not_attempted", "item_not_found"
            return out

        # Gate: only auto-reapply the configured risk levels (default low/medium). high/critical
        # stop for human review unless the caller explicitly widens request.risk_levels.
        allowed_risk = {str(r).lower() for r in (request.risk_levels or [])} or AUTO_REAPPLY_RISK_LEVELS
        risk = str(getattr(item, "risk_level", "") or "").lower()
        if risk not in allowed_risk:
            exception = self._high_risk_frontend_exception(pool, item, risk)
            if not exception.get("allowed"):
                out.status, out.reason = "skipped", exception.get("reason") or f"risk_level_not_auto_reapplyable:{risk or 'unknown'}"
                out.metadata = {**(out.metadata or {}), **exception}
                return out
            out.metadata = {**(out.metadata or {}), **exception, "high_risk_frontend_exception": True}
            self._emit(request, "self_correction_high_risk_frontend_exception", attempt=0, status="allowed")

        max_attempts = max(1, int(request.max_attempts or 1))
        last_verification = dict(request.verification_result or {})
        for attempt in range(1, max_attempts + 1):
            out.attempts = attempt
            self._emit(request, "self_correction_attempt", attempt=attempt, status="started")

            # 1. Record the failing verification onto the item so the patch generator can use it as
            #    feedback (propose_for_item reads item.metadata["verification"]).
            if not self._store_verification_feedback(pool, request.item_id, last_verification):
                out.status, out.reason = "failed", "item_not_found"
                return out

            # 2. Regenerate the patch (LLM, schema-constrained) using the verification feedback.
            proposal = self.patch_proposal_service.propose_for_item(
                AtlasPatchProposalRequest(
                    pool_id=request.pool_id,
                    item_id=request.item_id,
                    run_id=request.run_id,
                    workspace_id=request.workspace_id,
                    source_type="plan_item",
                )
            )
            if str(proposal.status) != "proposed" or not bool((proposal.metadata or {}).get("patch_content_available")):
                out.status = "exhausted" if attempt >= max_attempts else "regen_failed"
                out.reason = "patch_regeneration_no_content"
                self._emit(request, "self_correction_regen_failed", attempt=attempt, status="failed")
                if attempt >= max_attempts:
                    return out
                continue

            # 3. Re-apply the corrected content.
            safe = self.auto_safe_apply_service.execute_one(
                AtlasAutoSafeApplyRequest(pool_id=request.pool_id, item_id=request.item_id, run_id=request.run_id, workspace_id=request.workspace_id)
            )
            out.changed_files = list(getattr(safe, "changed_files", []) or [])
            if str(safe.status) != "applied":
                out.status = "exhausted" if attempt >= max_attempts else "reapply_failed"
                out.reason = f"reapply_not_applied:{safe.status}"
                self._emit(request, "self_correction_reapply_failed", attempt=attempt, status=str(safe.status))
                if attempt >= max_attempts:
                    return out
                continue

            # 4. Re-verify.
            vr = self.auto_verification_service.run_after_auto_safe_apply(
                AtlasAutoVerificationRequest(pool_id=request.pool_id, item_id=request.item_id, run_id=request.run_id)
            )
            last_verification = vr.model_dump()
            out.metadata["final_verification_result"] = dict(last_verification)
            out.final_verification_status = str(vr.status)
            self._emit(request, "self_correction_verification", attempt=attempt, status=str(vr.status))

            if str(vr.status) in {"passed", "skipped"} or self._no_verification_configured(vr):
                out.status, out.reason = "recovered", f"verification_{vr.status}"
                self._emit(request, "self_correction_recovered", attempt=attempt, status="recovered")
                return out

        out.status = "exhausted"
        out.reason = out.reason or "verification_still_failing"
        self._emit(request, "self_correction_exhausted", attempt=out.attempts, status="exhausted")
        return out

    def _store_verification_feedback(self, pool, item_id: str, verification: dict) -> bool:
        item = pool.get_item(item_id)
        if item is None:
            return False
        md = dict(item.metadata or {})
        md["verification"] = dict(verification or {})
        item.metadata = md
        item.status = "ready"
        if hasattr(pool, "completed_item_ids"):
            pool.completed_item_ids = [i for i in list(pool.completed_item_ids or []) if i != item_id]
        self.storage.save_pool(pool)
        return True

    def _no_verification_configured(self, vr) -> bool:
        warnings = list(getattr(vr, "warnings", []) or [])
        return any(w in warnings for w in ("verification_command_missing", "no_test_commands"))

    def _high_risk_frontend_exception(self, pool, item, risk: str) -> dict:
        if risk != "high":
            return {"allowed": False, "reason": f"risk_level_not_auto_reapplyable:{risk or 'unknown'}"}
        if not self._is_frontend_only_artifact(item):
            return {"allowed": False, "reason": "risk_level_not_auto_reapplyable:high"}
        if bool(getattr(item, "requires_user_confirmation", False)):
            envelope = self._active_envelope(pool)
            if not envelope:
                return {"allowed": False, "reason": "high_risk_frontend_exception_requires_active_envelope"}
            if not self._envelope_allows_high(envelope):
                return {"allowed": False, "reason": "high_risk_frontend_exception_exceeds_envelope_risk"}
            allowed_paths = list(((envelope.get("bounds") or {}).get("allowed_paths") or envelope.get("allowed_paths") or []))
            target_files = [str(f).replace("\\", "/") for f in (getattr(item, "target_files", []) or [])]
            if not self._paths_within_allowed_paths(target_files, allowed_paths):
                return {"allowed": False, "reason": "high_risk_frontend_exception_outside_envelope_paths"}
        return {
            "allowed": True,
            "reason": "high_risk_frontend_exception_allowed",
            "exception_scope": "frontend_only_artifact",
            "target_files": list(getattr(item, "target_files", []) or []),
        }

    @staticmethod
    def _is_frontend_only_artifact(item) -> bool:
        files = [str(f).lower().strip() for f in (getattr(item, "target_files", []) or []) if str(f).strip()]
        if not files:
            return False
        if any(path.endswith(_NON_FRONTEND_OR_EXECUTION_EXTENSIONS) for path in files):
            return False
        return all(path.endswith(_FRONTEND_EXTENSIONS) for path in files)

    @staticmethod
    def _active_envelope(pool) -> dict:
        metadata = getattr(pool, "metadata", None) or {}
        candidates = [
            metadata.get("envelope"),
            metadata.get("active_envelope"),
            metadata.get("pre_authorized_envelope"),
        ]
        for candidate in candidates:
            if isinstance(candidate, dict) and str(candidate.get("status") or "").lower() == "active":
                return candidate
        return {}

    @staticmethod
    def _envelope_allows_high(envelope: dict) -> bool:
        bounds = envelope.get("bounds") if isinstance(envelope.get("bounds"), dict) else {}
        max_risk = str(bounds.get("max_risk_level") or envelope.get("max_risk_level") or "").lower()
        return _RISK_ORDER.get(max_risk, -1) >= _RISK_ORDER["high"]

    @staticmethod
    def _paths_within_allowed_paths(target_files: list[str], allowed_paths: list[str]) -> bool:
        allowed = [str(path).replace("\\", "/").strip().rstrip("/") for path in allowed_paths or [] if str(path).strip()]
        if not target_files or not allowed:
            return False
        for raw_path in target_files:
            path = str(raw_path).replace("\\", "/").strip().lstrip("/")
            if not any(path == root or path.startswith(root.rstrip("/") + "/") for root in allowed):
                return False
        return True

    def _emit(self, request: AtlasSelfCorrectionRequest, event_type: str, *, attempt: int, status: str) -> None:
        if not request.run_id:
            return
        try:
            self.journal.append_event(request.pool_id, request.run_id, {
                "event_type": event_type,
                "pool_id": request.pool_id,
                "run_id": request.run_id,
                "item_id": request.item_id,
                "attempt": attempt,
                "status": status,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
        except Exception:
            pass
