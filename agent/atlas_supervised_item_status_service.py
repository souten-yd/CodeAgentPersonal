from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agent.atlas_journal import AtlasJournal
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_supervised_item_status_policies import get_supervised_item_status_policy
from agent.atlas_supervised_item_status_schema import AtlasSupervisedItemStatusFinalizeRequest, AtlasSupervisedItemStatusFinalizeResult, AtlasSupervisedItemTransition


class AtlasSupervisedItemStatusService:
    SOURCE_MAP = {
        "patch_regen_candidate": ("patch_regen_candidates", ["regen_run_id", "proposal_id"], "latest_patch_candidate"),
        "patch_candidate_approval": ("patch_candidate_approvals", ["approval_run_id", "handoff_id"], "latest_approval"),
        "safe_apply_handoff": ("safe_apply_handoffs", ["handoff_id"], "latest_handoff"),
        "supervised_safe_apply": ("supervised_handoff_safe_apply_results", ["execution_id", "safe_apply_execution_id"], "latest_safe_apply"),
        "supervised_verification": ("supervised_handoff_verification_results", ["verification_run_id"], "latest_verification"),
        "supervised_retry": ("supervised_handoff_retry_results", ["supervised_retry_run_id", "bounded_retry_run_id"], "latest_retry"),
        "patch_regen_recommendation": ("patch_regen_recommendations", ["recommendation_run_id"], "latest_regen_recommendation"),
        "patch_regen_from_recommendation": ("patch_regen_from_recommendation_results", ["recommendation_exec_id", "patch_regen_result_id"], "latest_regen_from_recommendation"),
    }

    def __init__(self, *, storage=None, journal=None):
        self.storage = storage or AtlasPlanPoolStorage(Path("ca_data"))
        self.journal = journal or AtlasJournal(Path("ca_data"))

    def _now(self):
        return datetime.now(timezone.utc).isoformat()

    def _parse_dt(self, value, warnings):
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except Exception:
            warnings.append(f"invalid_created_at:{value}")
            return None

    def _latest(self, values, warnings):
        if not values:
            return {}
        parsed = [(self._parse_dt(v.get("created_at"), warnings), idx, v) for idx, v in enumerate(values)]
        if any(dt is not None for dt, _, _ in parsed):
            parsed.sort(key=lambda x: (x[0] is not None, x[0] or datetime.min.replace(tzinfo=timezone.utc), x[1]))
            return parsed[-1][2]
        return values[-1]

    def collect_evidence(self, item, request):
        md = item.metadata or {}
        warnings = []
        evidence = {
            "latest_patch_candidate": self._latest(list(md.get("patch_regen_candidates") or []), warnings),
            "latest_approval": self._latest(list(md.get("patch_candidate_approvals") or []), warnings),
            "latest_handoff": self._latest(list(md.get("safe_apply_handoffs") or []), warnings),
            "latest_safe_apply": self._latest(list(md.get("supervised_handoff_safe_apply_results") or []), warnings),
            "latest_verification": self._latest(list(md.get("supervised_handoff_verification_results") or []), warnings),
            "latest_retry": self._latest(list(md.get("supervised_handoff_retry_results") or []), warnings),
            "latest_regen_recommendation": self._latest(list(md.get("patch_regen_recommendations") or []), warnings),
            "latest_regen_from_recommendation": self._latest(list(md.get("patch_regen_from_recommendation_results") or []), warnings),
            "warnings": warnings,
            "selected_by": "latest_artifact" if request.use_latest_artifacts else "fallback",
        }
        if request.source_type:
            mapped = self.SOURCE_MAP.get(request.source_type)
            if not mapped:
                evidence["explicit_source_missing"] = True
                evidence["selected_by"] = "explicit_source"
                return evidence
            key, id_fields, latest_key = mapped
            values = list(md.get(key) or [])
            match = None
            if request.source_run_id:
                for v in values:
                    if any(str(v.get(f) or "") == request.source_run_id for f in id_fields):
                        match = v
                        break
            else:
                match = self._latest(values, warnings)
            evidence[latest_key] = match or {}
            evidence["selected_source_type"] = request.source_type
            evidence["selected_source_run_id"] = request.source_run_id
            evidence["selected_by"] = "explicit_source"
            evidence["explicit_source_missing"] = not bool(match)
        return evidence

    def decide_transition(self, ev):
        ver = ev.get("latest_verification") or {}
        retry = ev.get("latest_retry") or {}
        safe = ev.get("latest_safe_apply") or {}
        handoff = ev.get("latest_handoff") or {}
        cand = ev.get("latest_patch_candidate") or {}
        rec = ev.get("latest_regen_recommendation") or {}
        regen2 = ev.get("latest_regen_from_recommendation") or {}

        if ev.get("explicit_source_missing"):
            return "blocked", "source_evidence_not_found", "investigate_failure", ev.get("selected_source_type", "explicit_source"), ev.get("selected_source_run_id", "")
        if str(ver.get("evaluator_decision") or "").lower() == "manual_required":
            return "manual_required", "evaluator_manual_required", "manual_review", "verification", str(ver.get("verification_run_id") or "")
        if str(cand.get("status") or "") == "manual_required" or str(regen2.get("status") or "") == "manual_required":
            return "manual_required", "patch_regen_manual_required", "manual_review", "patch_candidate", str(cand.get("regen_run_id") or regen2.get("patch_regen_result_id") or "")
        if str(cand.get("status") or "") == "not_regeneratable" or str(regen2.get("status") or "") == "not_regeneratable":
            return "needs_revision", "not_regeneratable", "manual_review", "patch_candidate", str(cand.get("regen_run_id") or regen2.get("patch_regen_result_id") or "")
        if str(regen2.get("status") or "") == "patch_regen_created" and str(regen2.get("patch_regen_status") or "") == "proposal_ready" and str(regen2.get("approval_status") or "") == "pending" and not bool(regen2.get("safe_apply_ready")):
            return "patch_candidate_ready", "regen_from_recommendation_pending_approval", "approve_patch_candidate", "patch_regen_from_recommendation", str(regen2.get("recommendation_exec_id") or regen2.get("patch_regen_result_id") or "")

        retry_status = str(retry.get("status") or "")
        if retry_status in {"exhausted", "not_retryable"}:
            if bool(retry.get("patch_regen_recommended")) or str(rec.get("status") or "") == "recommendation_ready":
                return "patch_regen_recommended", "retry_exhausted_recommendation_ready", "run_patch_regen_from_recommendation", "retry", str(retry.get("supervised_retry_run_id") or "")
            if str(rec.get("status") or "") in {"not_recommended", "blocked"}:
                return "needs_revision", "retry_exhausted_without_recommendation", "manual_review", "retry", str(retry.get("supervised_retry_run_id") or "")

        if ((ver.get("verification_status") or ver.get("status")) == "passed" and str(ver.get("evaluator_decision") or "").lower() in {"continue", "passed", "ok"}) or (retry_status == "recovered" and str(retry.get("final_verification_status") or "") == "passed"):
            return "completed", "verification_passed", "none", "verification", str(ver.get("verification_run_id") or retry.get("supervised_retry_run_id") or "")

        if str(ver.get("status") or "") == "failed_internal" or retry_status == "failed_internal":
            return "failed_internal", "latest_failed_internal", "investigate_failure", "verification", str(ver.get("verification_run_id") or retry.get("supervised_retry_run_id") or "")
        if "blocked" in {str(ver.get("status") or ""), retry_status, str(rec.get("status") or "")}:
            return "blocked", "latest_blocked", "investigate_failure", "result", str(ver.get("verification_run_id") or retry.get("supervised_retry_run_id") or rec.get("recommendation_run_id") or "")

        if str(cand.get("status") or "") == "proposal_ready" and cand.get("approval_status") == "pending":
            return "patch_candidate_ready", "candidate_pending_approval", "approve_patch_candidate", "patch_candidate", str(cand.get("regen_run_id") or "")
        if str(rec.get("status") or "") == "recommendation_ready":
            return "patch_regen_recommended", "recommendation_ready", "run_patch_regen_from_recommendation", "patch_regen_recommendation", str(rec.get("recommendation_run_id") or "")
        if str(handoff.get("safe_apply_ready") or "").lower() == "true" and not bool(handoff.get("safe_apply_executed")):
            return "safe_apply_ready", "handoff_ready", "run_supervised_safe_apply", "safe_apply_handoff", str(handoff.get("handoff_id") or "")
        if str(safe.get("status") or "") == "applied" and not ev.get("latest_verification"):
            return "verification_required", "safe_apply_done_verification_missing", "run_supervised_verification", "supervised_safe_apply", str(safe.get("safe_apply_execution_id") or safe.get("execution_id") or "")
        if any(v for k, v in ev.items() if k.startswith("latest_")):
            return "manual_required", "ambiguous_evidence", "manual_review", "mixed", ""
        return "unchanged", "no_useful_evidence", "manual_review", "none", ""

    def build_next_action_payload(self, request, ev, next_action, reason, etype, erun):
        payload = {"pool_id": request.pool_id, "item_id": request.item_id}
        if next_action == "run_supervised_verification":
            safe = ev.get("latest_safe_apply") or {}
            handoff = ev.get("latest_handoff") or {}
            payload.update({"handoff_id": safe.get("handoff_id") or handoff.get("handoff_id"), "safe_apply_execution_id": safe.get("execution_id") or safe.get("safe_apply_execution_id")})
        elif next_action == "run_supervised_safe_apply":
            payload.update({"handoff_id": (ev.get("latest_handoff") or {}).get("handoff_id")})
        elif next_action == "approve_patch_candidate":
            cand = ev.get("latest_patch_candidate") or {}
            payload.update({"regen_run_id": cand.get("regen_run_id"), "proposal_id": cand.get("proposal_id")})
        elif next_action == "run_patch_regen_from_recommendation":
            rec = ev.get("latest_regen_recommendation") or {}
            payload.update({"recommendation_run_id": rec.get("recommendation_run_id")})
        elif next_action == "run_supervised_retry":
            ver = ev.get("latest_verification") or {}
            payload.update({"handoff_id": ver.get("handoff_id"), "safe_apply_execution_id": ver.get("safe_apply_execution_id"), "verification_run_id": ver.get("verification_run_id")})
        elif next_action in {"manual_review", "investigate_failure"}:
            payload.update({"evidence_type": etype, "evidence_run_id": erun, "reason": reason})
        return payload

    def finalize(self, request: AtlasSupervisedItemStatusFinalizeRequest) -> AtlasSupervisedItemStatusFinalizeResult:
        finalize_id = f"itemstatus_{uuid4().hex[:12]}"
        rid = request.run_id or finalize_id
        policy = get_supervised_item_status_policy(request.policy_id)
        transition = AtlasSupervisedItemTransition(to_status="blocked", reason="item_not_found", next_action="investigate_failure", errors=["item_not_found"])
        result_status = "blocked"
        ev = {}
        before_status = ""
        item_status_after = ""
        errors = []
        meta_flags = {"status_history_updated": False, "item_status_updated": False, "metadata_updated": False}
        self.emit(request.pool_id, rid, "supervised_item_status_finalize_started", finalize_id=finalize_id, status="started", transition=transition)
        try:
            pool = self.storage.load_pool(request.pool_id)
            item = pool.get_item(request.item_id)
            if item is None:
                raise KeyError("item_not_found")
            before_status = str(item.status or "")
            ev = self.collect_evidence(item, request)
            self.emit(request.pool_id, rid, "supervised_item_status_evidence_collected", finalize_id=finalize_id, status="in_progress", transition=transition, ev=ev)
            to_status, reason, next_action, etype, erun = self.decide_transition(ev)
            payload = self.build_next_action_payload(request, ev, next_action, reason, etype, erun)
            transition = AtlasSupervisedItemTransition(from_status=before_status, to_status=to_status, reason=reason, next_action=next_action, next_action_payload=payload, evidence_type=etype, evidence_run_id=erun, evidence_summary=ev, warnings=list(ev.get("warnings") or []), errors=[])
            self.emit(request.pool_id, rid, "supervised_item_status_transition_decided", finalize_id=finalize_id, status="in_progress", transition=transition)
            md = item.metadata or {}
            before_supervised = str(md.get("supervised_item_status", {}).get("status") or "")
            if request.dry_run or policy.policy_id == "supervised_item_status_dry_run_v1":
                result_status = "dry_run"
            else:
                result_status = "finalized" if to_status != "unchanged" else "unchanged"
                if request.update_item_status and policy.update_plan_item_status and hasattr(item, "status"):
                    if policy.preserve_original_status and "original_status_before_supervised_finalize" not in md:
                        md["original_status_before_supervised_finalize"] = item.status
                    item.status = to_status if to_status != "unchanged" else item.status
                    meta_flags["item_status_updated"] = True
                if request.update_metadata:
                    md["supervised_item_status"] = {"status": to_status, "finalize_run_id": finalize_id, "reason": reason, "next_action": next_action, "next_action_payload": payload, "evidence_type": etype, "evidence_run_id": erun, "updated_at": self._now()}
                    hist = list(md.get("supervised_item_status_history") or [])
                    hist.append({"finalize_run_id": finalize_id, "from_status": before_supervised, "to_status": to_status, "reason": reason, "next_action": next_action, "evidence_type": etype, "evidence_run_id": erun, "created_at": self._now()})
                    md["supervised_item_status_history"] = hist[-policy.max_status_history:]
                    meta_flags["status_history_updated"] = True
                    meta_flags["metadata_updated"] = True
                item.metadata = md
                self.storage.save_pool(pool)
                self.emit(request.pool_id, rid, "supervised_item_status_updated", finalize_id=finalize_id, status=result_status, transition=transition)
            item_status_after = str(item.status)
        except KeyError:
            transition = AtlasSupervisedItemTransition(from_status="", to_status="blocked", reason="item_not_found", next_action="investigate_failure", next_action_payload={"pool_id": request.pool_id, "item_id": request.item_id, "reason": "item_not_found"}, evidence_type="", evidence_run_id="", errors=["item_not_found"])
            result_status = "blocked"
            errors = ["item_not_found"]
            self.emit(request.pool_id, rid, "supervised_item_status_blocked", finalize_id=finalize_id, status=result_status, transition=transition)
        except Exception as ex:
            transition = AtlasSupervisedItemTransition(from_status=before_status, to_status="failed_internal", reason="finalize_exception", next_action="investigate_failure", next_action_payload={"pool_id": request.pool_id, "item_id": request.item_id, "reason": "finalize_exception"}, evidence_type="internal", evidence_run_id=rid, errors=[str(ex)])
            result_status = "failed_internal"
            errors = [str(ex)]
            self.emit(request.pool_id, rid, "supervised_item_status_failed_internal", finalize_id=finalize_id, status=result_status, transition=transition)
        res = AtlasSupervisedItemStatusFinalizeResult(pool_id=request.pool_id, item_id=request.item_id, run_id=rid, finalize_run_id=finalize_id, policy_id=policy.policy_id, status=result_status, item_status_before=before_status, item_status_after=item_status_after, supervised_status_before="", supervised_status_after=transition.to_status, transition=transition, selected_evidence={}, evidence_index=ev, next_action=transition.next_action, next_action_payload=transition.next_action_payload, warnings=list(ev.get("warnings") or []), errors=errors, metadata={"source_type": request.source_type, "source_run_id": request.source_run_id, "use_latest_artifacts": request.use_latest_artifacts, "selected_by": ev.get("selected_by", "fallback"), "side_effects": {"safe_apply_executed": False, "verification_executed": False, "bounded_retry_executed": False, "patch_regeneration_executed": False, "approval_executed": False, "rollback_executed": False, "restore_executed": False, "debug_review_executed": False}, **meta_flags})
        self.save_result(res)
        self.emit(request.pool_id, rid, "supervised_item_status_result_saved", finalize_id=finalize_id, status=res.status, transition=transition)
        return res

    def save_result(self, res):
        root = Path("ca_data") / "atlas" / "supervised_item_status" / res.pool_id
        root.mkdir(parents=True, exist_ok=True)
        (root / f"{res.finalize_run_id}.json").write_text(json.dumps(res.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
        ev = res.evidence_index
        md_text = f"""# Supervised Item Status Finalization

## Summary
- finalize_run_id: {res.finalize_run_id}
- pool_id: {res.pool_id}
- item_id: {res.item_id}
- status: {res.status}
- next_action: {res.next_action}

## Transition
- from_status: {res.transition.from_status}
- to_status: {res.transition.to_status}
- reason: {res.transition.reason}
- evidence_type: {res.transition.evidence_type}
- evidence_run_id: {res.transition.evidence_run_id}
- confidence: {res.transition.confidence}

## Evidence
- latest_patch_candidate: {json.dumps(ev.get("latest_patch_candidate", {}), ensure_ascii=False)}
- latest_approval: {json.dumps(ev.get("latest_approval", {}), ensure_ascii=False)}
- latest_handoff: {json.dumps(ev.get("latest_handoff", {}), ensure_ascii=False)}
- latest_safe_apply: {json.dumps(ev.get("latest_safe_apply", {}), ensure_ascii=False)}
- latest_verification: {json.dumps(ev.get("latest_verification", {}), ensure_ascii=False)}
- latest_retry: {json.dumps(ev.get("latest_retry", {}), ensure_ascii=False)}
- latest_regen_recommendation: {json.dumps(ev.get("latest_regen_recommendation", {}), ensure_ascii=False)}
- latest_regen_from_recommendation: {json.dumps(ev.get("latest_regen_from_recommendation", {}), ensure_ascii=False)}

## Next Action Payload
```json
{json.dumps(res.next_action_payload, ensure_ascii=False, indent=2)}
```
"""
        (root / f"{res.finalize_run_id}.md").write_text(md_text, encoding="utf-8")

    def emit(self, pool_id, run_id, event_type, *, finalize_id, status, transition, ev=None):
        ev = ev or {}
        self.journal.append_event(pool_id, run_id, {"event_type": event_type, "finalize_run_id": finalize_id, "pool_id": pool_id, "item_id": transition.next_action_payload.get("item_id", ""), "run_id": run_id or finalize_id, "status": status, "from_status": transition.from_status, "to_status": transition.to_status, "next_action": transition.next_action, "evidence_type": transition.evidence_type, "evidence_run_id": transition.evidence_run_id, "warning_count": len(ev.get("warnings") or transition.warnings or []), "error_count": len(transition.errors or []), "safe_apply_executed": False, "verification_executed": False, "bounded_retry_executed": False, "patch_regeneration_executed": False, "approval_executed": False, "rollback_executed": False, "restore_executed": False, "debug_review_executed": False, "created_at": self._now()})
