from __future__ import annotations

from typing import Any

from agent.atlas_auto_policy_schema import AtlasAutoPolicyPreset, AtlasAutomationDecision
from agent.atlas_automation_profile_resolver import normalize_automation_profile
from agent.atlas_critical_event_policy import normalize_critical_event
from agent.atlas_plan_item_file_changes import has_file_change_content, normalize_plan_item_file_changes


class AtlasAutomationGateService:
    def decide_pre_safe_apply(self, pool: Any, item: Any, preset: AtlasAutoPolicyPreset) -> AtlasAutomationDecision:
        reasons: list[str] = []
        warnings: list[str] = []
        normalize_plan_item_file_changes(item)
        meta = getattr(item, "metadata", {}) or {}
        action_type = str(meta.get("action_type") or "update").lower()
        risk = str(getattr(item, "risk_level", "")).lower()
        item_type = str(getattr(item, "item_type", "")).lower()
        target_files = list(getattr(item, "target_files", []) or [])
        status = str(getattr(item, "status", "")).lower()
        approval = str((meta.get("approval") or {}).get("decision") or "").lower()
        patch_approval = str((meta.get("patch_proposal_approval") or {}).get("decision") or "").lower()
        source_proposal_id = str((meta.get("patch_proposal_planitem") or {}).get("source_proposal_id") or meta.get("source_proposal_id") or "")
        resolved_profile = normalize_automation_profile(
            preset_id=str(getattr(preset, "preset_id", "") or ""),
            automation_level=str(getattr(preset, "automation_level", "") or ""),
            envelope_id=str(meta.get("envelope_id") or ""),
            envelope_active=bool(meta.get("envelope_active")),
            self_improvement=bool(meta.get("self_improvement")),
            strict_gate_approved=bool(meta.get("strict_gate_approved")),
        )

        if preset.preset_id == "manual_only":
            return AtlasAutomationDecision(pool_id=pool.pool_id, item_id=item.item_id, preset_id=preset.preset_id, decision="require_manual", reasons=["manual_only_preset"], warnings=[], metadata={"action_type": action_type, "automation_profile": resolved_profile})

        if action_type in set(preset.forbidden_action_types): reasons.append("forbidden_action_type")
        if action_type not in set(preset.allowed_action_types): reasons.append("unsupported_action")
        # Respect the preset's allowed_risk_levels (a full-automation preset opts into medium/high);
        # don't hardcode a low-only ceiling here, or no preset could ever permit higher risk.
        if risk == "critical": reasons.append("critical_risk_not_allowed")
        if risk not in set(preset.allowed_risk_levels): reasons.append("risk_not_allowed")
        if item_type not in set(preset.allowed_item_types): reasons.append("item_type_not_allowed")
        if not preset.allow_auto_safe_apply: reasons.append("auto_safe_apply_disabled")
        if not target_files: reasons.append("target_files_missing")
        if len(target_files) > int(preset.max_changed_files_per_item): reasons.append("target_files_too_many")
        if any((str(p).startswith("/") or ".." in str(p).split("/")) for p in target_files): reasons.append("unsafe_path")
        if any(str(p).startswith((".git/", "/etc/", "../")) for p in target_files): reasons.append("protected_path")
        if preset.require_planitem_approval and approval != "approved": reasons.append("approval_missing")
        if preset.require_patch_proposal_approval and (patch_approval != "approved" and not source_proposal_id): reasons.append("patch_proposal_approval_missing")
        if preset.require_project_path and not str(getattr(pool, "project_path", "") or "").strip(): reasons.append("project_path_missing")
        if str(meta.get("safe_apply_status") or "").lower() in {"applied", "completed"}: reasons.append("already_safe_applied")
        if str(meta.get("restored") or "").lower() in {"true", "1", "yes"}: reasons.append("already_restored")
        if status in {"completed", "failed", "cancelled", "skipped", "blocked"}: reasons.append("terminal_status")
        if preset.require_snapshot_before_apply and not (meta.get("require_snapshot_before_apply") in (True, "true", "1") or True):
            warnings.append("snapshot_requirement_unclear")
        content_candidates = [
            meta.get("proposed_content"),
            meta.get("patch"),
            meta.get("unified_diff_preview"),
            (meta.get("patch_proposal") or {}).get("proposed_content"),
            (meta.get("patch_proposal") or {}).get("unified_diff_preview"),
        ]
        file_changes = meta.get("file_changes") if isinstance(meta.get("file_changes"), list) else []
        file_change_content = bool(file_changes) and all(isinstance(fc, dict) and has_file_change_content(fc) for fc in file_changes)
        if preset.require_executor_readable_patch and not (any(isinstance(v, str) and v.strip() for v in content_candidates) or file_change_content):
            reasons.append("content_missing")

        decision = "allow"
        critical_reasons = {"critical_risk_not_allowed", "forbidden_action_type", "unsafe_path", "protected_path"}
        critical_event = None
        if any(r in critical_reasons for r in reasons):
            critical_event = normalize_critical_event(
                category="safe_apply_gate",
                severity="critical" if "critical_risk_not_allowed" in reasons else "high",
                reason="Critical event detected before safe_apply",
                affected_files=target_files,
                affected_capabilities=sorted(set(reasons) & critical_reasons),
                estimated_impact="Autonomous safe_apply may affect protected paths, forbidden actions, or critical-risk work.",
                source_gate="safe_apply_gate",
                extra={"full_auto_bypass_allowed": False},
            )
        if reasons:
            # Forbidden/direct execution invariants remain disabled unless separately gated, but every
            # critical finding is still surfaced as a critical decision instead of being auto-continued.
            block_reasons = {"forbidden_action_type", "unsupported_action", "risk_not_allowed", "target_files_too_many", "target_files_missing", "unsafe_path", "content_missing", "terminal_status"}
            decision = "require_manual" if critical_event and "critical_risk_not_allowed" in reasons else ("block" if any(r in block_reasons for r in reasons) else "require_manual")
        metadata = {"action_type": action_type, "risk_level": risk, "target_file_count": len(target_files), "automation_profile": resolved_profile}
        if critical_event:
            metadata["critical_event"] = critical_event
            metadata["status"] = "waiting_for_critical_decision"
        # Human override after a post-clarification safety block: when a user has explicitly granted a
        # safety override for this pool (via the override endpoint, only reachable from
        # "blocked_safety_review"), treat a NON-critical block/require_manual as approved-by-human so
        # the apply-time gate proceeds instead of silently re-blocking (Patch 0/N). Critical events
        # (critical risk / forbidden action / unsafe or protected path) are NEVER overridable here.
        pool_meta = getattr(pool, "metadata", {}) or {}
        override_granted = bool(pool_meta.get("safety_override_granted_after_clarification"))
        if override_granted and not critical_event and decision in {"block", "require_manual"}:
            warnings.append("safety_override_granted_after_clarification")
            metadata["safety_override_applied"] = True
            metadata["safety_override_original_decision"] = decision
            metadata["safety_override_overridden_reasons"] = sorted(set(reasons))
            decision = "allow"
        return AtlasAutomationDecision(pool_id=pool.pool_id, item_id=item.item_id, preset_id=preset.preset_id, decision=decision, phase="pre_safe_apply", reasons=sorted(set(reasons)), warnings=sorted(set(warnings)), metadata=metadata)
