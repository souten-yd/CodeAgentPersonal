from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from agent.atlas_multi_item_supervised_status_schema import AtlasMultiItemSupervisedStatusRequest, AtlasMultiItemSupervisedStatusResult
from agent.atlas_next_action_orchestrator_policies import get_next_action_orchestrator_policy
from agent.atlas_next_action_orchestrator_schema import AtlasNextActionContract, AtlasNextActionOrchestratorRequest, AtlasNextActionOrchestratorResult

ALLOW_PATHS = {
    "/api/atlas/patch-candidate-approval/decide": "AtlasPatchCandidateApprovalService.decide",
    "/api/atlas/supervised-handoff-safe-apply/execute": "AtlasSupervisedHandoffSafeApplyService.execute",
    "/api/atlas/supervised-handoff-verification/run": "AtlasSupervisedHandoffVerificationService.run",
    "/api/atlas/supervised-handoff-retry/run": "AtlasSupervisedHandoffRetryService.run",
    "/api/atlas/patch-regen-from-recommendation/run": "AtlasPatchRegenFromRecommendationService.run",
}

SIDE_EFFECT_FLAGS = {
    "next_action_executed": False,
    "safe_apply_executed": False,
    "verification_executed": False,
    "bounded_retry_executed": False,
    "patch_regeneration_executed": False,
    "approval_executed": False,
    "rollback_executed": False,
    "restore_executed": False,
    "debug_review_executed": False,
    "remote_git_executed": False,
}


