from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4
from pathlib import Path
from typing import Callable

from agent.atlas_file_safe_apply_executor import normalize_safe_apply_action_type
from agent.atlas_journal import AtlasJournal
from agent.atlas_patch_proposal_schema import AtlasPatchProposal, AtlasPatchProposalRequest, AtlasPatchProposalResult
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage


class AtlasPatchProposalService:
    ALLOWED_SOURCE_TYPES = {"debug_review", "plan_item"}
    LLM_ALLOWED_FIELDS = {"title", "summary", "root_cause", "proposed_fix", "target_files", "suggested_changes", "unified_diff_preview", "proposed_content", "risk_level", "verification_plan", "rollback_plan", "assumptions"}
    LLM_UNTRUSTED_FIELDS = {"status", "pool_id", "item_id", "run_id", "proposal_id", "metadata", "warnings", "errors", "proposal_json_path", "proposal_md_path", "created_at"}
    ALLOWED_RISK_LEVELS = {"low", "medium", "high", "critical"}
    MAX_DIFF_PREVIEW_CHARS = 12000
    MAX_PROPOSED_CONTENT_CHARS = 200000

    def __init__(self, *, journal: AtlasJournal, storage: AtlasPlanPoolStorage, llm_json_fn: Callable[[str, str], dict | None] | None = None):
        self.journal = journal
        self.storage = storage
        self.llm_json_fn = llm_json_fn

    def propose_for_item(self, request: AtlasPatchProposalRequest) -> AtlasPatchProposalResult:
        pool = self.storage.load_pool(request.pool_id)
        item = pool.get_item(request.item_id)
        self._append_event(pool.pool_id, request.run_id, "patch_proposal_manual_started", item, "started")
        if item is None:
            warnings = ["item_not_found"]
            self._append_event(pool.pool_id, request.run_id, "patch_proposal_manual_blocked", None, "blocked", warnings=warnings)
            return AtlasPatchProposalResult(pool_id=pool.pool_id, item_id=request.item_id, run_id=request.run_id, status="blocked", warnings=warnings, plan_pool=pool.model_dump())
        ok, warnings = self.validate_item_for_patch_proposal(pool, item, request)
        if not ok:
            self._append_event(pool.pool_id, request.run_id, "patch_proposal_manual_blocked", item, "blocked", warnings=warnings)
            return AtlasPatchProposalResult(pool_id=pool.pool_id, item_id=item.item_id, run_id=request.run_id, status="blocked", warnings=warnings, plan_pool=pool.model_dump())
        try:
            payload = self.build_proposal_input(pool, item, request)
            proposal = self.generate_proposal_with_llm(payload) if self.llm_json_fn else self.generate_fallback_proposal(payload)
            proposal.pool_id = pool.pool_id
            proposal.item_id = item.item_id
            proposal.run_id = request.run_id
            json_path, md_path = self.save_patch_proposal_record(pool.pool_id, item.item_id, proposal)
            # Honest signal: a proposal can be "proposed" yet carry NO applicable content (weak/absent
            # LLM, or fallback). Surface that explicitly so the UI does not report fake success and the
            # autopilot does not silently skip with "missing_patch_or_content".
            has_content = bool(proposal.unified_diff_preview or (proposal.metadata or {}).get("proposed_content"))
            result = AtlasPatchProposalResult(pool_id=pool.pool_id, item_id=item.item_id, run_id=request.run_id, status="proposed", proposal=proposal, proposal_json_path=json_path, proposal_md_path=md_path, metadata={"patch_content_available": has_content})
            self.mark_item_from_patch_proposal(pool, item, result)
            self.storage.save_pool(pool)
            self.journal.save_plan_pool(pool)
            self._append_event(pool.pool_id, request.run_id, "patch_proposal_manual_proposed", item, "proposed")
            result.plan_pool = pool.model_dump()
            return result
        except Exception as exc:
            errors = [str(exc) or exc.__class__.__name__]
            self._append_event(pool.pool_id, request.run_id, "patch_proposal_manual_failed", item, "failed", errors=errors)
            return AtlasPatchProposalResult(pool_id=pool.pool_id, item_id=item.item_id, run_id=request.run_id, status="failed", errors=errors, plan_pool=pool.model_dump())

    def validate_item_for_patch_proposal(self, pool: AtlasPlanPool, item: AtlasPlanItem, request: AtlasPatchProposalRequest) -> tuple[bool, list[str]]:
        warnings = []
        source_type = self._effective_source_type(item, request)
        debug_review = (item.metadata or {}).get("debug_review") or {}
        if request.source_type not in self.ALLOWED_SOURCE_TYPES:
            warnings.append("source_type_not_allowed")
        if source_type == "debug_review":
            if str(debug_review.get("status") or "").lower() != "analyzed":
                warnings.append("debug_review_not_analyzed")
            if not str(debug_review.get("proposed_fix") or "").strip() and not str(debug_review.get("root_cause_category") or "").strip():
                warnings.append("proposed_fix_missing")
        elif source_type == "plan_item":
            if not (str(item.title or "").strip() or str(item.goal or "").strip() or str(item.description or "").strip()):
                warnings.append("plan_item_goal_missing")
            if str((item.metadata or {}).get("action_type") or "").lower() in {"delete", "run_command"}:
                warnings.append("forbidden_action_type")
            if any(Path(str(p)).is_absolute() or ".." in Path(str(p)).parts for p in list(item.target_files or [])):
                warnings.append("unsafe_target_files")
        patch_status = str(((item.metadata or {}).get("patch_proposal") or {}).get("status") or "").lower()
        if patch_status == "approved":
            warnings.append("patch_proposal_already_approved")
        elif patch_status == "rejected":
            warnings.append("patch_proposal_already_rejected")
        elif patch_status in {"accepted", "applied"}:
            warnings.append("patch_proposal_blocked")
        return len(warnings) == 0, warnings

    def _effective_source_type(self, item: AtlasPlanItem, request: AtlasPatchProposalRequest) -> str:
        requested = str(request.source_type or "debug_review").strip().lower() or "debug_review"
        if requested != "debug_review":
            return requested
        debug_review = (item.metadata or {}).get("debug_review") or {}
        if not request.run_id and str(debug_review.get("status") or "").lower() != "analyzed":
            return "plan_item"
        return "debug_review"

    def build_proposal_input(self, pool: AtlasPlanPool, item: AtlasPlanItem, request: AtlasPatchProposalRequest) -> dict:
        source_type = self._effective_source_type(item, request)
        debug_review = (item.metadata or {}).get("debug_review") or {}
        item_metadata = item.metadata or {}
        return {
            "pool_id": pool.pool_id,
            "item_id": item.item_id,
            "run_id": request.run_id,
            "workspace_id": request.workspace_id,
            "source_type": source_type,
            "requested_source_type": request.source_type,
            "proposal_mode": request.proposal_mode,
            "item": {
                "title": item.title,
                "description": item.description,
                "goal": item.goal,
                "done_definition": list(item.done_definition or []),
                "target_files": list(item.target_files or []),
                "risk_level": item.risk_level,
                "item_type": item.item_type,
                "action_type": str(item_metadata.get("action_type") or ""),
                "existing_patch": str(item_metadata.get("patch") or ""),
                "existing_content": str(item_metadata.get("content") or item_metadata.get("proposed_content") or ""),
            },
            "debug_review": {
                "root_cause_category": str(debug_review.get("root_cause_category") or ("plan_item" if source_type == "plan_item" else "")),
                "proposed_fix": str(debug_review.get("proposed_fix") or (item.description or item.goal or item.title if source_type == "plan_item" else "")),
                "retry_recommended": bool(debug_review.get("retry_recommended", False)),
                "debug_notes_path": str(debug_review.get("debug_notes_path") or ""),
            },
            "latest_verification": dict((item.metadata or {}).get("verification") or {}),
            "constraints": [
                "proposal_only",
                "no_auto_apply",
                "no_safe_apply",
                "no_verification_rerun",
                "no_command_execution",
            ],
        }

    def generate_proposal_with_llm(self, input_payload: dict) -> AtlasPatchProposal:
        assert self.llm_json_fn is not None
        system_prompt = (
            "You generate advisory patch proposals only. Return a single JSON object only, no prose, "
            "no markdown fences. Do not claim changes were applied."
        )
        user_prompt = json.dumps({
            "task": (
                "Generate a safe patch proposal as JSON. For source_type=plan_item that lists target_files, "
                "you MUST return a non-empty \"proposed_content\" string containing the COMPLETE file text for the "
                "first target file (this is a new/overwritten file write, not a diff). "
                "Example: {\"target_files\":[\"index.html\"],\"proposed_content\":\"<!doctype html>\\n<html>...\",\"risk_level\":\"low\"}"
            ),
            "input": input_payload,
        }, ensure_ascii=False)
        try:
            output = self.llm_json_fn(system_prompt, user_prompt) or {}
            if not isinstance(output, dict):
                raise ValueError("llm_output_not_dict")
            debug = input_payload.get("debug_review") or {}
            item = input_payload.get("item") or {}
            warnings: list[str] = []

            ignored_untrusted = bool(self.LLM_UNTRUSTED_FIELDS.intersection(output.keys()))
            if ignored_untrusted:
                warnings.append("llm_untrusted_fields_ignored")

            llm_allowed = {k: output[k] for k in self.LLM_ALLOWED_FIELDS if k in output}

            raw_risk = str(llm_allowed.get("risk_level") or item.get("risk_level") or "medium").strip().lower()
            risk_level = raw_risk if raw_risk in self.ALLOWED_RISK_LEVELS else "medium"
            if raw_risk != risk_level:
                warnings.append("llm_risk_level_normalized")

            target_files = self._normalize_target_files(llm_allowed.get("target_files"), list(item.get("target_files") or []), warnings)

            diff_preview = str(llm_allowed.get("unified_diff_preview") or "")
            if len(diff_preview) > self.MAX_DIFF_PREVIEW_CHARS:
                diff_preview = diff_preview[: self.MAX_DIFF_PREVIEW_CHARS]
                warnings.append("diff_preview_truncated")

            proposed_content = str(llm_allowed.get("proposed_content") or "")
            if len(proposed_content) > self.MAX_PROPOSED_CONTENT_CHARS:
                proposed_content = proposed_content[: self.MAX_PROPOSED_CONTENT_CHARS]
                warnings.append("proposed_content_truncated")

            # Deterministic safety net: a weak model may return JSON with no usable content. For a
            # single-file plan_item create/update, synthesize minimal valid file content so a trivial
            # "create X" goal still yields an applicable patch instead of a silent skip.
            if not proposed_content and not diff_preview:
                scaffold = self._scaffold_content_for_plan_item(input_payload)
                if scaffold:
                    proposed_content = scaffold[: self.MAX_PROPOSED_CONTENT_CHARS]
                    warnings.append("scaffolded_minimal_content")

            metadata = {
                "source_type": str(input_payload.get("source_type") or "debug_review"),
                "requested_source_type": str(input_payload.get("requested_source_type") or ""),
                "patch_content_available": bool(proposed_content or diff_preview),
            }
            if proposed_content:
                metadata["proposed_content"] = proposed_content

            normalized = AtlasPatchProposal.model_validate({
                "proposal_id": f"proposal_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}",
                "pool_id": str(input_payload.get("pool_id") or ""),
                "item_id": str(input_payload.get("item_id") or ""),
                "run_id": str(input_payload.get("run_id") or ""),
                "status": "proposed",
                "title": str(llm_allowed.get("title") or f"Patch proposal for {item.get('title') or input_payload.get('item_id') or ''}"),
                "summary": str(llm_allowed.get("summary") or debug.get("proposed_fix") or item.get("description") or ""),
                "proposed_fix": str(llm_allowed.get("proposed_fix") or debug.get("proposed_fix") or item.get("description") or item.get("goal") or ""),
                "root_cause": str(llm_allowed.get("root_cause") or debug.get("root_cause_category") or ""),
                "target_files": target_files,
                "suggested_changes": list(llm_allowed.get("suggested_changes") or []),
                "unified_diff_preview": diff_preview,
                "risk_level": risk_level,
                "verification_plan": list(llm_allowed.get("verification_plan") or []),
                "rollback_plan": list(llm_allowed.get("rollback_plan") or []),
                "assumptions": list(llm_allowed.get("assumptions") or []),
                "warnings": warnings,
                "metadata": metadata,
            })
            return normalized
        except Exception:
            fallback = self.generate_fallback_proposal(input_payload)
            fallback.warnings.append("llm_invalid_json_fallback_proposal")
            return fallback

    def _normalize_target_files(self, raw_target_files: object, fallback_target_files: list[str], warnings: list[str]) -> list[str]:
        if not isinstance(raw_target_files, list):
            return list(fallback_target_files)
        safe_files: list[str] = []
        ignored = False
        for path in raw_target_files:
            if not isinstance(path, str):
                ignored = True
                continue
            candidate = path.strip()
            if not candidate:
                ignored = True
                continue
            path_obj = Path(candidate)
            if path_obj.is_absolute() or ".." in path_obj.parts:
                ignored = True
                continue
            safe_files.append(candidate)
        if ignored:
            warnings.append("unsafe_target_files_ignored")
        return safe_files or list(fallback_target_files)

    def _scaffold_content_for_plan_item(self, input_payload: dict) -> str | None:
        # Synthesize minimal valid file content for a single-file plan_item create/update so a
        # trivial dev goal still produces an applicable patch when the LLM yields no content. Gated
        # to keep it safe and honest (callers add a "scaffolded_minimal_content" warning).
        if str(input_payload.get("source_type") or "") != "plan_item":
            return None
        item = input_payload.get("item") or {}
        target_files = [str(p).strip() for p in (item.get("target_files") or []) if str(p).strip()]
        if len(target_files) != 1:
            return None
        if str(item.get("action_type") or "").lower() in {"delete", "run_command"}:
            return None
        if str(item.get("risk_level") or "medium").lower() not in {"low", "medium"}:
            return None
        goal = str(item.get("goal") or item.get("title") or item.get("description") or "Generated file").strip()
        title = str(item.get("title") or goal).strip()
        ext = Path(target_files[0]).suffix.lower()
        if ext == ".html":
            return (
                "<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
                f"<title>{title}</title>\n</head>\n<body>\n<h1>{goal}</h1>\n</body>\n</html>\n"
            )
        if ext == ".md":
            return f"# {title}\n\n{goal}\n"
        if ext == ".py":
            return f"\"\"\"{goal}\"\"\"\n\n\ndef main() -> None:\n    print({goal!r})\n\n\nif __name__ == \"__main__\":\n    main()\n"
        if ext == ".js":
            return f"// {goal}\nfunction main() {{\n  console.log({goal!r});\n}}\n\nmain();\n"
        if ext == ".json":
            return json.dumps({"goal": goal, "title": title}, ensure_ascii=False, indent=2) + "\n"
        if ext in {".txt", ""}:
            return f"{title}\n\n{goal}\n"
        return f"{goal}\n"

    def generate_fallback_proposal(self, input_payload: dict) -> AtlasPatchProposal:
        source_type = str(input_payload.get("source_type") or "debug_review")
        debug = input_payload.get("debug_review") or {}
        item = input_payload.get("item") or {}
        warnings = ["llm_unavailable_fallback_proposal"]
        if source_type == "plan_item":
            warnings.append("plan_item_patch_content_missing")
        scaffold = self._scaffold_content_for_plan_item(input_payload)
        metadata = {"source_type": source_type, "patch_content_available": bool(scaffold)}
        if scaffold:
            metadata["proposed_content"] = scaffold[: self.MAX_PROPOSED_CONTENT_CHARS]
            warnings.append("scaffolded_minimal_content")
        return AtlasPatchProposal(
            proposal_id=f"proposal_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}",
            pool_id=str(input_payload.get("pool_id") or ""),
            item_id=str(input_payload.get("item_id") or ""),
            run_id=str(input_payload.get("run_id") or ""),
            title=f"Patch proposal for {item.get('title') or input_payload.get('item_id')}",
            summary=str(debug.get("proposed_fix") or item.get("description") or item.get("goal") or "Use available guidance to update target files."),
            root_cause=str(debug.get("root_cause_category") or ("plan_item" if source_type == "plan_item" else "unknown")),
            proposed_fix=str(debug.get("proposed_fix") or item.get("description") or item.get("goal") or "Investigate and apply safe code-level fixes manually."),
            target_files=list(item.get("target_files") or []),
            suggested_changes=[{"type": "advisory", "detail": str(debug.get("proposed_fix") or item.get("description") or "Apply minimal focused patch around root cause.")}],
            unified_diff_preview="",
            risk_level=str(item.get("risk_level") or "medium"),
            verification_plan=["Run targeted tests manually after human review."],
            rollback_plan=["Revert proposed edits if regressions are detected."],
            assumptions=["Patch proposal has not been applied."],
            warnings=warnings,
            metadata=metadata,
        )

    def save_patch_proposal_record(self, pool_id: str, item_id: str, proposal: AtlasPatchProposal) -> tuple[str, str]:
        ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        out_dir = Path(self.journal.paths(pool_id=pool_id).plan_pool_json).parent / "patch_proposals"
        out_dir.mkdir(parents=True, exist_ok=True)
        json_path = out_dir / f"{item_id}_{ts}.json"
        md_path = out_dir / f"{item_id}_{ts}.md"
        json_path.write_text(json.dumps(proposal.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
        md = f"# Atlas Patch Proposal\n\n- Pool ID: {pool_id}\n- Item ID: {item_id}\n- Source type: {proposal.metadata.get('source_type', 'debug_review')}\n- Status: {proposal.status}\n- Root cause: {proposal.root_cause}\n- Proposed fix: {proposal.proposed_fix}\n- Target files: {', '.join(proposal.target_files)}\n- Suggested changes: {json.dumps(proposal.suggested_changes, ensure_ascii=False)}\n- Proposed content available: {bool((proposal.metadata or {}).get('proposed_content'))}\n- Unified diff preview:\n\n```diff\n{proposal.unified_diff_preview}\n```\n\n- Risk level: {proposal.risk_level}\n- Verification plan: {json.dumps(proposal.verification_plan, ensure_ascii=False)}\n- Rollback plan: {json.dumps(proposal.rollback_plan, ensure_ascii=False)}\n\n- No patch was applied.\n- No safe_apply was run.\n- No verification rerun was performed.\n"
        md_path.write_text(md, encoding="utf-8")
        return str(json_path), str(md_path)

    def mark_item_from_patch_proposal(self, pool: AtlasPlanPool, item: AtlasPlanItem, result: AtlasPatchProposalResult) -> None:
        proposal = result.proposal or AtlasPatchProposal(proposal_id="", pool_id=pool.pool_id, item_id=item.item_id)
        item.metadata.setdefault("patch_proposal", {})
        previous = dict(item.metadata.get("patch_proposal") or {})
        revision_count = int(previous.get("revision_count", 0) or 0) + 1
        item.metadata["patch_proposal_previous"] = {
            "proposal_id": previous.get("proposal_id", ""),
            "status": previous.get("status", ""),
            "summary": previous.get("summary", ""),
            "risk_level": previous.get("risk_level", ""),
            "proposed_at": previous.get("proposed_at", ""),
        } if previous else item.metadata.get("patch_proposal_previous")
        item.metadata["patch_proposal_revision_count"] = revision_count
        debug_review = (item.metadata or {}).get("debug_review") or {}
        proposal_metadata = dict(proposal.metadata or {})
        source_type = str(proposal_metadata.get("source_type") or "debug_review")
        source = str(debug_review.get("source") or ("plan_item" if source_type == "plan_item" else ""))
        source_proposal_id = str(debug_review.get("source_proposal_id") or item.metadata.get("source_proposal_id") or "")
        root_cause_category = str(debug_review.get("root_cause_category") or ("plan_item" if source_type == "plan_item" else ""))
        proposed_fix = str(debug_review.get("proposed_fix") or proposal.proposed_fix or "")
        proposed_content = str(proposal_metadata.get("proposed_content") or "")
        item.metadata["patch_proposal"].update({
            "status": result.status,
            "proposal_id": proposal.proposal_id,
            "proposal_json_path": result.proposal_json_path,
            "proposal_md_path": result.proposal_md_path,
            "summary": proposal.summary,
            "risk_level": proposal.risk_level,
            "target_files": list(proposal.target_files),
            "suggested_changes": list(proposal.suggested_changes),
            "unified_diff_preview": proposal.unified_diff_preview,
            "verification_plan": list(proposal.verification_plan),
            "rollback_plan": list(proposal.rollback_plan),
            "metadata": proposal_metadata,
            "proposed_at": datetime.now(timezone.utc).isoformat(),
            "revision_count": revision_count,
            "source": source or "patch_proposal_planitem_draft",
            "source_type": source_type,
            "source_proposal_id": source_proposal_id,
            "debug_review_status": str(debug_review.get("status") or ""),
            "root_cause_category": root_cause_category,
            "proposed_fix": proposed_fix,
            "manual_only": True,
            "auto_apply": False,
            "auto_safe_apply": False,
            "auto_verification": False,
        })
        if proposed_content:
            item.metadata["patch_proposal"]["proposed_content"] = proposed_content
            item.metadata["proposed_content"] = proposed_content
            item.metadata["content"] = proposed_content
        if proposal.unified_diff_preview:
            item.metadata["patch_proposal"]["patch"] = proposal.unified_diff_preview
            item.metadata["unified_diff_preview"] = proposal.unified_diff_preview
            item.metadata["patch"] = proposal.unified_diff_preview
        # When real patch content was produced, wire the item into the canonical safe-apply
        # vocabulary so the autopilot can actually apply it: action_type must be {create, update}
        # and item_type must be implementation/documentation (the executor + adapter reject others).
        # Empty/unknown action_type defaults to create (greenfield write); an existing action_type
        # is preserved (e.g. an LLM-specified "update" for edits) via normalization.
        if proposed_content or proposal.unified_diff_preview:
            item.metadata["action_type"] = normalize_safe_apply_action_type(item.metadata.get("action_type"))
            if str(getattr(item, "item_type", "") or "") not in {"implementation", "documentation"}:
                item.item_type = "implementation"

    def _append_event(self, pool_id: str, run_id: str, event_type: str, item: AtlasPlanItem | None, status: str, warnings: list[str] | None = None, errors: list[str] | None = None) -> None:
        if not run_id:
            return
        self.journal.append_event(pool_id, run_id, {"event_type": event_type, "pool_id": pool_id, "run_id": run_id, "item_id": item.item_id if item else "", "status": status, "warnings": list(warnings or []), "errors": list(errors or []), "created_at": datetime.now(timezone.utc).isoformat()})
