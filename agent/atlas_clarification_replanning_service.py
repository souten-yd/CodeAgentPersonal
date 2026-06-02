from __future__ import annotations

import re
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

from agent.atlas_auto_policy_presets import atlas_auto_policy_presets
from agent.atlas_automation_gate_service import AtlasAutomationGateService
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_quality_gate import apply_plan_quality_gate

_HIGH_RISK_TERMS = (
    "security", "credential", "secret", "token", "delete", "destructive",
    "data loss", "runtime", "self-improvement", "self improvement",
    "command execution", "run_command", "shell", "remote git",
    "direct merge", "stable runtime",
)

_PATH_RE = re.compile(r"(?P<path>[\w./-]+\.(?:py|js|ts|tsx|jsx|html|css|md|json|yaml|yml|txt))")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AtlasClarificationReplanningService:
    """Revise a PlanPool after clarification answers, then rerun gates."""

    def revise_after_answers(
        self,
        pool: AtlasPlanPool,
        *,
        preset_id: str = "guarded_low_risk",
        automation_level: str = "",
        critical_handling: str = "ask",
    ) -> dict:
        try:
            return self._revise_after_answers_success(
                pool,
                preset_id=preset_id,
                automation_level=automation_level,
                critical_handling=critical_handling,
            )
        except Exception as exc:
            return self.mark_replanning_failed(pool, exc)

    def _revise_after_answers_success(
        self,
        pool: AtlasPlanPool,
        *,
        preset_id: str = "guarded_low_risk",
        automation_level: str = "",
        critical_handling: str = "ask",
    ) -> dict:
        metadata = pool.metadata if isinstance(pool.metadata, dict) else {}
        answers = [dict(a) for a in metadata.get("clarification_answers") or [] if isinstance(a, dict)]
        original_pool_snapshot = self._pool_payload(pool)
        original_requirement = str(metadata.get("original_requirement_summary") or pool.root_goal or "")
        answer_summary = self._answer_summary(answers)
        selected_option_impacts = self._selected_option_impacts(answers)
        revised_requirement = self._revised_requirement_summary(original_requirement, answer_summary)
        extracted_paths = self._extract_target_files(answer_summary)
        risk_raised = self._raises_risk(answer_summary, answers)
        scope_reduced = self._reduces_scope(answers)

        pool.root_goal = revised_requirement
        revised_items = []
        for item in pool.items:
            revised_items.append(
                self._revise_item(
                    item,
                    answer_summary=answer_summary,
                    extracted_paths=extracted_paths,
                    risk_raised=risk_raised,
                    scope_reduced=scope_reduced,
                    selected_option_impacts=selected_option_impacts,
                )
            )
        allowed_paths_after_clarification = self._allowed_paths_after_clarification(revised_items)
        item_changed_fields = self._item_changed_fields(revised_items)

        revised_plan = self._build_revised_plan(pool, answers, risk_raised=risk_raised)
        critique_gate = apply_plan_quality_gate(
            revised_plan,
            automation_level=automation_level or pool.automation_level,
            preset_id=preset_id,
            critical_handling=critical_handling,
        )
        safety_gate = self._rerun_safety_gate(pool, revised_items[0] if revised_items else None, preset_id)
        next_status = self._next_status(critique_gate, safety_gate, risk_raised)
        pool.status = next_status

        revision_id = f"clar_rev_{uuid4().hex[:12]}"
        revised_plan_summary = self._revised_plan_summary(revised_requirement, len(revised_items))
        changed_scope_summary = self._changed_scope_summary(
            allowed_paths_after_clarification,
            scope_reduced=scope_reduced,
            risk_raised=risk_raised,
        )
        gate_rerun_summary = self._gate_rerun_summary(critique_gate, safety_gate)
        metadata.update(
            {
                "clarification_replanning": {
                    "status": "completed",
                    "revision_id": revision_id,
                    "decision_id": f"clar_decision_{uuid4().hex[:12]}",
                    "answered_question_count": len(answers),
                    "revised_at": _utc_now_iso(),
                    "risk_raised": risk_raised,
                    "scope_reduced": scope_reduced,
                    "target_files_from_answer": extracted_paths,
                    "allowed_paths_after_clarification": allowed_paths_after_clarification,
                    "item_changed_fields": item_changed_fields,
                    "selected_option_impacts": selected_option_impacts,
                },
                "original_requirement_summary": original_requirement,
                "revised_requirement_summary": revised_requirement,
                "original_plan_snapshot": original_pool_snapshot,
                "revised_plan_snapshot": self._pool_payload(pool),
                "plan_revision_diff": {
                    "root_goal_changed": revised_requirement != original_requirement,
                    "target_files_from_answer": extracted_paths,
                    "risk_raised": risk_raised,
                    "scope_reduced": scope_reduced,
                    "allowed_paths_after_clarification": allowed_paths_after_clarification,
                    "blocked_paths_after_clarification": [],
                    "item_changed_fields": item_changed_fields,
                    "selected_option_impacts": selected_option_impacts,
                },
                "allowed_paths_after_clarification": allowed_paths_after_clarification,
                "blocked_paths_after_clarification": [],
                "gate_rerun_required_after_clarification": False,
                "gate_rerun_performed_after_clarification": True,
                "plan_revision_required_after_clarification": False,
                "rerun_critique_gate_after_clarification": critique_gate,
                "rerun_safety_gate_after_clarification": safety_gate,
                "revised_plan_summary": revised_plan_summary,
                "changed_scope_summary": changed_scope_summary,
                "gate_rerun_summary": gate_rerun_summary,
                "next_required_user_action": self._next_required_user_action(next_status),
            }
        )
        if critique_gate.get("critical_event"):
            metadata["critical_event"] = critique_gate["critical_event"]
            metadata["critical_event_status"] = "waiting_for_critical_decision"
        pool.metadata = metadata
        return {
            "revision_id": revision_id,
            "status": next_status,
            "allowed_paths_after_clarification": allowed_paths_after_clarification,
            "revised_plan_snapshot": metadata["revised_plan_snapshot"],
            "plan_revision_diff": metadata["plan_revision_diff"],
            "rerun_critique_gate": critique_gate,
            "rerun_safety_gate": safety_gate,
            "revised_plan_summary": revised_plan_summary,
            "changed_scope_summary": changed_scope_summary,
            "gate_rerun_summary": gate_rerun_summary,
            "next_required_user_action": metadata["next_required_user_action"],
        }

    def mark_replanning_failed(self, pool: AtlasPlanPool, exc: Exception) -> dict:
        metadata = pool.metadata if isinstance(pool.metadata, dict) else {}
        answers = [dict(a) for a in metadata.get("clarification_answers") or [] if isinstance(a, dict)]
        failure = {
            "status": "failed",
            "revision_id": f"clar_rev_failed_{uuid4().hex[:12]}",
            "decision_id": f"clar_decision_failed_{uuid4().hex[:12]}",
            "answered_question_count": len(answers),
            "failed_at": _utc_now_iso(),
            "error_summary": self._bounded_error_summary(exc),
        }
        metadata.update(
            {
                "clarification_replanning": failure,
                "plan_revision_required_after_clarification": True,
                "gate_rerun_required_after_clarification": True,
                "gate_rerun_performed_after_clarification": False,
                "revised_plan_summary": "Plan revision failed; original unclarified plan remains blocked.",
                "changed_scope_summary": "No revised scope was accepted.",
                "gate_rerun_summary": "Gate rerun was not accepted because clarification replanning failed.",
                "next_required_user_action": "Review the clarification failure and request a safer revised plan or cancel.",
            }
        )
        pool.metadata = metadata
        if pool.status == "ready":
            pool.status = "approval_required"
        return {
            **failure,
            "blocked_reasons": [
                "plan_revision_required_after_clarification",
                "gate_rerun_required_after_clarification",
            ],
            "next_required_user_action": metadata["next_required_user_action"],
        }

    @staticmethod
    def critical_ambiguity_requires_user(text: str) -> bool:
        lowered = str(text or "").lower()
        return any(term in lowered for term in _HIGH_RISK_TERMS)

    def _revise_item(
        self,
        item: AtlasPlanItem,
        *,
        answer_summary: str,
        extracted_paths: list[str],
        risk_raised: bool,
        scope_reduced: bool,
        selected_option_impacts: list[dict],
    ) -> AtlasPlanItem:
        changed_fields: list[str] = []
        primary_impact = selected_option_impacts[0] if selected_option_impacts else {}
        plan_change_summary = str(primary_impact.get("plan_change_summary") or "").strip()
        implementation_scope = str(primary_impact.get("implementation_scope") or "").strip()
        risk_level_from_option = str(primary_impact.get("risk_level") or "").strip()
        item.metadata.setdefault("clarification_revision", {})
        item.metadata["clarification_revision"].update(
            {
                "answer_summary": answer_summary,
                "risk_raised": risk_raised,
                "scope_reduced": scope_reduced,
                "selected_option_impacts": selected_option_impacts,
                "revised_at": _utc_now_iso(),
            }
        )
        if answer_summary:
            goal_addition = plan_change_summary or answer_summary
            item.goal = self._append_sentence(item.goal, f"Clarification decision: {goal_addition}")
            item.description = self._append_sentence(item.description, f"Clarification: {answer_summary}")
            item.expected_changes = self._append_unique(item.expected_changes, f"Apply clarification answer: {answer_summary}")
            item.done_definition = self._append_unique(item.done_definition, f"Clarification reflected: {answer_summary}")
            changed_fields.extend(["goal", "description", "expected_changes", "done_definition"])
        if implementation_scope:
            item.metadata["implementation_scope_after_clarification"] = implementation_scope
            item.done_definition = self._append_unique(
                item.done_definition,
                f"Implementation scope after clarification: {implementation_scope}",
            )
            if "done_definition" not in changed_fields:
                changed_fields.append("done_definition")
        if risk_level_from_option:
            item.metadata["option_risk_level_after_clarification"] = risk_level_from_option
        if extracted_paths:
            item.target_files = extracted_paths
            item.metadata["allowed_paths_after_clarification"] = extracted_paths
            changed_fields.append("target_files")
        elif scope_reduced and len(item.target_files) > 1:
            item.target_files = item.target_files[:1]
            item.metadata["allowed_paths_after_clarification"] = list(item.target_files)
            changed_fields.append("target_files")
        if selected_option_impacts:
            item.metadata["verification_intent_after_clarification"] = {
                "gate_rerun_required": any(bool(i.get("gate_rerun_required")) for i in selected_option_impacts),
                "can_continue_after_answer": all(bool(i.get("can_continue_after_answer")) for i in selected_option_impacts),
                "selected_option_impacts": selected_option_impacts,
            }
            item.test_commands = self._append_unique(
                item.test_commands,
                "rerun critique and safety gates after clarification",
            )
            changed_fields.append("test_commands")
        if "test" in answer_summary.lower() or "smoke" in answer_summary.lower():
            existing_intent = item.metadata.get("verification_intent_after_clarification")
            existing_payload = existing_intent if isinstance(existing_intent, dict) else {}
            item.metadata["verification_intent_after_clarification"] = {
                **existing_payload,
                "answer_summary": answer_summary,
                "selected_verification": answer_summary,
                "gate_rerun_required": bool(existing_payload.get("gate_rerun_required", True)),
                "can_continue_after_answer": bool(existing_payload.get("can_continue_after_answer", False)),
            }
            item.test_commands = self._append_unique(item.test_commands, "focused verification selected by clarification")
            if "test_commands" not in changed_fields:
                changed_fields.append("test_commands")
        if risk_raised:
            item.risk_level = "high"
            item.requires_user_confirmation = True
            changed_fields.extend(["risk_level", "requires_user_confirmation"])
            if item.status in {"queued", "ready", "approved"}:
                item.status = "approval_required"
                changed_fields.append("status")
        item.metadata["clarification_revision"]["changed_fields"] = sorted(set(changed_fields))
        return item

    @staticmethod
    def _append_sentence(base: str, addition: str) -> str:
        if not addition:
            return base or ""
        if not base:
            return addition
        if addition in base:
            return base
        return f"{base.rstrip()} {addition}"

    @staticmethod
    def _append_unique(values: list[str], value: str) -> list[str]:
        out = list(values or [])
        if value and value not in out:
            out.append(value)
        return out

    @staticmethod
    def _allowed_paths_after_clarification(items: list[AtlasPlanItem]) -> list[str]:
        out: list[str] = []
        for item in items:
            for path in item.target_files or []:
                text = str(path or "").replace("\\", "/").strip()
                if text and text not in out:
                    out.append(text)
        return out

    @staticmethod
    def _item_changed_fields(items: list[AtlasPlanItem]) -> list[dict]:
        out: list[dict] = []
        for item in items:
            revision = item.metadata.get("clarification_revision") if isinstance(item.metadata, dict) else {}
            changed_fields = list((revision or {}).get("changed_fields") or [])
            out.append({"item_id": item.item_id, "changed_fields": changed_fields})
        return out

    @staticmethod
    def _answer_summary(answers: list[dict]) -> str:
        parts = []
        for answer in answers:
            option = answer.get("selected_option") or {}
            label = str(option.get("label") or answer.get("option_id") or "").strip()
            text = str(answer.get("answer_text") or answer.get("note") or "").strip()
            impact = answer.get("selected_option_impact") if isinstance(answer.get("selected_option_impact"), dict) else {}
            plan_change = str(impact.get("plan_change_summary") or option.get("plan_change_summary") or "").strip()
            scope = str(impact.get("implementation_scope") or option.get("implementation_scope") or "").strip()
            risk = str(impact.get("risk_level") or option.get("risk_level") or "").strip()
            detail = "; ".join(part for part in (plan_change, f"scope={scope}" if scope else "", f"risk={risk}" if risk else "", text) if part)
            if label and detail:
                parts.append(f"{label}: {detail}")
            elif detail:
                parts.append(detail)
            elif label:
                parts.append(label)
            elif text:
                parts.append(text)
        return "; ".join(parts)

    @staticmethod
    def _selected_option_impacts(answers: list[dict]) -> list[dict]:
        impacts: list[dict] = []
        for answer in answers:
            impact = answer.get("selected_option_impact")
            if isinstance(impact, dict) and impact:
                impacts.append({"question_id": str(answer.get("question_id") or ""), **impact})
        return impacts

    @staticmethod
    def _revised_requirement_summary(original: str, answer_summary: str) -> str:
        if not answer_summary:
            return original
        return f"{original.rstrip()}\n\nClarification answers applied:\n{answer_summary}"

    @staticmethod
    def _extract_target_files(text: str) -> list[str]:
        paths: list[str] = []
        for match in _PATH_RE.finditer(text or ""):
            path = match.group("path").replace("\\", "/")
            if path.startswith("/") or ".." in path.split("/"):
                continue
            if path not in paths:
                paths.append(path)
        return paths[:8]

    def _raises_risk(self, answer_summary: str, answers: list[dict]) -> bool:
        if self.critical_ambiguity_requires_user(answer_summary):
            return True
        return any(self.critical_ambiguity_requires_user(str(a.get("reason") or "")) for a in answers)

    @staticmethod
    def _reduces_scope(answers: list[dict]) -> bool:
        reduced_option_ids = {"minimal_scope", "defer_or_change_scope"}
        return any(str(a.get("option_id") or "") in reduced_option_ids for a in answers)

    @staticmethod
    def _build_revised_plan(pool: AtlasPlanPool, answers: list[dict], *, risk_raised: bool) -> dict:
        findings = []
        if risk_raised:
            findings.append(
                {
                    "severity": "critical",
                    "angle": "clarification_risk",
                    "title": "Clarification raised safety-sensitive scope",
                    "detail": "User clarification mentioned security, deletion, runtime, command execution, remote git, direct merge, stable runtime, or self-improvement scope.",
                    "recommendation": "Require explicit user decision before implementation.",
                }
            )
        return {
            "requirement_summary": pool.root_goal,
            "goal": pool.root_goal,
            "implementation_steps": [item.model_dump() for item in pool.items],
            "clarification_answers": answers,
            "adversarial_critique": {
                "requires_revision": bool(findings),
                "consensus_risk": "critical" if findings else "low",
                "findings": findings,
            },
        }

    @staticmethod
    def _rerun_safety_gate(pool: AtlasPlanPool, item: AtlasPlanItem | None, preset_id: str) -> dict:
        if item is None:
            return {"decision": "block", "reason": "no_plan_items"}
        presets = atlas_auto_policy_presets()
        preset = presets.get(preset_id) or presets["guarded_low_risk"]
        return AtlasAutomationGateService().decide_pre_safe_apply(pool, item, preset).model_dump()

    @staticmethod
    def _next_status(critique_gate: dict, safety_gate: dict, risk_raised: bool) -> str:
        if critique_gate.get("critical_event"):
            return "waiting_for_critical_decision"
        if risk_raised:
            return "approval_required"
        if str(safety_gate.get("decision") or "") == "allow":
            return "ready"
        return "approval_required"

    @staticmethod
    def _next_required_user_action(status: str) -> str:
        if status == "waiting_for_critical_decision":
            return "Review critical clarification risk and choose approve, safer replan, edit scope, or cancel."
        if status == "approval_required":
            return "Review revised plan and approve or request another revision."
        return "Revised plan is gate-checked and ready for bounded execution."

    @staticmethod
    def _revised_plan_summary(revised_requirement: str, item_count: int) -> str:
        summary = str(revised_requirement or "Revised plan").strip()
        if len(summary) > 160:
            summary = summary[:157].rstrip() + "..."
        return f"Plan revised and gates rerun for {item_count} item(s): {summary}"

    @staticmethod
    def _changed_scope_summary(allowed_paths: list[str], *, scope_reduced: bool, risk_raised: bool) -> str:
        parts = []
        if allowed_paths:
            parts.append("allowed paths: " + ", ".join(allowed_paths[:8]))
        if scope_reduced:
            parts.append("scope reduced")
        if risk_raised:
            parts.append("risk raised for user review")
        return "; ".join(parts) if parts else "No explicit path scope change."

    @staticmethod
    def _gate_rerun_summary(critique_gate: dict, safety_gate: dict) -> str:
        critique_status = str(critique_gate.get("status") or critique_gate.get("decision") or "checked")
        safety_status = str(safety_gate.get("decision") or safety_gate.get("status") or "checked")
        return f"critique gate: {critique_status}; safety gate: {safety_status}"

    @staticmethod
    def _bounded_error_summary(exc: Exception) -> str:
        message = f"{exc.__class__.__name__}: {exc}".replace("\n", " ").strip()
        return message[:200] if len(message) <= 200 else message[:197].rstrip() + "..."

    @staticmethod
    def _pool_payload(pool: AtlasPlanPool) -> dict:
        if hasattr(pool, "model_dump"):
            return pool.model_dump()
        return deepcopy(pool.dict())