class AtlasNextActionOrchestratorService:
    def __init__(self, *, storage, journal, supervised_status_service):
        self.storage = storage
        self.journal = journal
        self.supervised_status_service = supervised_status_service

    def prepare(self, request: AtlasNextActionOrchestratorRequest) -> AtlasNextActionOrchestratorResult:
        pol = get_next_action_orchestrator_policy(request.policy_id)
        oid = f"nextaction_{uuid4().hex[:10]}"
        run_id = request.run_id or oid
        self.emit("next_action_orchestrator_started", request, oid)
        result = AtlasNextActionOrchestratorResult(pool_id=request.pool_id, run_id=run_id, orchestrator_run_id=oid, policy_id=pol.policy_id, status="blocked", metadata={})
        try:
            queue, qmeta, warns, errs = self.load_or_build_multi_status_queue(request)
            result.multi_status_run_id = qmeta.get("multi_status_run_id", "")
            result.warnings.extend(warns)
            result.errors.extend(errs)
            self.emit("next_action_orchestrator_queue_loaded", request, oid, multi_status_run_id=result.multi_status_run_id)
            q_errors, q_warnings = self.validate_queue_safety(queue)
            result.warnings.extend(q_warnings)
            if q_errors:
                result.errors.extend(q_errors)
                result.status = "blocked"
                self.emit("next_action_orchestrator_blocked", request, oid, error_count=len(result.errors), warning_count=len(result.warnings))
                self._apply_result_metadata(result, qmeta, queue, None, True)
                self.save_result(result)
                self.emit("next_action_orchestrator_result_saved", request, oid)
                return result

            summary, selection_error = self.select_action_item(queue, request)
            if selection_error:
                result.status = "blocked"
                result.errors.append(selection_error)
                self.emit("next_action_orchestrator_blocked", request, oid, error_count=len(result.errors), warning_count=len(result.warnings))
                self._apply_result_metadata(result, qmeta, queue, None, True)
                self.save_result(result)
                self.emit("next_action_orchestrator_result_saved", request, oid)
                return result
            if summary is None:
                result.status = "no_action"
                self._apply_result_metadata(result, qmeta, queue, None, True)
                self.save_result(result)
                self.emit("next_action_orchestrator_result_saved", request, oid)
                return result

            self.emit("next_action_orchestrator_item_selected", request, oid, selected_item_id=summary.get("item_id", ""), selected_next_action=summary.get("next_action", ""))
            c = self.map_next_action_to_contract(summary, request)
            self.emit("next_action_orchestrator_contract_built", request, oid, selected_next_action=c.next_action, action_kind=c.action_kind, target_api_path=c.target_api_path)
            self.validate_action_contract(c)
            self.emit("next_action_orchestrator_contract_validated", request, oid, payload_valid=c.payload_valid, missing_fields=c.missing_fields, error_count=len(c.errors), warning_count=len(c.warnings))
            result.selected_item_id = c.item_id
            result.selected_next_action = c.next_action
            result.action_contract = c

            if c.errors or not c.payload_valid:
                result.status = "blocked"
                self.emit("next_action_orchestrator_blocked", request, oid)
            elif c.action_kind == "manual_display":
                result.status = "manual_display"
                self.emit("next_action_orchestrator_manual_display", request, oid)
            elif c.action_kind == "execution_candidate":
                result.status = "action_ready"
                self.emit("next_action_orchestrator_action_ready", request, oid)
            elif c.next_action == "none":
                result.status = "no_action"
            else:
                result.status = "blocked"
            if request.dry_run or pol.policy_id == "next_action_orchestrator_dry_run_v1":
                result.status = "dry_run"
            self._apply_result_metadata(result, qmeta, queue, c, True)
            self.save_result(result)
            self.emit("next_action_orchestrator_result_saved", request, oid, selected_item_id=result.selected_item_id, selected_next_action=result.selected_next_action)
            return result
        except Exception as exc:
            result.status = "failed_internal"
            result.errors.append(f"unexpected_prepare_exception:{exc.__class__.__name__}")
            self.emit("next_action_orchestrator_failed_internal", request, oid, error_count=len(result.errors))
            self._apply_result_metadata(result, {}, None, None, True)
            try:
                self.save_result(result)
            finally:
                self.emit("next_action_orchestrator_result_saved", request, oid)
            return result

    def validate_queue_safety(self, queue):
        errors, warnings = [], []
        if queue is None:
            return ["queue_missing"], warnings
        md = queue.metadata or {}
        se = md.get("side_effects", {})
        if queue.status == "failed_internal": errors.append("queue_failed_internal")
        if not (queue.item_summaries or []): errors.append("queue_empty")
        if md.get("next_action_executed") is True: errors.append("queue_next_action_executed")
        if se.get("safe_apply_executed") is True: errors.append("queue_safe_apply_executed")
        if se.get("verification_executed") is True: errors.append("queue_verification_executed")
        if se.get("bounded_retry_executed") is True: errors.append("queue_bounded_retry_executed")
        if se.get("patch_regeneration_executed") is True: errors.append("queue_patch_regeneration_executed")
        if se.get("approval_executed") is True: errors.append("queue_approval_executed")
        if md.get("queue_only") is not True: errors.append("queue_not_queue_only")
        if md.get("supervised_status_integrated") is not True: errors.append("queue_not_integrated")
        if queue.status == "blocked": warnings.append("queue_status_blocked")
        if queue.next_item is None: warnings.append("queue_next_item_missing")
        pvs = md.get("payload_validation_summary", {})
        if pvs.get("missing_payload_count", 0) > 0 or pvs.get("missing_required_fields_count", 0) > 0:
            warnings.append("queue_payloads_missing")
        return errors, warnings

    def load_or_build_multi_status_queue(self, request):
        root = Path("ca_data") / "atlas" / "multi_item_supervised_status" / request.pool_id
        warnings = []
        errors = []
        qmeta = {"queue_loaded_from": "", "multi_status_run_id": ""}
        if request.multi_status_run_id:
            if not request.multi_status_run_id.startswith("multistatus_"): return None, qmeta, warnings, ["invalid_multi_status_run_id"]
            p = root / f"{request.multi_status_run_id}.json"
            if p.exists():
                qmeta.update({"queue_loaded_from": "requested", "multi_status_run_id": request.multi_status_run_id})
                return AtlasMultiItemSupervisedStatusResult.model_validate(json.loads(p.read_text(encoding="utf-8"))), qmeta, warnings, errors
        files = sorted(root.glob("multistatus_*.json"), key=lambda x: x.stat().st_mtime, reverse=True) if root.exists() else []
        if files and not request.refresh_queue:
            data = json.loads(files[0].read_text(encoding="utf-8")); qmeta.update({"queue_loaded_from": "latest", "multi_status_run_id": data.get("multi_status_run_id", "")}); return AtlasMultiItemSupervisedStatusResult.model_validate(data), qmeta, warnings, errors
        if not request.build_queue_if_missing and not request.refresh_queue: return None, qmeta, warnings, ["queue_not_found"]
        built = self.supervised_status_service.build_status(AtlasMultiItemSupervisedStatusRequest(pool_id=request.pool_id, run_id=request.run_id, workspace_id=request.workspace_id, project_path=request.project_path, policy_id=request.queue_policy_id, dry_run=True, refresh_item_status=False, update_item_status=False, update_metadata=False))
        qmeta.update({"queue_loaded_from": "built", "multi_status_run_id": built.multi_status_run_id})
        return built, qmeta, warnings, errors

    def select_action_item(self, queue, request):
        sums = queue.item_summaries or []
        selected = None
        if request.item_id and request.requested_next_action:
            selected = next((s for s in sums if s.item_id == request.item_id), None)
            if selected is None: return None, "selected_action_not_found"
            if selected.next_action != request.requested_next_action: return None, "requested_action_mismatch"
        elif request.item_id:
            selected = next((s for s in sums if s.item_id == request.item_id), None)
        elif request.requested_next_action:
            selected = next((s for s in sorted(sums, key=lambda x: x.priority) if s.next_action == request.requested_next_action), None)
            if selected is None: return None, "selected_action_not_found"
        elif queue.next_item:
            selected = queue.next_item
        elif sums:
            selected = sorted(sums, key=lambda x: x.priority)[0]
        if selected is None:
            return None, None
        return selected.model_dump(), None

    def map_next_action_to_contract(self, s, request):
        n = s.get("next_action") or "none"; p = dict(s.get("next_action_payload") or {})
        base = dict(action_id=f"action_{uuid4().hex[:8]}", item_id=s.get("item_id", ""), item_title=s.get("item_title", ""), supervised_status=s.get("supervised_status", ""), next_action=n, selectable=bool(s.get("selectable", False)), payload_valid=False, manual_required=(n != "none"), execution_allowed=False)
        m = {
            "approve_patch_candidate": ("execution_candidate", "POST", "/api/atlas/patch-candidate-approval/decide", ["pool_id", "item_id", "regen_run_id", "proposal_id"]),
            "run_supervised_safe_apply": ("execution_candidate", "POST", "/api/atlas/supervised-handoff-safe-apply/execute", ["pool_id", "item_id", "handoff_id"]),
            "run_supervised_verification": ("execution_candidate", "POST", "/api/atlas/supervised-handoff-verification/run", ["pool_id", "item_id", "safe_apply_execution_id"]),
            "run_supervised_retry": ("execution_candidate", "POST", "/api/atlas/supervised-handoff-retry/run", ["pool_id", "item_id", "verification_run_id", "safe_apply_execution_id"]),
            "run_patch_regen_from_recommendation": ("execution_candidate", "POST", "/api/atlas/patch-regen-from-recommendation/run", ["pool_id", "item_id", "recommendation_run_id"]),
        }
        if n in {"manual_review", "investigate_failure"}:
            payload = {"pool_id": request.pool_id, "item_id": s.get("item_id", ""), "reason": request.reason, "evidence_type": s.get("evidence_type", ""), "evidence_run_id": s.get("evidence_run_id", "")}
            return AtlasNextActionContract(**base, action_kind="manual_display", payload=payload, required_fields=["pool_id", "item_id"])
        if n not in m: return AtlasNextActionContract(**base, action_kind="none", payload={"pool_id": request.pool_id, "item_id": s.get("item_id", "")})
        kind, method, path, reqs = m[n]; payload = {"pool_id": request.pool_id, "item_id": s.get("item_id", ""), **p, "reviewer": request.reviewer, "reason": request.reason, "dry_run": False}
        if n == "approve_patch_candidate": payload.update({"decision_required": True, "suggested_decision": "approve"})
        return AtlasNextActionContract(**base, action_kind=kind, target_api_method=method, target_api_path=path, target_service=ALLOW_PATHS[path], payload=payload, required_fields=reqs)

    def validate_action_contract(self, c):
        miss = [k for k in c.required_fields if not c.payload.get(k)]
        c.missing_fields = miss
        c.payload_valid = len(miss) == 0
        if c.target_api_path and c.target_api_path not in ALLOW_PATHS: c.errors.append("target_api_path_not_allowlisted")
        if c.action_kind == "manual_display" and c.target_api_path: c.errors.append("manual_display_must_not_have_target")
        if c.action_kind == "execution_candidate" and not c.selectable: c.errors.append("selected_item_unselectable")
        if c.supervised_status == "completed": c.errors.append("completed_item_has_no_action")
        if c.supervised_status == "failed_internal": c.errors.append("failed_internal_item_not_actionable")
        if c.next_action == "none": c.blocked_reason = "no_action"
        c.metadata["validation_errors"] = list(c.errors)
        c.metadata["validation_warnings"] = list(c.warnings)

    def _apply_result_metadata(self, result, qmeta, queue, c, queue_safety_checked):
        qmd = (queue.metadata if queue else {}) or {}
        result.metadata.update({
            "queue_loaded_from": qmeta.get("queue_loaded_from", ""),
            "queue_status": (queue.status if queue else ""),
            "queue_counts": (queue.counts if queue else {}),
            "queue_next_item_id": (queue.next_item.item_id if queue and queue.next_item else ""),
            "queue_next_action": (queue.next_item.next_action if queue and queue.next_item else ""),
            "contract_validation": {"payload_valid": (c.payload_valid if c else False), "missing_fields": (c.missing_fields if c else []), "errors": (c.errors if c else []), "warnings": (c.warnings if c else [])},
            "side_effects": SIDE_EFFECT_FLAGS,
            "queue_safety_checked": queue_safety_checked,
            "action_executable_by_orchestrator": False,
        })
        result.queue_summary = {"counts": (queue.counts if queue else {}), "next_item_id": (queue.next_item.item_id if queue and queue.next_item else ""), "next_action": (queue.next_item.next_action if queue and queue.next_item else ""), "queue_loaded_from": qmeta.get("queue_loaded_from", ""), "queue_status": (queue.status if queue else "")}

    def save_result(self, r):
        root = Path("ca_data") / "atlas" / "next_action_orchestrator" / r.pool_id; root.mkdir(parents=True, exist_ok=True)
        (root / f"{r.orchestrator_run_id}.json").write_text(json.dumps(r.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
        c = r.action_contract
        preview = {}
        if c:
            preview = {k: v for k, v in c.payload.items() if k not in {"patch", "stdout", "stderr", "secrets"}}
        lines = ["# Next Action Orchestrator", "", "## Summary", f"- orchestrator_run_id: {r.orchestrator_run_id}", f"- pool_id: {r.pool_id}", f"- status: {r.status}", f"- multi_status_run_id: {r.multi_status_run_id}", f"- selected_item_id: {r.selected_item_id}", f"- selected_next_action: {r.selected_next_action}", "", "## Action Contract", f"- action_kind: {c.action_kind if c else ''}", f"- target_api_method: {c.target_api_method if c else ''}", f"- target_api_path: {c.target_api_path if c else ''}", f"- target_service: {c.target_service if c else ''}", f"- manual_required: {c.manual_required if c else False}", f"- execution_allowed: {c.execution_allowed if c else False}", f"- payload_valid: {c.payload_valid if c else False}", f"- missing_fields: {c.missing_fields if c else []}", f"- blocked_reason: {c.blocked_reason if c else ''}", f"- errors: {c.errors if c else []}", f"- warnings: {c.warnings if c else []}", "", "## Payload Preview", "```json", json.dumps(preview, ensure_ascii=False, indent=2), "```", "", "## Queue Summary", f"- counts: {r.metadata.get('queue_counts', {})}", f"- next_item_id: {r.metadata.get('queue_next_item_id', '')}", f"- next_action: {r.metadata.get('queue_next_action', '')}", f"- queue_loaded_from: {r.metadata.get('queue_loaded_from', '')}", f"- queue_status: {r.metadata.get('queue_status', '')}", "", "## Safety", "- next action executed: false", "- safe_apply executed: false", "- verification executed: false", "- bounded retry executed: false", "- patch regeneration executed: false", "- approval executed: false", "- rollback/restore/debug executed: false", "- remote git executed: false"]
        (root / f"{r.orchestrator_run_id}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def emit(self, event_type, request, oid, **kw):
        self.journal.append_event(request.pool_id, request.run_id or oid, {"event_type": event_type, "orchestrator_run_id": oid, "pool_id": request.pool_id, "run_id": request.run_id or oid, "created_at": datetime.now(timezone.utc).isoformat(), **SIDE_EFFECT_FLAGS, **kw})
