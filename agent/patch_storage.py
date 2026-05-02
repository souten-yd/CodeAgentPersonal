from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from agent.patch_approval_schema import PatchApprovalRecord
from agent.patch_schema import PatchApplyResult, PatchProposal
from agent.verification_schema import VerificationResult


class PatchStorage:
    def __init__(self, ca_data_dir: str | Path) -> None:
        self.base_dir = Path(ca_data_dir)

    def _run_dir(self, run_id: str) -> Path:
        return self.base_dir / "runs" / run_id

    def _patches_dir(self, run_id: str) -> Path:
        p = self._run_dir(run_id) / "patches"
        p.mkdir(parents=True, exist_ok=True)
        return p


    def _patch_approvals_dir(self, run_id: str) -> Path:
        p = self._run_dir(run_id) / "patch_approvals"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _verification_dir(self, run_id: str) -> Path:
        p = self._run_dir(run_id) / "verification"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def save_patch_proposal(self, proposal: PatchProposal) -> None:
        pd = self._patches_dir(proposal.run_id)
        (pd / f"{proposal.patch_id}.patch.json").write_text(json.dumps(proposal.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
        (pd / f"{proposal.patch_id}.diff").write_text(proposal.unified_diff, encoding="utf-8")
        patch_md = (
            f"# Patch {proposal.patch_id}\n\n"
            f"- target: {proposal.target_file}\n"
            f"- status: {proposal.status}\n"
            f"- patch_type: {proposal.patch_type}\n"
            f"- generator: {proposal.generator or proposal.metadata.get('generator','')}\n"
            f"- apply_allowed: {proposal.apply_allowed}\n"
            f"- can_apply_reason: {proposal.can_apply_reason}\n"
            f"- safety_warnings: {'; '.join(proposal.safety_warnings or [])}\n"
            f"- original_block_summary: {(proposal.original_block or '')[:120].replace(chr(10), ' ')}\n"
            f"- replacement_block_summary: {(proposal.replacement_block or '')[:120].replace(chr(10), ' ')}\n"
        )
        (pd / f"{proposal.patch_id}.md").write_text(patch_md, encoding="utf-8")

    def save_apply_result(self, run_id: str, result: PatchApplyResult) -> None:
        pd = self._patches_dir(run_id)
        (pd / f"{result.patch_id}.apply.json").write_text(json.dumps(result.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")

    def save_verification_result(self, result: VerificationResult) -> None:
        vd = self._verification_dir(result.run_id)
        (vd / f"{result.verification_id}.verification.json").write_text(json.dumps(result.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
        (vd / f"{result.verification_id}.md").write_text(f"# Verification {result.verification_id}\n\n- status: {result.status}\n- summary: {result.summary}\n", encoding="utf-8")


    def load_verification_result(self, run_id: str, verification_id: str) -> dict:
        path = self._verification_dir(run_id) / f"{verification_id}.verification.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def list_patches(self, run_id: str) -> list[dict]:
        pd = self._patches_dir(run_id)
        out: list[dict] = []
        for path in sorted(pd.glob("*.patch.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            latest = self.find_latest_patch_approval(run_id, str(payload.get("patch_id", "")))
            if latest:
                payload.setdefault("approval_status", latest.status)
                payload.setdefault("approved_for_apply", latest.approved_for_apply)
                payload.setdefault("patch_approval_id", latest.patch_approval_id)
            else:
                payload.setdefault("approval_status", "pending")
                payload.setdefault("approved_for_apply", False)
                payload.setdefault("patch_approval_id", "")
            payload.setdefault("safety_warnings", payload.get("safety_warnings") or [])
            payload.setdefault("apply_allowed", bool(payload.get("apply_allowed", False)))
            payload.setdefault("unified_diff", payload.get("unified_diff", ""))
            out.append(payload)
        by_parent: dict[str, list[dict]] = {}
        for p in out:
            parent = str(p.get("reproposal_of_patch_id", "") or "")
            if parent:
                by_parent.setdefault(parent, []).append(p)
        for p in out:
            p["verification_failed"] = str(p.get("verification_status", "")) == "failed"
            children = by_parent.get(str(p.get("patch_id", "")), [])
            p["reproposal_count"] = len(children)
            p["has_reproposal"] = len(children) > 0
            p["latest_reproposal_patch_id"] = str(children[-1].get("patch_id", "")) if children else ""
        return out

    def load_patch(self, run_id: str, patch_id: str) -> dict:
        path = self._patches_dir(run_id) / f"{patch_id}.patch.json"
        return json.loads(path.read_text(encoding="utf-8"))


    def save_patch_approval(self, record: PatchApprovalRecord) -> None:
        ad = self._patch_approvals_dir(record.run_id)
        (ad / f"{record.patch_approval_id}.patch_approval.json").write_text(json.dumps(record.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
        (ad / f"{record.patch_approval_id}.patch_approval.md").write_text(
            f"# Patch Approval {record.patch_approval_id}\n\n- patch_id: {record.patch_id}\n- status: {record.status}\n- decision: {record.decision}\n",
            encoding="utf-8",
        )

    def load_patch_approval(self, run_id: str, patch_approval_id: str) -> dict:
        path = self._patch_approvals_dir(run_id) / f"{patch_approval_id}.patch_approval.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def find_latest_patch_approval(self, run_id: str, patch_id: str) -> PatchApprovalRecord | None:
        approvals = self.list_patch_approvals(run_id)
        filtered = [a for a in approvals if str(a.get("patch_id", "")) == patch_id]
        if not filtered:
            return None
        filtered.sort(key=lambda x: str(x.get("updated_at", "")))
        return PatchApprovalRecord(**filtered[-1])

    def list_patch_approvals(self, run_id: str) -> list[dict]:
        ad = self._patch_approvals_dir(run_id)
        out: list[dict] = []
        for path in sorted(ad.glob("*.patch_approval.json")):
            out.append(json.loads(path.read_text(encoding="utf-8")))
        return out

    def update_patch_payload(self, run_id: str, patch_id: str, updates: dict) -> dict:
        path = self._patches_dir(run_id) / f"{patch_id}.patch.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload.update(updates or {})
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload

    def get_patch_chain_summary(self, run_id: str, patch_id: str) -> dict:
        patches = self.list_patches(run_id)
        by_id: dict[str, dict] = {str(p.get("patch_id", "")): p for p in patches if str(p.get("patch_id", ""))}
        current = by_id.get(patch_id)
        if not current:
            raise ValueError("patch not found")

        by_parent: dict[str, list[dict]] = {}
        for p in patches:
            parent = str(p.get("reproposal_of_patch_id", "") or "")
            if parent:
                by_parent.setdefault(parent, []).append(p)

        seen: set[str] = set()
        lineage_rev: list[dict] = []
        cursor = current
        while cursor:
            cid = str(cursor.get("patch_id", ""))
            if not cid or cid in seen:
                break
            seen.add(cid)
            lineage_rev.append(cursor)
            parent_id = str(cursor.get("reproposal_of_patch_id", "") or "")
            cursor = by_id.get(parent_id) if parent_id else None

        chain = list(reversed(lineage_rev))
        root_patch_id = str(chain[0].get("patch_id", "")) if chain else patch_id
        parent_patch_id = str(current.get("reproposal_of_patch_id", "") or "")
        children = [str(x.get("patch_id", "")) for x in by_parent.get(patch_id, []) if str(x.get("patch_id", ""))]
        ancestor_reproposal_count = max(0, len(chain) - 1)
        child_reproposal_count = len(children)
        related_reproposal_count = ancestor_reproposal_count + child_reproposal_count
        reproposal_count_total = related_reproposal_count
        return {
            "run_id": run_id,
            "root_patch_id": root_patch_id,
            "current_patch_id": patch_id,
            "parent_patch_id": parent_patch_id,
            "children": children,
            "chain": [
                {
                    "patch_id": str(p.get("patch_id", "")),
                    "status": str(p.get("status", "")),
                    "verification_status": str(p.get("verification_status", "")),
                    "reproposal_of_patch_id": str(p.get("reproposal_of_patch_id", "")),
                    "created_at": str(p.get("created_at", "")),
                }
                for p in chain
            ],
            "ancestor_reproposal_count": ancestor_reproposal_count,
            "child_reproposal_count": child_reproposal_count,
            "related_reproposal_count": related_reproposal_count,
            "reproposal_count_total": reproposal_count_total,
            "reproposal_count_total_semantics": "ancestor_plus_direct_children",
        }

    def get_run_patch_dashboard_summary(
        self,
        run_id: str,
        manual_checks: list[dict] | None = None,
        telemetry: list[dict] | None = None,
    ) -> dict:
        patches = self.list_patches(run_id)
        manual_checks = manual_checks or []
        telemetry = telemetry or []
        manual_by_patch: dict[str, list[dict]] = {}
        telemetry_by_patch: dict[str, list[dict]] = {}
        for item in manual_checks:
            pid = str(item.get("patch_id", "") or "")
            if pid:
                manual_by_patch.setdefault(pid, []).append(item)
        for item in telemetry:
            pid = str(item.get("patch_id", "") or "")
            if pid:
                telemetry_by_patch.setdefault(pid, []).append(item)
        counts = {
            "total": 0,
            "apply_allowed": 0,
            "apply_blocked": 0,
            "pending": 0,
            "approved": 0,
            "rejected": 0,
            "applied": 0,
            "verification_failed": 0,
            "verification_passed": 0,
            "low_quality": 0,
            "quality_warnings": 0,
            "safety_warnings": 0,
            "has_telemetry": 0,
            "has_manual_check": 0,
            "has_reproposal": 0,
            "reproposal_patch": 0,
            "reproposal_candidates": 0,
            "total_manual_checks": len(manual_checks),
            "patches_with_manual_check": 0,
            "llm_telemetry_records": len(telemetry),
            "patches_with_telemetry": 0,
        }
        risk_counts: dict[str, int] = {}
        patch_type_counts: dict[str, int] = {}
        generator_counts: dict[str, int] = {}
        attention = {
            "blocked_patch_ids": [],
            "low_quality_patch_ids": [],
            "verification_failed_patch_ids": [],
            "unreviewed_patch_ids": [],
            "missing_telemetry_patch_ids": [],
            "missing_manual_check_patch_ids": [],
            "reproposal_needed_patch_ids": [],
        }
        out_patches: list[dict] = []
        for p in patches:
            patch_id = str(p.get("patch_id", "") or "")
            approval_status = str(p.get("approval_status", "") or "pending")
            applied = bool(p.get("applied", False) or approval_status == "applied")
            apply_allowed = bool(p.get("apply_allowed", False))
            verification_status = str(p.get("verification_status", "") or "")
            quality_score = float(p.get("quality_score", 0.0) or 0.0)
            safety_warnings = p.get("safety_warnings") or []
            quality_warnings = p.get("quality_warnings") or []
            metadata = p.get("metadata") if isinstance(p.get("metadata"), dict) else {}
            generator = str(p.get("generator", "") or "")
            patch_type = str(p.get("patch_type", "") or "")
            has_reproposal = bool(p.get("has_reproposal", False))
            reproposal_of_patch_id = str(p.get("reproposal_of_patch_id", "") or "")
            patch_manual_checks = manual_by_patch.get(patch_id, [])
            patch_telemetry = telemetry_by_patch.get(patch_id, [])
            has_manual_check = len(patch_manual_checks) > 0
            has_telemetry = bool(metadata.get("llm_telemetry_id") or metadata.get("fallback_telemetry_id") or patch_telemetry)
            attention_flags: list[str] = []
            if not apply_allowed:
                attention_flags.append("blocked")
            if safety_warnings:
                attention_flags.append("safety_warning")
            if quality_warnings:
                attention_flags.append("quality_warning")
            if quality_score < 0.4:
                attention_flags.append("low_quality")
            if approval_status in ("", "pending"):
                attention_flags.append("unreviewed")
            if approval_status == "approved" and not applied:
                attention_flags.append("approved_not_applied")
            if applied:
                attention_flags.append("applied")
            if verification_status == "failed":
                attention_flags.append("verification_failed")
            if verification_status == "passed":
                attention_flags.append("verification_passed")
            if has_reproposal:
                attention_flags.append("has_reproposal")
            if reproposal_of_patch_id:
                attention_flags.append("reproposal_patch")
            if generator == "llm_replace_block" and not has_telemetry:
                attention_flags.append("missing_telemetry")
            if generator == "llm_replace_block" and not has_manual_check:
                attention_flags.append("missing_manual_check")
            if approval_status == "rejected":
                attention_flags.append("rejected")
            is_reproposal_candidate = verification_status == "failed" and (not has_reproposal) and patch_type == "replace_block"
            counts["total"] += 1
            if apply_allowed:
                counts["apply_allowed"] += 1
            else:
                counts["apply_blocked"] += 1
            if approval_status in ("", "pending"):
                counts["pending"] += 1
            elif approval_status == "approved":
                counts["approved"] += 1
            elif approval_status == "rejected":
                counts["rejected"] += 1
            if applied:
                counts["applied"] += 1
            if verification_status == "failed":
                counts["verification_failed"] += 1
            if verification_status == "passed":
                counts["verification_passed"] += 1
            if quality_score < 0.4:
                counts["low_quality"] += 1
            if quality_warnings:
                counts["quality_warnings"] += 1
            if safety_warnings:
                counts["safety_warnings"] += 1
            if has_telemetry:
                counts["has_telemetry"] += 1
                counts["patches_with_telemetry"] += 1
            if has_manual_check:
                counts["has_manual_check"] += 1
                counts["patches_with_manual_check"] += 1
            if has_reproposal:
                counts["has_reproposal"] += 1
            if reproposal_of_patch_id:
                counts["reproposal_patch"] += 1
            if is_reproposal_candidate:
                counts["reproposal_candidates"] += 1
            risk_key = str(p.get("risk_level", "low") or "low").lower()
            risk_counts[risk_key] = risk_counts.get(risk_key, 0) + 1
            if patch_type:
                patch_type_counts[patch_type] = patch_type_counts.get(patch_type, 0) + 1
            if generator:
                generator_counts[generator] = generator_counts.get(generator, 0) + 1
            if "blocked" in attention_flags:
                attention["blocked_patch_ids"].append(patch_id)
            if "low_quality" in attention_flags:
                attention["low_quality_patch_ids"].append(patch_id)
            if "verification_failed" in attention_flags:
                attention["verification_failed_patch_ids"].append(patch_id)
            if "unreviewed" in attention_flags:
                attention["unreviewed_patch_ids"].append(patch_id)
            if "missing_telemetry" in attention_flags:
                attention["missing_telemetry_patch_ids"].append(patch_id)
            if "missing_manual_check" in attention_flags:
                attention["missing_manual_check_patch_ids"].append(patch_id)
            if is_reproposal_candidate:
                attention["reproposal_needed_patch_ids"].append(patch_id)
            out_patches.append({
                "patch_id": patch_id,
                "target_file": str(p.get("target_file", "") or ""),
                "patch_type": patch_type,
                "generator": generator,
                "apply_allowed": apply_allowed,
                "approval_status": approval_status,
                "applied": applied,
                "verification_status": verification_status,
                "quality_score": quality_score,
                "has_safety_warnings": bool(safety_warnings),
                "has_quality_warnings": bool(quality_warnings),
                "has_telemetry": has_telemetry,
                "telemetry_count": len(patch_telemetry),
                "has_manual_check": has_manual_check,
                "manual_check_count": len(patch_manual_checks),
                "has_reproposal": has_reproposal,
                "reproposal_of_patch_id": reproposal_of_patch_id,
                "attention_flags": attention_flags,
            })
        return {
            "run_id": run_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "counts": counts,
            "risk_counts": risk_counts,
            "patch_type_counts": patch_type_counts,
            "generator_counts": generator_counts,
            "attention": attention,
            "patches": out_patches,
        }
