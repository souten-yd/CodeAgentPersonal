"""Bounded correction router: observe a verification failure -> diagnose test-vs-code -> route the
regeneration to the right item -> re-verify. Bounded and risk-gated.

This is the targeted slice of a dynamic agent loop needed so a failing test caused by a CODE bug is
routed back to code generation (not just test regeneration), which plain self-correction cannot do
(it only ever regenerates the item that failed). Atlas-owned: it composes existing services
(patch proposal, safe apply, verification, self-correction). It does NOT import or use
``agent/loop.py`` (Lumen-owned) -> zero Lumen impact.

Drop-in for the autopilot: takes/returns the same AtlasSelfCorrectionRequest/Result as the
self-correction service, so wiring is a one-line swap.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from agent.atlas_auto_safe_apply_schema import AtlasAutoSafeApplyRequest
from agent.atlas_auto_verification_schema import AtlasAutoVerificationRequest
from agent.atlas_patch_proposal_schema import AtlasPatchProposalRequest
from agent.atlas_self_correction_schema import AtlasSelfCorrectionRequest, AtlasSelfCorrectionResult
from agent.atlas_self_correction_service import AUTO_REAPPLY_RISK_LEVELS
from agent.atlas_failure_diagnosis_service import AtlasFailureDiagnosisService, FIX_CODE
from agent.atlas_test_impl_linker import find_implementation_item
from agent.atlas_workspace_root import resolve_atlas_workspace_root


class AtlasCorrectionRouterService:
    def __init__(self, *, storage, journal, patch_proposal_service, auto_safe_apply_service, auto_verification_service, self_correction_service, diagnosis_service=None):
        self.storage = storage
        self.journal = journal
        self.patch_proposal_service = patch_proposal_service
        self.auto_safe_apply_service = auto_safe_apply_service
        self.auto_verification_service = auto_verification_service
        self.self_correction_service = self_correction_service
        self.diagnosis_service = diagnosis_service or AtlasFailureDiagnosisService()

    def run(self, request: AtlasSelfCorrectionRequest) -> AtlasSelfCorrectionResult:
        out = AtlasSelfCorrectionResult(pool_id=request.pool_id, item_id=request.item_id, run_id=request.run_id, status="not_attempted", created_at=datetime.now(timezone.utc).isoformat())
        pool = self.storage.load_pool(request.pool_id)
        test_item = pool.get_item(request.item_id)
        if test_item is None:
            out.status, out.reason = "not_attempted", "item_not_found"
            return out

        vr = dict(request.verification_result or {})
        test_content = self._read_item_file(pool, request, test_item)
        impl_link = find_implementation_item(pool=pool, test_item=test_item, test_content=test_content)

        # Diagnose only when we actually have an implementation item to route to; otherwise there is
        # nothing to do but regenerate the failing item itself (self-correction).
        decision = "no_route"
        if impl_link:
            impl_item = pool.get_item(impl_link["item_id"])
            impl_content = self._read_item_file(pool, request, impl_item) if impl_item else ""
            diag = self.diagnosis_service.diagnose(
                stdout=str(vr.get("stdout_tail") or ""), stderr=str(vr.get("stderr_tail") or ""),
                exit_code=vr.get("exit_code"), test_content=test_content, impl_content=impl_content,
            )
            decision = str(diag.get("decision") or "")
            out.metadata["diagnosis"] = diag
            out.metadata["linked_implementation_item"] = impl_link["item_id"]
            self._emit(request, "correction_route_diagnosis", status=decision, extra={"impl_item": impl_link["item_id"], "source": diag.get("source")})

            if decision == FIX_CODE and impl_item is not None and self._is_applied(impl_item) and self._risk_ok(impl_item):
                routed = self._fix_code(request, pool, impl_item, test_item, vr, test_content)
                if routed.status == "recovered":
                    routed.metadata.update(out.metadata)
                    return routed
                # Code fix did not recover; fall through to fixing the test (within budget).
                out.metadata["code_fix_result"] = routed.model_dump()

        # Fallback / fix_test path: regenerate the failing item itself via the existing loop.
        self._emit(request, "correction_route_fix_test", status="started", extra={"reason": decision})
        sc = self.self_correction_service.run(request)
        sc.metadata = {**out.metadata, **(sc.metadata or {}), "correction_route": decision}
        return sc

    def _fix_code(self, request: AtlasSelfCorrectionRequest, pool, impl_item, test_item, test_verification: dict, test_content: str) -> AtlasSelfCorrectionResult:
        """Regenerate the implementation item using the failing test as feedback, re-apply it, then
        re-verify by re-running the TEST item (not the impl item)."""
        out = AtlasSelfCorrectionResult(pool_id=request.pool_id, item_id=impl_item.item_id, run_id=request.run_id, status="not_attempted", created_at=datetime.now(timezone.utc).isoformat())
        self._emit(request, "correction_route_fix_code", status="started", extra={"impl_item": impl_item.item_id})

        # 1. Feed the failing test (its output + source) to the impl item's regeneration.
        feedback = {
            "status": "failed",
            "command": str(test_verification.get("command") or ""),
            "exit_code": test_verification.get("exit_code"),
            "stdout_tail": str(test_verification.get("stdout_tail") or ""),
            "stderr_tail": str(test_verification.get("stderr_tail") or ""),
            "failing_test_file": (test_item.target_files or [""])[0],
            "failing_test_content": test_content,
        }
        impl = pool.get_item(impl_item.item_id)
        impl.metadata = {**(impl.metadata or {}), "verification": feedback}
        self.storage.save_pool(pool)

        # 2. Regenerate the implementation code.
        proposal = self.patch_proposal_service.propose_for_item(AtlasPatchProposalRequest(pool_id=request.pool_id, item_id=impl_item.item_id, run_id=request.run_id, workspace_id=request.workspace_id, source_type="plan_item"))
        if str(proposal.status) != "proposed" or not bool((proposal.metadata or {}).get("patch_content_available")):
            out.status, out.reason = "regen_failed", "impl_patch_regeneration_no_content"
            self._emit(request, "correction_route_fix_code", status="regen_failed", extra={"impl_item": impl_item.item_id})
            return out

        # 3. Re-apply the corrected implementation.
        safe = self.auto_safe_apply_service.execute_one(AtlasAutoSafeApplyRequest(pool_id=request.pool_id, item_id=impl_item.item_id, run_id=request.run_id, workspace_id=request.workspace_id))
        out.changed_files = list(getattr(safe, "changed_files", []) or [])
        if str(safe.status) != "applied":
            out.status, out.reason = "reapply_failed", f"impl_reapply_not_applied:{safe.status}"
            self._emit(request, "correction_route_fix_code", status="reapply_failed", extra={"impl_item": impl_item.item_id})
            return out

        # 4. Re-verify by re-running the TEST item.
        vr = self.auto_verification_service.run_after_auto_safe_apply(AtlasAutoVerificationRequest(pool_id=request.pool_id, item_id=test_item.item_id, run_id=request.run_id))
        out.attempts = 1
        out.final_verification_status = str(vr.status)
        if str(vr.status) in {"passed", "skipped"}:
            out.status, out.reason = "recovered", f"code_fixed_verification_{vr.status}"
            self._emit(request, "correction_route_recovered", status="recovered", extra={"impl_item": impl_item.item_id})
            return out
        out.status, out.reason = "exhausted", "code_fix_test_still_failing"
        self._emit(request, "correction_route_fix_code", status="exhausted", extra={"impl_item": impl_item.item_id})
        return out

    def _is_applied(self, item) -> bool:
        md = item.metadata or {}
        safe = str((md.get("safe_apply") or {}).get("status") or "").lower()
        auto = str((md.get("auto_safe_apply") or {}).get("status") or "").lower()
        return safe == "applied" or auto == "applied"

    def _risk_ok(self, item) -> bool:
        return str(getattr(item, "risk_level", "") or "").lower() in AUTO_REAPPLY_RISK_LEVELS

    def _read_item_file(self, pool, request: AtlasSelfCorrectionRequest, item) -> str:
        """Best-effort read of an item's single target file from the workspace; "" on any problem."""
        try:
            files = [str(f).strip() for f in (getattr(item, "target_files", None) or []) if str(f).strip()]
            if len(files) != 1:
                return ""
            p = Path(files[0])
            if p.is_absolute() or ".." in p.parts:
                return ""
            workspace_root = resolve_atlas_workspace_root(ca_data_root=self.storage.root_dir, workspace_id=request.workspace_id or "default", project_path=str(getattr(pool, "project_path", "") or ""))
            target = (workspace_root / p).resolve()
            target.relative_to(workspace_root)
            if not target.is_file():
                return ""
            return target.read_text(encoding="utf-8", errors="replace")[:8000]
        except Exception:  # noqa: BLE001
            return ""

    def _emit(self, request: AtlasSelfCorrectionRequest, event_type: str, *, status: str, extra: dict | None = None) -> None:
        if not request.run_id:
            return
        try:
            self.journal.append_event(request.pool_id, request.run_id, {"event_type": event_type, "pool_id": request.pool_id, "run_id": request.run_id, "item_id": request.item_id, "status": status, "created_at": datetime.now(timezone.utc).isoformat(), **(extra or {})})
        except Exception:
            pass
