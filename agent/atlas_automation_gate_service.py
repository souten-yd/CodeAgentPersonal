from __future__ import annotations

from typing import Any

from agent.atlas_auto_policy_schema import AtlasAutoPolicyPreset, AtlasAutomationDecision


class AtlasAutomationGateService:
    def decide_pre_safe_apply(self, pool: Any, item: Any, preset: AtlasAutoPolicyPreset) -> AtlasAutomationDecision:
        reasons: list[str] = []
        warnings: list[str] = []
        meta = getattr(item, "metadata", {}) or {}
        action_type = str(meta.get("action_type") or "update").lower()
        risk = str(getattr(item, "risk_level", "")).lower()
        item_type = str(getattr(item, "item_type", "")).lower()
        target_files = list(getattr(item, "target_files", []) or [])
        status = str(getattr(item, "status", "")).lower()
        approval = str((meta.get("approval") or {}).get("decision") or "").lower()
        patch_approval = str((meta.get("patch_proposal_approval") or {}).get("decision") or "").lower()
        source_proposal_id = str((meta.get("patch_proposal_planitem") or {}).get("source_proposal_id") or meta.get("source_proposal_id") or "")

        if preset.preset_id == "manual_only":
            return AtlasAutomationDecision(pool_id=pool.pool_id, item_id=item.item_id, preset_id=preset.preset_id, decision="require_manual", reasons=["manual_only_preset"], warnings=[], metadata={"action_type": action_type})

        if action_type in set(preset.forbidden_action_types): reasons.append("forbidden_action_type")
        if action_type not in set(preset.allowed_action_types): reasons.append("unsupported_action")
        # Respect the preset's allowed_risk_levels (a full-automation preset opts into medium/high);
        # don't hardcode a low-only ceiling here, or no preset could ever permit higher risk.
        if risk not in set(preset.allowed_risk_levels): reasons.append("risk_not_allowed")
        if item_type not in set(preset.allowed_item_types): reasons.append("item_type_not_allowed")
        if not preset.allow_auto_safe_apply: reasons.append("auto_safe_apply_disabled")
        if not target_files: reasons.append("target_files_missing")
        if len(target_files) > int(preset.max_changed_files_per_item): reasons.append("target_files_too_many")
        if any((str(p).startswith("/") or ".." in str(p).split("/")) for p in target_files): reasons.append("unsafe_path")
        if any(str(p).startswith((".git/", "/etc/", "../")) for p in target_files): reasons.append("protected_path")
        if approval != "approved": reasons.append("approval_missing")
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
        if preset.require_executor_readable_patch and not any(isinstance(v, str) and v.strip() for v in content_candidates):
            reasons.append("content_missing")

        decision = "allow"
        if reasons:
            block_reasons = {"forbidden_action_type", "unsupported_action", "risk_not_allowed", "target_files_too_many", "target_files_missing", "unsafe_path", "protected_path", "content_missing", "terminal_status"}
            decision = "block" if any(r in block_reasons for r in reasons) else "require_manual"
        return AtlasAutomationDecision(pool_id=pool.pool_id, item_id=item.item_id, preset_id=preset.preset_id, decision=decision, phase="pre_safe_apply", reasons=sorted(set(reasons)), warnings=sorted(set(warnings)), metadata={"action_type": action_type, "risk_level": risk, "target_file_count": len(target_files)})
