from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agent.atlas_journal import AtlasJournal
from agent.atlas_patch_generation_state import is_patch_generation_success
from agent.atlas_patch_proposal_planitem_schema import (
    AtlasPatchProposalPlanItemDraft,
    AtlasPatchProposalPlanItemDraftRequest,
    AtlasPatchProposalPlanItemDraftResult,
)
from agent.atlas_plan_item_file_changes import DEFAULT_CHANGE_SET, normalize_plan_item_file_changes
from agent.atlas_plan_pool_schema import AtlasPlanItem
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage


class AtlasPatchProposalPlanItemDraftService:
    def __init__(self, *, journal: AtlasJournal, storage: AtlasPlanPoolStorage):
        self.journal = journal
        self.storage = storage

    def create_draft(self, request: AtlasPatchProposalPlanItemDraftRequest) -> AtlasPatchProposalPlanItemDraftResult:
        pool = self.storage.load_pool(request.pool_id)
        source_item = pool.get_item(request.item_id)
        self._append_event(pool.pool_id, request.run_id, "patch_proposal_planitem_draft_manual_started", request.item_id, "started")
        if source_item is None:
            warnings = ["item_not_found"]
            self._append_event(pool.pool_id, request.run_id, "patch_proposal_planitem_draft_manual_blocked", request.item_id, "blocked", warnings=warnings)
            return AtlasPatchProposalPlanItemDraftResult(pool_id=pool.pool_id, item_id=request.item_id, proposal_id=request.proposal_id, status="blocked", warnings=warnings, plan_pool=pool.model_dump())
        ok, warnings = self.validate_source(pool, source_item, request)
        if not ok:
            self._append_event(pool.pool_id, request.run_id, "patch_proposal_planitem_draft_manual_blocked", source_item.item_id, "blocked", warnings=warnings)
            return AtlasPatchProposalPlanItemDraftResult(pool_id=pool.pool_id, item_id=source_item.item_id, proposal_id=request.proposal_id, status="blocked", warnings=warnings, plan_pool=pool.model_dump())
        try:
            draft_item = self.build_draft_item(pool, source_item, request)
            pool.items.append(draft_item)
            draft = AtlasPatchProposalPlanItemDraft(
                draft_item_id=draft_item.item_id,
                source_item_id=source_item.item_id,
                source_proposal_id=str((source_item.metadata.get("patch_proposal") or {}).get("proposal_id") or ""),
                pool_id=pool.pool_id,
                run_id=request.run_id,
                title=draft_item.title,
                description=draft_item.description,
                item_type=draft_item.item_type,
                status=draft_item.status,
                risk_level=draft_item.risk_level,
                target_files=list(draft_item.target_files or []),
                expected_changes=list(draft_item.metadata.get("expected_changes") or []),
                verification_plan=list(draft_item.done_definition or []),
                rollback_plan=list(draft_item.rollback_plan or []),
                requires_user_confirmation=bool(draft_item.requires_user_confirmation),
                metadata=dict(draft_item.metadata or {}),
            )
            json_path, md_path = self.save_draft_record(pool.pool_id, source_item.item_id, draft)
            result = AtlasPatchProposalPlanItemDraftResult(pool_id=pool.pool_id, item_id=source_item.item_id, proposal_id=draft.source_proposal_id, status="created", draft_item=draft, metadata={"draft_json_path": json_path, "draft_md_path": md_path})
            self.mark_source_item_from_draft(pool, source_item, draft_item, result)
            self.storage.save_pool(pool)
            self.journal.save_plan_pool(pool)
            self._append_event(pool.pool_id, request.run_id, "patch_proposal_planitem_draft_manual_created", source_item.item_id, "drafted")
            result.plan_pool = pool.model_dump()
            return result
        except Exception as exc:
            errors = [str(exc) or exc.__class__.__name__]
            self._append_event(pool.pool_id, request.run_id, "patch_proposal_planitem_draft_manual_failed", request.item_id, "failed", errors=errors)
            return AtlasPatchProposalPlanItemDraftResult(pool_id=pool.pool_id, item_id=request.item_id, proposal_id=request.proposal_id, status="failed", errors=errors, plan_pool=pool.model_dump())

    def validate_source(self, pool, item, request) -> tuple[bool, list[str]]:
        warnings: list[str] = []
        patch = dict((item.metadata or {}).get("patch_proposal") or {})
        approval = dict((item.metadata or {}).get("patch_proposal_approval") or {})
        if str(patch.get("status") or "").lower() != "approved": warnings.append("patch_proposal_not_approved")
        if str(approval.get("decision") or "").lower() != "approved": warnings.append("patch_proposal_approval_not_approved")
        if not is_patch_generation_success((item.metadata or {}).get("patch_generation")): warnings.append("patch_generation_not_successful")
        req_pid = str(request.proposal_id or "").strip()
        if req_pid and req_pid != str(patch.get("proposal_id") or "").strip(): warnings.append("proposal_id_mismatch")
        target_files = list(patch.get("target_files") or [])
        if not target_files: warnings.append("patch_proposal_target_files_missing")
        if any(Path(str(p)).is_absolute() or ".." in Path(str(p)).parts for p in target_files): warnings.append("unsafe_target_files")
        if str(patch.get("risk_level") or "").lower() != "low": warnings.append("patch_proposal_risk_not_low")
        if (item.metadata or {}).get("patch_proposal_planitem_draft", {}).get("draft_item_id"):
            warnings.append("draft_already_exists")
        return len(warnings) == 0, warnings

    def build_draft_item(self, pool, item, request) -> AtlasPlanItem:
        patch = dict((item.metadata or {}).get("patch_proposal") or {})
        shortid = uuid4().hex[:8]
        draft_item_id = f"patch_apply_{item.item_id}_{shortid}"
        title = f"Apply approved patch proposal: {item.title}"
        summary = str(patch.get("summary") or "")
        proposed_fix = str(patch.get("proposed_fix") or "")
        description = summary or proposed_fix
        metadata = {
            "source": "patch_proposal",
            "source_item_id": item.item_id,
            "source_proposal_id": str(patch.get("proposal_id") or ""),
            "proposal_md_path": str(patch.get("proposal_md_path") or ""),
            "proposal_json_path": str(patch.get("proposal_json_path") or ""),
            "proposal_summary": summary,
            "proposal_risk_level": str(patch.get("risk_level") or ""),
            "manual_safe_apply_required": True,
            "auto_execute": False,
            "auto_verification": False,
            "requires_planitem_approval": True,
            "action_type": "update",
            "expected_changes": list(patch.get("suggested_changes") or []),
        }
        proposed_content = ""
        patch_metadata = patch.get("metadata") if isinstance(patch.get("metadata"), dict) else {}
        if patch.get("proposed_content"):
            proposed_content = str(patch.get("proposed_content") or "")
        elif patch_metadata.get("proposed_content"):
            proposed_content = str(patch_metadata.get("proposed_content") or "")

        diff_preview = str(patch.get("unified_diff_preview") or "") if patch.get("unified_diff_preview") else ""
        if diff_preview:
            metadata["unified_diff_preview"] = diff_preview
            metadata["patch"] = diff_preview
        if proposed_content:
            metadata["proposed_content"] = proposed_content

        patch_proposal_metadata = {
            "proposal_id": str(patch.get("proposal_id") or ""),
            "target_files": list(patch.get("target_files") or []),
            "risk_level": str(patch.get("risk_level") or ""),
        }
        patch_metadata = patch.get("metadata") if isinstance(patch.get("metadata"), dict) else {}
        file_changes = patch.get("file_changes") if isinstance(patch.get("file_changes"), list) else patch_metadata.get("file_changes")
        if isinstance(file_changes, list) and file_changes:
            metadata["file_changes"] = [dict(fc) for fc in file_changes if isinstance(fc, dict)]
            metadata["change_set"] = {**DEFAULT_CHANGE_SET, **(patch_metadata.get("change_set") if isinstance(patch_metadata.get("change_set"), dict) else {}), "change_set_id": f"cs_{draft_item_id}"}
            patch_proposal_metadata["file_changes"] = metadata["file_changes"]
            patch_proposal_metadata["change_set"] = metadata["change_set"]
        if proposed_content:
            patch_proposal_metadata["proposed_content"] = proposed_content
        if diff_preview:
            patch_proposal_metadata["unified_diff_preview"] = diff_preview
        metadata["patch_proposal"] = patch_proposal_metadata
        draft = AtlasPlanItem(
            item_id=draft_item_id,
            pool_id=pool.pool_id,
            title=title,
            goal=item.goal,
            description=description,
            item_type="implementation",
            status="approval_required",
            priority="medium",
            risk_level="low",
            target_files=list(patch.get("target_files") or []),
            expected_changes=[json.dumps(entry, ensure_ascii=False) for entry in list(patch.get("suggested_changes") or [])],
            done_definition=list(patch.get("verification_plan") or []),
            rollback_plan=list(patch.get("rollback_plan") or []),
            requires_user_confirmation=True,
            auto_execution_allowed=False,
            linked_run_id=request.run_id,
            metadata=metadata,
        )
        normalize_plan_item_file_changes(draft)
        return draft

    def save_draft_record(self, pool_id, item_id, draft) -> tuple[str, str]:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_dir = Path(self.journal.paths(pool_id=pool_id).plan_pool_json).parent / "patch_proposal_planitem_drafts"
        out_dir.mkdir(parents=True, exist_ok=True)
        json_path = out_dir / f"{item_id}_{ts}.json"
        md_path = out_dir / f"{item_id}_{ts}.md"
        json_path.write_text(json.dumps(draft.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
        md_path.write_text(
            f"# Atlas Patch Proposal PlanItem Draft\n\n- Pool ID: {pool_id}\n- Source Item ID: {draft.source_item_id}\n- Source Proposal ID: {draft.source_proposal_id}\n- Draft Item ID: {draft.draft_item_id}\n- Target files: {json.dumps(draft.target_files, ensure_ascii=False)}\n- Expected changes: {json.dumps(draft.expected_changes, ensure_ascii=False)}\n- Verification plan: {json.dumps(draft.verification_plan, ensure_ascii=False)}\n- Rollback plan: {json.dumps(draft.rollback_plan, ensure_ascii=False)}\n\n- No patch was applied.\n- No safe_apply was run.\n- No verification was run.\n- This draft still requires PlanItem approval before manual safe_apply.\n",
            encoding="utf-8",
        )
        return str(json_path), str(md_path)

    def mark_source_item_from_draft(self, pool, source_item, draft_item, result) -> None:
        source_item.metadata.setdefault("patch_proposal_planitem_draft", {})
        source_item.metadata["patch_proposal_planitem_draft"].update({
            "status": result.status,
            "draft_item_id": draft_item.item_id,
            "source_proposal_id": str((source_item.metadata.get("patch_proposal") or {}).get("proposal_id") or ""),
            "source": "patch_proposal_planitem_draft",
            "manual_only": True,
            "auto_planitem_approval": False,
            "auto_safe_apply": False,
            "auto_verification": False,
            "draft_md_path": str((result.metadata or {}).get("draft_md_path") or ""),
            "draft_json_path": str((result.metadata or {}).get("draft_json_path") or ""),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

    def _append_event(self, pool_id: str, run_id: str, event_type: str, item_id: str, status: str, warnings: list[str] | None = None, errors: list[str] | None = None) -> None:
        if not run_id:
            return
        self.journal.append_event(pool_id, run_id, {"event_type": event_type, "pool_id": pool_id, "run_id": run_id, "item_id": item_id, "status": status, "warnings": list(warnings or []), "errors": list(errors or []), "created_at": datetime.now(timezone.utc).isoformat()})
