from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agent.atlas_llm_evaluator_client import AtlasEvaluatorLLMClient, AtlasEvaluatorNullLLMClient
from agent.atlas_llm_evaluator_policies import get_evaluator_policy
from agent.atlas_llm_evaluator_schema import AtlasEvaluationInputPacket, AtlasEvaluatorDecision, AtlasEvaluatorRequest, AtlasEvaluatorResult


class AtlasLLMEvaluatorService:
    def __init__(self, journal=None, llm_client: AtlasEvaluatorLLMClient | None = None):
        self.journal = journal
        self.llm_client = llm_client or AtlasEvaluatorNullLLMClient()

    def evaluate(self, request: AtlasEvaluatorRequest) -> AtlasEvaluatorResult:
        policy = get_evaluator_policy(request.policy_id)
        eval_id = f"eval_{uuid4().hex[:10]}"
        warnings: list[str] = []
        errors: list[str] = []
        self.emit_event("evaluator_started", request, eval_id, "manual_required", 0.0, "")
        packet, context_bundle_id = self.build_input_packet(request, policy, warnings)
        if policy.require_context_bundle and not packet.context_bundle:
            decision = AtlasEvaluatorDecision(decision="manual_required", confidence=0.6, reasons=["context_bundle_required"], risks=["missing_context"], recommended_next_actions=["Run context refresh and evaluate again."], requires_manual_review=True)
            result = self.save_result(eval_id, request, policy.policy_id, "blocked", decision, packet, context_bundle_id, "", "", warnings, errors, used_llm=False, used_fallback=True, overridden=False)
            self.emit_event("evaluator_blocked", request, eval_id, decision.decision, decision.confidence, context_bundle_id)
            return result
        prompt = self.build_prompt(packet)
        if len(prompt) > min(request.max_prompt_chars, policy.max_prompt_chars):
            prompt = prompt[: min(request.max_prompt_chars, policy.max_prompt_chars)]
            warnings.append("prompt_truncated")
        raw = ""
        used_llm = False
        status = "fallback_evaluated"
        decision = self.fallback_decision(packet)
        if policy.allow_llm and not isinstance(self.llm_client, AtlasEvaluatorNullLLMClient):
            try:
                raw = self.llm_client.evaluate(prompt, {"policy_id": policy.policy_id})
                used_llm = True
                status = "evaluated"
                decision = self.parse_decision(raw)
            except Exception:
                warnings.append("llm_unavailable")
        elif policy.policy_id == "manual_review_only":
            decision = AtlasEvaluatorDecision(decision="manual_required", confidence=0.9, reasons=["manual_review_policy"], risks=["automation_disabled_by_policy"], recommended_next_actions=["Manual review required by policy."], requires_manual_review=True)
        overridden = self.validate_decision(decision, packet, policy)
        if overridden:
            warnings.append("decision_overridden_by_policy")
            self.emit_event("evaluator_policy_override", request, eval_id, decision.decision, decision.confidence, context_bundle_id)
        if status == "fallback_evaluated":
            self.emit_event("evaluator_fallback_used", request, eval_id, decision.decision, decision.confidence, context_bundle_id)
        result = self.save_result(eval_id, request, policy.policy_id, status, decision, packet, context_bundle_id, prompt[:1000], raw[:4000], warnings, errors, used_llm=used_llm, used_fallback=not used_llm, overridden=overridden)
        self.emit_event("evaluator_completed", request, eval_id, decision.decision, decision.confidence, context_bundle_id)
        return result

    def build_input_packet(self, request, policy, warnings):
        bundle = {}
        context_bundle_id = request.context_bundle_id
        if request.use_latest_context_bundle and request.pool_id:
            root = Path("ca_data") / "atlas" / "context_bundles" / request.pool_id
            if context_bundle_id:
                p = root / f"{context_bundle_id}.json"
                if p.exists():
                    bundle = json.loads(p.read_text(encoding="utf-8"))
                else:
                    warnings.append("context_bundle_unavailable")
            elif root.exists():
                files = sorted(root.glob("ctx_*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
                if files:
                    bundle = json.loads(files[0].read_text(encoding="utf-8"))
                    context_bundle_id = bundle.get("bundle_id", "")
                else:
                    warnings.append("context_bundle_missing")
        changed_files = request.changed_files or bundle.get("changed_files") or []
        packet = AtlasEvaluationInputPacket(pool_id=request.pool_id, item_id=request.item_id, run_id=request.run_id, trigger=request.trigger, policy_id=policy.policy_id, changed_files=changed_files, context_bundle=bundle, verification_result=request.verification_result, safe_apply_result=request.safe_apply_result, failure_stop_suggestion=request.failure_stop_suggestion, related_tests=bundle.get("related_tests") or [], dependency_edges=bundle.get("dependency_edges") or [], warnings=list(warnings), metadata=dict(request.metadata or {}))
        return packet, context_bundle_id

    def build_prompt(self, packet):
        return json.dumps(packet.model_dump(), ensure_ascii=False)

    def parse_decision(self, raw):
        try:
            data = json.loads(raw)
        except Exception:
            return AtlasEvaluatorDecision(decision="manual_required", confidence=0.6, reasons=["llm_json_parse_failed"], risks=["invalid_llm_output"], recommended_next_actions=["Review evaluator output format."], requires_manual_review=True)
        return AtlasEvaluatorDecision(**data)

    def fallback_decision(self, packet):
        vr = str((packet.verification_result or {}).get("status") or "").lower()
        sr = str((packet.safe_apply_result or {}).get("status") or "").lower()
        changed = bool((packet.safe_apply_result or {}).get("actual_file_changed", False))
        if vr == "failed":
            return AtlasEvaluatorDecision(decision="stop", confidence=0.85, reasons=["verification failed"], risks=["regression risk"], recommended_next_actions=["Review verification failure", "Run Debug Review manually"], requires_manual_review=True, should_run_debug_review=True)
        if sr in {"failed", "blocked"}:
            return AtlasEvaluatorDecision(decision="revise", confidence=0.75, reasons=["safe_apply_not_applied"], risks=["patch_not_applied"], recommended_next_actions=["Revise patch and rerun safe_apply."], requires_manual_review=True)
        if vr == "passed" and sr == "applied" and changed:
            return AtlasEvaluatorDecision(decision="continue", confidence=0.75, reasons=["verification passed after applied safe_apply"], risks=[], recommended_next_actions=["Proceed with manual confirmation of next step."], requires_manual_review=False)
        return AtlasEvaluatorDecision(decision="manual_required", confidence=0.6, reasons=["insufficient_signals"], risks=["incomplete_evidence"], recommended_next_actions=["Gather missing context and verify manually."], requires_manual_review=True)

    def validate_decision(self, decision, packet, policy):
        overridden = False
        if decision.decision not in {"continue", "stop", "revise", "manual_required"}:
            decision.decision = "manual_required"; overridden = True
        decision.confidence = max(0.0, min(1.0, float(decision.confidence)))
        vr = str((packet.verification_result or {}).get("status") or "").lower()
        if vr == "failed" and decision.decision == "continue":
            decision.decision = "stop"; decision.requires_manual_review = True; overridden = True
        if not policy.allow_continue_on_failed_verification and vr == "failed" and decision.decision == "continue":
            decision.decision = "stop"; overridden = True
        decision.should_continue_autopilot = False
        if not decision.reasons: decision.reasons = ["decision_validated"]
        if not decision.recommended_next_actions: decision.recommended_next_actions = ["Manual review."]
        return overridden

    def save_result(self, eval_id, request, policy_id, status, decision, packet, context_bundle_id, prompt_preview, raw, warnings, errors, *, used_llm, used_fallback, overridden):
        created = datetime.now(timezone.utc).isoformat()
        result = AtlasEvaluatorResult(pool_id=request.pool_id, item_id=request.item_id, run_id=request.run_id, trigger=request.trigger, policy_id=policy_id, status=status, decision=decision, input_packet=packet, context_bundle_id=context_bundle_id, prompt_preview=prompt_preview, raw_llm_output=raw, warnings=warnings, errors=errors, metadata={"eval_id": eval_id, "context_bundle_id": context_bundle_id, "prompt_chars": len(prompt_preview), "raw_output_chars": len(raw), "used_llm": used_llm, "used_fallback": used_fallback, "decision_overridden_by_policy": overridden, "policy_id": policy_id, "trigger": request.trigger, "created_at": created}, created_at=created)
        root = Path("ca_data") / "atlas" / "evaluator_results" / request.pool_id
        root.mkdir(parents=True, exist_ok=True)
        (root / f"{eval_id}.json").write_text(json.dumps(result.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
        (root / f"{eval_id}.md").write_text(f"# {eval_id}\n\n- decision: {decision.decision}\n- confidence: {decision.confidence}\n- status: {status}\n", encoding="utf-8")
        return result

    def emit_event(self, event_type, request, eval_id, decision, confidence, context_bundle_id):
        if not self.journal or not request.run_id:
            return
        self.journal.append_event(request.pool_id, request.run_id, {"event_type": event_type, "pool_id": request.pool_id, "item_id": request.item_id, "run_id": request.run_id, "status": "ok", "warnings": [], "errors": [], "created_at": datetime.now(timezone.utc).isoformat(), "metadata": {"eval_id": eval_id, "trigger": request.trigger, "policy_id": request.policy_id, "decision": decision, "confidence": confidence, "context_bundle_id": context_bundle_id}})
