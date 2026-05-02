from __future__ import annotations

import json
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
