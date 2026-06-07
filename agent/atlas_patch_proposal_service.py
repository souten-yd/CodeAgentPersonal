from __future__ import annotations

import ast
import hashlib
import json
import re
from datetime import datetime, timezone
from uuid import uuid4
from pathlib import Path, PurePosixPath
from typing import Callable

from agent.atlas_file_safe_apply_executor import normalize_safe_apply_action_type
from agent.atlas_journal import AtlasJournal
from agent.atlas_llm_json_adapter import call_llm_json
from agent.atlas_llm_schemas import patch_proposal_json_schema
from agent.atlas_plan_item_file_changes import DEFAULT_CHANGE_SET, has_file_change_content, normalize_plan_item_file_changes
from agent.atlas_patch_proposal_schema import AtlasPatchProposal, AtlasPatchProposalRequest, AtlasPatchProposalResult
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_plan_trace import PlanTrace
from agent.atlas_workspace_root import resolve_atlas_workspace_root


class AtlasPatchProposalService:
    ALLOWED_SOURCE_TYPES = {"debug_review", "plan_item"}
    LLM_ALLOWED_FIELDS = {
        "title", "summary", "root_cause", "proposed_fix", "target_files", "file_changes", "change_set",
        "suggested_changes", "unified_diff_preview", "proposed_content", "edits", "risk_level",
        "verification_plan", "rollback_plan", "assumptions", "satisfied_requirement_ids",
        "preserved_requirement_ids", "implemented_symbols", "behavioral_cases", "verification_cases",
        "known_limitations", "remaining_todos",
    }
    MAX_EDITS = 20
    LLM_UNTRUSTED_FIELDS = {"status", "pool_id", "item_id", "run_id", "proposal_id", "metadata", "warnings", "errors", "proposal_json_path", "proposal_md_path", "created_at"}
    ALLOWED_RISK_LEVELS = {"low", "medium", "high", "critical"}
    MAX_DIFF_PREVIEW_CHARS = 12000
    MAX_PROPOSED_CONTENT_CHARS = 200000
    # Read-before-edit: how much of an existing target file to feed the model as ground truth so it
    # produces a patch that CONNECTS to the current code instead of overwriting it blindly.
    MAX_EXISTING_FILE_CHARS = 60000
    # A plan_item that must write a file gets more than one shot at the LLM: weak models often emit
    # an empty/invalid first response but succeed when told the prior attempt was unusable.
    MAX_LLM_GENERATION_ATTEMPTS = 2
    _SIGNAL_REPAIR_HINTS = {
        "color_mutation_signal": (
            "色の変化が静的解析で検出できなかった。描画コードで色を動的に変える表現を使うこと"
            "（例: ctx.fillStyle に hsl(...) / rgb(...) を使い、requestAnimationFrame ループ内で"
            "色相や成分を毎フレーム更新する）。16進数固定色のみは不可。"
        ),
        "animation_signal": (
            "アニメーション信号が検出できなかった。requestAnimationFrame による描画ループ、"
            "または CSS @keyframes を実装すること。"
        ),
        "motion_signal": (
            "動きの信号が検出できなかった。canvas の getContext 描画更新、CSS transform/translate を"
            "実装すること。"
        ),
        "wave_phase_signal": (
            "波形/位相信号が検出できなかった。Math.sin/Math.cos と phase/amplitude/frequency を用いること。"
        ),
    }

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
            self._record_trace(pool.pool_id, request.run_id, "blocked", "item_not_found", {"llm_called": False})
            return AtlasPatchProposalResult(pool_id=pool.pool_id, item_id=request.item_id, run_id=request.run_id, status="blocked", warnings=warnings, plan_pool=pool.model_dump())
        # Critique gate (PR-8b): a plan flagged plan_revision_required must not generate patches
        # until the plan is revised / approved. full_auto-continuation pools never set this flag.
        if bool((pool.metadata or {}).get("plan_revision_required")):
            warnings = ["plan_revision_required_blocks_patch"]
            planner_fallback = (pool.metadata or {}).get("planner_fallback")
            if isinstance(planner_fallback, dict) and planner_fallback.get("reason"):
                warnings.append(f"planner_fallback:{planner_fallback.get('reason')}")
            self._append_event(pool.pool_id, request.run_id, "patch_proposal_manual_blocked", item, "blocked", warnings=warnings)
            self._record_trace(pool.pool_id, request.run_id, "blocked", "plan_revision_required_blocks_patch", {"llm_called": False})
            return AtlasPatchProposalResult(pool_id=pool.pool_id, item_id=item.item_id, run_id=request.run_id, status="blocked", warnings=warnings, plan_pool=pool.model_dump())
        ok, warnings = self.validate_item_for_patch_proposal(pool, item, request)
        if not ok:
            self._append_event(pool.pool_id, request.run_id, "patch_proposal_manual_blocked", item, "blocked", warnings=warnings)
            self._record_trace(pool.pool_id, request.run_id, "blocked", ";".join(warnings), {"llm_called": False})
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
            _pmeta = proposal.metadata or {}
            _file_changes = _pmeta.get("file_changes") if isinstance(_pmeta.get("file_changes"), list) else []
            has_file_changes_content = bool(_file_changes) and all(has_file_change_content(fc) for fc in _file_changes)
            has_content = bool(proposal.unified_diff_preview or _pmeta.get("proposed_content") or _pmeta.get("edits") or has_file_changes_content)
            self._record_trace(
                pool.pool_id,
                request.run_id,
                "generated",
                "patch_proposal_generated",
                {"llm_called": bool(self.llm_json_fn), "has_content": has_content},
            )
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
            self._record_trace(pool.pool_id, request.run_id, "failed", "patch_proposal_exception", {"llm_called": bool(self.llm_json_fn), "errors": errors})
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
        force = bool(getattr(request, "force_regenerate", False))
        if not force:
            if patch_status == "approved":
                warnings.append("patch_proposal_already_approved")
            elif patch_status == "rejected":
                warnings.append("patch_proposal_already_rejected")
        if patch_status in {"accepted", "applied"}:
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

    def _read_existing_target_content(self, pool: AtlasPlanPool, item: AtlasPlanItem, request: AtlasPatchProposalRequest) -> dict:
        """Read-before-edit: return the current on-disk content of the item's (single) target file.

        Returns {"exists": bool, "content": str, "truncated": bool, "rel_path": str}. A patch for an
        EXISTING file must connect to its current code, so we ground the model with the real bytes
        rather than guessing. Reuses the executor's workspace + safe-path logic; never reads outside
        the workspace and never raises.
        """
        out = {"exists": False, "content": "", "truncated": False, "rel_path": ""}
        try:
            target_files = [str(p).strip() for p in (item.target_files or []) if str(p).strip()]
            if len(target_files) != 1:
                return out
            rel = target_files[0]
            out["rel_path"] = rel
            p = Path(rel)
            if p.is_absolute() or ".." in p.parts:
                return out
            workspace_root = resolve_atlas_workspace_root(
                ca_data_root=self.storage.root_dir,
                workspace_id=request.workspace_id or "default",
                project_path=str(getattr(pool, "project_path", "") or ""),
            )
            target = (workspace_root / p).resolve()
            try:
                target.relative_to(workspace_root)
            except ValueError:
                return out
            if not target.is_file():
                return out
            text = target.read_text(encoding="utf-8", errors="replace")
            out["exists"] = True
            if len(text) > self.MAX_EXISTING_FILE_CHARS:
                out["content"] = text[: self.MAX_EXISTING_FILE_CHARS]
                out["truncated"] = True
            else:
                out["content"] = text
        except Exception:
            return {"exists": False, "content": "", "truncated": False, "rel_path": out.get("rel_path", "")}
        return out

    def _read_current_target_contents(self, pool: AtlasPlanPool, item: AtlasPlanItem, request: AtlasPatchProposalRequest) -> dict[str, dict]:
        out: dict[str, dict] = {}
        try:
            target_files = [str(p).strip() for p in (item.target_files or []) if str(p).strip()]
            workspace_root = resolve_atlas_workspace_root(
                ca_data_root=self.storage.root_dir,
                workspace_id=request.workspace_id or "default",
                project_path=str(getattr(pool, "project_path", "") or ""),
            )
            for rel in target_files:
                entry = {"exists": False, "content": "", "truncated": False, "revision": "absent"}
                path_obj = Path(rel)
                posix_path = PurePosixPath(rel.replace("\\", "/"))
                if path_obj.is_absolute() or posix_path.is_absolute() or ".." in path_obj.parts or ".." in posix_path.parts:
                    entry["unsafe"] = True
                    out[rel] = entry
                    continue
                target = (workspace_root / path_obj).resolve()
                try:
                    target.relative_to(workspace_root)
                except ValueError:
                    entry["unsafe"] = True
                    out[rel] = entry
                    continue
                if target.is_file():
                    text = target.read_text(encoding="utf-8", errors="replace")
                    entry["exists"] = True
                    entry["revision"] = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
                    if len(text) > self.MAX_EXISTING_FILE_CHARS:
                        entry["content"] = text[: self.MAX_EXISTING_FILE_CHARS]
                        entry["truncated"] = True
                    else:
                        entry["content"] = text
                out[rel] = entry
        except Exception:
            return out
        return out

    def _build_code_context(self, pool: AtlasPlanPool, item: AtlasPlanItem, request: AtlasPatchProposalRequest) -> dict:
        """Pillar C: surrounding-code awareness for the patch — project symbols the change can call or
        extend, plus tests related to the target file. Best-effort; empty when no project dir."""
        out: dict = {"symbols": [], "related_tests": []}
        try:
            from agent.atlas_code_explorer import extract_symbols, find_related_tests

            project_path = str(getattr(pool, "project_path", "") or "")
            if not project_path:
                return out
            target_files = [str(p).strip() for p in (item.target_files or []) if str(p).strip()]
            # Symbols across the project so the model knows what already exists to reuse (cap small for
            # weak models); related tests for the file under change.
            syms = extract_symbols(project_path, max_symbols=40)
            out["symbols"] = [f"{s['file']}:{s['line']} {s.get('signature') or s.get('name','')}" for s in syms[:40]]
            out["related_tests"] = find_related_tests(project_path, target_files, max_tests=8)
        except Exception:  # noqa: BLE001
            return {"symbols": [], "related_tests": []}
        return out

    def build_proposal_input(self, pool: AtlasPlanPool, item: AtlasPlanItem, request: AtlasPatchProposalRequest) -> dict:
        source_type = self._effective_source_type(item, request)
        debug_review = (item.metadata or {}).get("debug_review") or {}
        item_metadata = item.metadata or {}
        # Ground the model in the target files' CURRENT content (read-before-edit). Prefer real disk
        # bytes; fall back to any content captured in metadata for legacy single-target consumers.
        current_targets = self._read_current_target_contents(pool, item, request)
        existing_target = self._read_existing_target_content(pool, item, request)
        existing_content = existing_target["content"] or str(item_metadata.get("content") or item_metadata.get("proposed_content") or "")
        # Pillar C: surrounding-code awareness — symbols the patch can call/extend, and related tests.
        code_context = self._build_code_context(pool, item, request)
        requirements = self._all_requirements(pool)
        requirement_ids = [str(v) for v in (getattr(item, "requirement_ids", []) or item_metadata.get("requirement_ids") or []) if str(v).strip()]
        requirements_for_item = [r for r in requirements if str(r.get("requirement_id") or "") in set(requirement_ids)]
        satisfied_requirement_ids = self._satisfied_requirement_ids(pool)
        remaining_requirements = [
            r for r in requirements
            if str(r.get("requirement_id") or "") not in satisfied_requirement_ids
        ]
        completed_summaries = self._completed_item_summaries(pool)
        return {
            "pool_id": pool.pool_id,
            "item_id": item.item_id,
            "run_id": request.run_id,
            "workspace_id": request.workspace_id,
            "root_goal": pool.root_goal,
            "original_user_request": getattr(pool, "original_user_request", "") or (pool.metadata or {}).get("original_user_request", "") or pool.root_goal,
            "selected_architecture": getattr(pool, "selected_architecture", "") or (pool.metadata or {}).get("selected_architecture", ""),
            "global_constraints": list(getattr(pool, "global_constraints", []) or (pool.metadata or {}).get("global_constraints") or (pool.metadata or {}).get("constraints") or []),
            "all_requirements": requirements,
            "requirements_for_this_item": requirements_for_item,
            "already_satisfied_requirements": [r for r in requirements if str(r.get("requirement_id") or "") in satisfied_requirement_ids],
            "remaining_requirements": remaining_requirements,
            "completed_item_summaries": completed_summaries,
            "current_target_contents": current_targets,
            "base_file_revisions": {path: str(entry.get("revision") or "absent") for path, entry in current_targets.items()},
            "preserve_behaviors": list(getattr(item, "preserve_behaviors", []) or getattr(pool, "preserve_behaviors", []) or (pool.metadata or {}).get("preserve_behaviors") or []),
            "source_type": source_type,
            "requested_source_type": request.source_type,
            "proposal_mode": request.proposal_mode,
            "item": {
                "title": item.title,
                "description": item.description,
                "goal": item.goal,
                "requirement_ids": requirement_ids,
                "acceptance_criteria": list(getattr(item, "acceptance_criteria", []) or item_metadata.get("acceptance_criteria") or []),
                "expected_changes": list(getattr(item, "expected_changes", []) or []),
                "verification_contract": dict(getattr(item, "verification_contract", {}) or item_metadata.get("verification_contract") or {}),
                "preserve_behaviors": list(getattr(item, "preserve_behaviors", []) or item_metadata.get("preserve_behaviors") or []),
                "done_definition": list(item.done_definition or []),
                "target_files": list(item.target_files or []),
                "file_changes": list(item_metadata.get("file_changes") or []),
                "risk_level": item.risk_level,
                "item_type": item.item_type,
                "action_type": str(item_metadata.get("action_type") or ""),
                "existing_patch": str(item_metadata.get("patch") or ""),
                "existing_content": existing_content,
                "target_file_exists": bool(existing_target["exists"]),
                "current_file_content": existing_target["content"],
                "current_file_truncated": bool(existing_target["truncated"]),
                "current_target_contents": current_targets,
                "base_file_revisions": {path: str(entry.get("revision") or "absent") for path, entry in current_targets.items()},
                "project_symbols": code_context["symbols"],
                "related_tests": code_context["related_tests"],
                "clarification_implementation_directives": list(item_metadata.get("clarification_implementation_directives") or []),
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

    @staticmethod
    def _all_requirements(pool: AtlasPlanPool) -> list[dict]:
        values = list(getattr(pool, "requirements", []) or (getattr(pool, "metadata", {}) or {}).get("requirement_trace") or [])
        return [dict(v) for v in values if isinstance(v, dict)]

    @staticmethod
    def _completed_item_summaries(pool: AtlasPlanPool) -> list[dict]:
        completed_ids = set(getattr(pool, "completed_item_ids", []) or [])
        summaries: list[dict] = []
        for candidate in getattr(pool, "items", []) or []:
            if str(getattr(candidate, "status", "")).lower() != "completed" and candidate.item_id not in completed_ids:
                continue
            summaries.append({
                "item_id": candidate.item_id,
                "title": candidate.title,
                "goal": candidate.goal,
                "target_files": list(candidate.target_files or []),
                "requirement_ids": list(getattr(candidate, "requirement_ids", []) or []),
                "changed_files": list(((candidate.metadata or {}).get("safe_apply") or {}).get("changed_files") or []),
            })
        return summaries

    def _satisfied_requirement_ids(self, pool: AtlasPlanPool) -> set[str]:
        out: set[str] = set()
        for summary in self._completed_item_summaries(pool):
            out.update(str(v) for v in (summary.get("requirement_ids") or []) if str(v).strip())
        return out

    def _plan_item_requires_content(self, input_payload: dict) -> bool:
        # A plan_item that names target files and is not a delete/run_command MUST yield real patch
        # content to be applicable. For these we treat an empty LLM response as a genuine failure
        # (retry, then report the cause) rather than fabricating a placeholder file.
        if str(input_payload.get("source_type") or "") != "plan_item":
            return False
        item = input_payload.get("item") or {}
        if str(item.get("action_type") or "").lower() in {"delete", "run_command"}:
            return False
        target_files = [str(p).strip() for p in (item.get("target_files") or []) if str(p).strip()]
        return bool(target_files)

    def _verification_feedback(self, input_payload: dict) -> dict | None:
        # Extract a compact, model-facing description of WHY the previously applied content failed
        # verification, set by the self-correction loop on item.metadata["verification"].
        verification = (input_payload.get("latest_verification") or {})
        if not isinstance(verification, dict) or not verification:
            return None
        if str(verification.get("status") or "").lower() != "failed":
            return None
        item = input_payload.get("item") or {}
        prior = str(item.get("existing_content") or "")
        primary_reason = self._primary_verification_reason(verification)
        feedback = {
            "instruction": self._verification_repair_instruction(primary_reason),
            "primary_reason": primary_reason,
            "command": str(verification.get("command") or ""),
            "exit_code": verification.get("exit_code"),
            "stdout_tail": str(verification.get("stdout_tail") or "")[-2000:],
            "stderr_tail": str(verification.get("stderr_tail") or "")[-2000:],
        }
        repair_targets = self._browser_repair_targets(primary_reason, input_payload)
        if repair_targets:
            feedback["repair_target_files"] = repair_targets
            feedback["do_not_repair_by_tests_only"] = True
        if (
            primary_reason.startswith("visual_missing:")
            or primary_reason == "visual_contract_failed"
            or "animation_not_detected" in primary_reason
        ):
            vr_meta = verification.get("metadata") or {}
            smoke_meta = vr_meta.get("browser_smoke") or {}
            if smoke_meta:
                diag = smoke_meta.get("diagnostics") or {}
                canvas_diag = diag.get("canvas") or {}
                feedback["browser_smoke_result"] = {
                    "status": smoke_meta.get("status", ""),
                    "reason": smoke_meta.get("reason", ""),
                    "style_changed": bool(diag.get("style_changed")),
                    "canvas_changed": bool(canvas_diag.get("changed")),
                    "canvas_present": bool(canvas_diag.get("present")),
                    "console_errors": list((smoke_meta.get("console_errors") or [])[:3]),
                }
            vc_meta = vr_meta.get("visual_contract") or {}
            missing = list(vc_meta.get("missing") or [])
            if missing:
                feedback["visual_contract_missing"] = missing
        if prior:
            feedback["previous_content"] = prior[: self.MAX_PROPOSED_CONTENT_CHARS]
        # Routed from the correction router: a test that exercises THIS implementation failed. Tell the
        # model to fix the implementation so the (unchanged) test passes, and give it the test source.
        failing_test_content = str(verification.get("failing_test_content") or "")
        if failing_test_content:
            feedback["instruction"] = (
                "The implementation you produced was applied, then a test that exercises it FAILED. "
                "Fix the IMPLEMENTATION CODE so the test passes — do NOT change the test. Return "
                "corrected, COMPLETE file content for the implementation."
            )
            feedback["failing_test_file"] = str(verification.get("failing_test_file") or "")
            feedback["failing_test_content"] = failing_test_content[: self.MAX_PROPOSED_CONTENT_CHARS]
        return feedback

    def _primary_verification_reason(self, verification: dict) -> str:
        warnings = [str(w) for w in (verification.get("warnings") or [])]
        meta_reason = str(((verification.get("metadata") or {}).get("primary_verification_reason") or ""))
        if meta_reason:
            return meta_reason
        priority = (
            "browser_smoke_failed:js_error",
            "browser_smoke_failed:",
            "visual_missing:",
            "browser_smoke_warning:",
            "visual_contract_failed",
        )
        for prefix in priority:
            for warning in warnings:
                if warning == prefix or warning.startswith(prefix):
                    return warning
        return warnings[0] if warnings else ""

    def _verification_repair_instruction(self, primary_reason: str) -> str:
        if primary_reason.startswith("browser_smoke_failed:js_error"):
            return (
                "The generated browser game files were applied, then browser smoke verification FAILED "
                f"with {primary_reason}. Fix the IMPLEMENTATION files (index.html and relevant js/*.js), "
                "especially script type=module vs classic script consistency, import/export usage, import paths, "
                "and global-scope wiring. Do NOT generate a Python test as the only repair. Return corrected, "
                "COMPLETE browser file content."
            )
        signal = primary_reason.split("visual_missing:", 1)[-1] if primary_reason.startswith("visual_missing:") else ""
        hint = self._SIGNAL_REPAIR_HINTS.get(signal)
        if (
            hint
            or primary_reason.startswith("visual_missing")
            or primary_reason == "visual_contract_failed"
            or "animation_not_detected" in primary_reason
        ):
            base = (
                "適用したブラウザ成果物が visual contract 検証に FAILED した "
                f"({primary_reason})。実装ファイル（index.html と関連する js/*.js, Renderer, GameEngine など）を"
                "修正すること。Python テストだけを生成して通すのは禁止。修正後の COMPLETE なファイル内容を返すこと。"
            )
            return f"{base}\n対処指針: {hint}" if hint else base
        return (
            "Your previous proposed_content was applied to the target file and then FAILED "
            "verification. Fix the root cause shown below and return corrected, COMPLETE file "
            "content. Do not repeat the same mistake."
        )

    def _browser_repair_targets(self, primary_reason: str, input_payload: dict) -> list[str]:
        if not (primary_reason.startswith("browser_smoke_failed:") or primary_reason.startswith("visual_missing") or "animation_not_detected" in primary_reason or primary_reason == "visual_contract_failed"):
            return []
        targets = [str(p) for p in ((input_payload.get("item") or {}).get("target_files") or [])]
        browser_targets = [p for p in targets if p == "index.html" or p.endswith(".html") or p.startswith("js/") or p.endswith(".js") or any(name in p for name in ("Renderer", "GameEngine"))]
        if browser_targets:
            return browser_targets
        if primary_reason.startswith("browser_smoke_failed:js_error"):
            return ["index.html", "js/*.js"]
        return ["index.html", "js/Renderer.js", "js/GameEngine.js"]

    def generate_proposal_with_llm(self, input_payload: dict) -> AtlasPatchProposal:
        assert self.llm_json_fn is not None
        system_prompt = (
            "You generate advisory patch proposals only. Return a single JSON object only, no prose, "
            "no markdown fences. Do not claim changes were applied."
        )
        item_for_task = input_payload.get("item") or {}
        target_exists = bool(item_for_task.get("target_file_exists"))
        if target_exists:
            base_task = (
                "Generate a safe patch proposal as JSON. The target file ALREADY EXISTS; its current "
                "content is provided in input.item.current_file_content. Apply ONLY the change required by "
                "the goal and PRESERVE all unrelated code. "
                "PREFERRED: return \"edits\" — a list of {\"old_string\",\"new_string\"} where each "
                "old_string is an EXACT, UNIQUE snippet copied from the current content (include enough "
                "surrounding context to be unique). This is safest for existing files. "
                "Example: {\"target_files\":[\"app.py\"],\"edits\":[{\"old_string\":\"def foo():\\n    return 1\",\"new_string\":\"def foo():\\n    return 2\"}],\"risk_level\":\"low\"} "
                "ALTERNATIVELY, if a localized edit is impractical, return \"proposed_content\" with the "
                "COMPLETE updated file text. Use input.item.project_symbols to reuse existing functions. "
                "CRITICAL: All new_string values in edits (and proposed_content if used) must contain "
                "COMPLETE, WORKING code — do NOT use placeholder comments (e.g. '// TODO', '// Implement...', "
                "'<!-- content goes here -->'), stub return values (e.g. bare 'return false;' or 'return null;' "
                "with no real logic), or '...' abbreviations. Every new function body must have real, working "
                "logic that fulfills the step goal."
            )
        else:
            base_task = (
                "Generate a safe patch proposal as JSON. For source_type=plan_item that lists target_files, "
                "you MUST return a non-empty \"proposed_content\" string containing the COMPLETE, WORKING file text for the "
                "first target file (this is a new file write, not a diff). "
                "CRITICAL: The proposed_content must be a FULLY IMPLEMENTED file — do NOT use placeholder comments "
                "(e.g. '// TODO', '// Implement...', '<!-- content goes here -->'), stub return values "
                "(e.g. bare 'return false;' or 'return null;' without real logic), or '...' abbreviations. "
                "Every function must contain real, working code that fulfills the step goal. "
                "For a multi-file PlanItem, keep the PlanItem as one work unit and return \"file_changes\" with "
                "one entry per path; do not put one top-level proposed_content across multiple target_files. "
                "Example: {\"target_files\":[\"index.html\"],\"proposed_content\":"
                "\"<!doctype html>\\n<html lang=\\\"en\\\"><head><title>App</title></head>"
                "<body><canvas id=\\\"gameCanvas\\\"></canvas><script>/* complete working implementation */</script></body></html>\","
                "\"risk_level\":\"low\"}"
            )
        content_required = self._plan_item_requires_content(input_payload)
        output_schema = patch_proposal_json_schema(require_content=content_required)
        # If this is a self-correction regeneration, surface the failing verification output so the
        # model fixes the ROOT CAUSE instead of re-emitting the same broken content.
        verification_feedback = self._verification_feedback(input_payload)
        clarification_directives = self._clarification_directives(input_payload)
        last_failure = "llm_no_output"
        parse_failures = 0
        empty_content_attempts = 0
        self_review_feedback: dict | None = None
        for attempt in range(1, self.MAX_LLM_GENERATION_ATTEMPTS + 1):
            user_obj: dict = {"task": base_task, "input": input_payload}
            if clarification_directives:
                user_obj["clarification_directives"] = clarification_directives
            if verification_feedback:
                user_obj["fix_verification_failure"] = verification_feedback
            if self_review_feedback:
                user_obj["self_review_feedback"] = {
                    "instruction": (
                        "The previous generated patch content failed a pre-apply self review. "
                        "Fix these findings before returning the next JSON response."
                    ),
                    **self_review_feedback,
                }
            if attempt > 1:
                # Escalate: tell the model exactly why the previous attempt was unusable.
                user_obj["retry_note"] = (
                    f"Attempt {attempt} of {self.MAX_LLM_GENERATION_ATTEMPTS}. The previous response could not be "
                    "used (it was not valid JSON, or its \"proposed_content\" was empty). Return JSON only with a "
                    "non-empty \"proposed_content\" containing the COMPLETE file text."
                )
            try:
                output = call_llm_json(self.llm_json_fn, system_prompt, json.dumps(user_obj, ensure_ascii=False), json_schema=output_schema) or {}
                if not isinstance(output, dict):
                    raise ValueError("llm_output_not_dict")
                proposal, has_content = self._build_proposal_from_output(output, input_payload)
            except Exception as exc:
                parse_failures += 1
                last_failure = f"llm_output_unparseable:{str(exc) or exc.__class__.__name__}"
                continue
            semantic = self._validate_task_complete_proposal(proposal, input_payload, has_content=has_content)
            proposal.metadata["semantic_validation"] = semantic
            if semantic.get("status") == "failed":
                proposal.warnings.append("semantic_validation_failed")
                last_failure = "semantic_validation_failed:" + ",".join(semantic.get("reasons") or [])
                if attempt < self.MAX_LLM_GENERATION_ATTEMPTS:
                    self_review_feedback = {
                        "status": "failed",
                        "findings": [{"type": "semantic_validation", "severity": "blocking", "message": r} for r in semantic.get("reasons") or []],
                    }
                    continue
                failure = self._no_content_failure_proposal(
                    input_payload,
                    reason=last_failure,
                    parse_failures=parse_failures,
                    empty_content_attempts=empty_content_attempts,
                )
                failure.metadata["semantic_validation"] = semantic
                failure.warnings.append("semantic_validation_failed")
                return failure
            if has_content or not content_required:
                review = self._self_review_proposal(proposal, input_payload, has_content=has_content)
                review["attempt_count"] = attempt
                review["regenerated"] = attempt > 1
                proposal.metadata["self_review"] = review
                if review.get("status") == "failed" and attempt < self.MAX_LLM_GENERATION_ATTEMPTS:
                    proposal.warnings.append(f"self_review_failed_attempt_{attempt}")
                    self_review_feedback = {
                        "status": "failed",
                        "findings": list(review.get("findings") or []),
                    }
                    last_failure = "self_review_failed"
                    continue
                if review.get("status") == "failed":
                    proposal.warnings.append("self_review_findings_unresolved")
                if attempt > 1:
                    proposal.warnings.append(f"llm_generation_succeeded_on_attempt_{attempt}")
                return proposal
            empty_content_attempts += 1
            last_failure = "llm_returned_empty_patch_content"

        # All attempts exhausted. Do NOT fabricate a placeholder file: report the failure honestly so
        # the caller can retry, surface the cause to the user, or skip the item.
        if content_required:
            return self._no_content_failure_proposal(
                input_payload,
                reason=last_failure,
                parse_failures=parse_failures,
                empty_content_attempts=empty_content_attempts,
            )
        # Non-content-required source (e.g. debug_review) with repeated unparseable output: advisory fallback.
        fallback = self.generate_fallback_proposal(input_payload)
        fallback.warnings.append("llm_invalid_json_fallback_proposal")
        fallback.metadata["generation_failure_reason"] = last_failure
        return fallback

    def _clarification_directives(self, input_payload: dict) -> dict | None:
        item = input_payload.get("item") or {}
        directives = item.get("clarification_implementation_directives")
        if not isinstance(directives, list) or not directives:
            return None
        required_elements: list[str] = []
        for directive in directives:
            if not isinstance(directive, dict):
                continue
            for signal in directive.get("signals") or []:
                if not isinstance(signal, dict):
                    continue
                instruction = str(signal.get("instruction") or "").strip()
                signal_name = str(signal.get("signal") or "").strip()
                if instruction:
                    required_elements.append(f"{signal_name}: {instruction}" if signal_name else instruction)
            plan_change = str(directive.get("plan_change_summary") or "").strip()
            scope = str(directive.get("implementation_scope") or "").strip()
            custom = str(directive.get("custom_answer") or "").strip()
            for value in (plan_change, scope, custom):
                if value and value not in required_elements:
                    required_elements.append(value)
        if not required_elements:
            return None
        return {
            "instruction": (
                "The user answered a clarification question and the revised plan requires these "
                "implementation elements. Include them in the generated patch content; do not satisfy "
                "the clarification by adding comments or generic prose only."
            ),
            "required_elements": required_elements,
            "raw_directives": directives,
        }

    def _build_proposal_from_output(self, output: dict, input_payload: dict) -> tuple[AtlasPatchProposal, bool]:
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

        file_changes = self._normalize_file_changes(llm_allowed.get("file_changes"), warnings)
        file_change_paths = [str(fc.get("path") or "") for fc in file_changes if str(fc.get("path") or "")]
        target_files = self._normalize_target_files(llm_allowed.get("target_files"), [*list(item.get("target_files") or []), *file_change_paths], warnings)
        target_files = list(dict.fromkeys([*target_files, *file_change_paths]))

        diff_preview = str(llm_allowed.get("unified_diff_preview") or "")
        if len(diff_preview) > self.MAX_DIFF_PREVIEW_CHARS:
            diff_preview = diff_preview[: self.MAX_DIFF_PREVIEW_CHARS]
            warnings.append("diff_preview_truncated")

        proposed_content = str(llm_allowed.get("proposed_content") or "")
        if len(proposed_content) > self.MAX_PROPOSED_CONTENT_CHARS:
            proposed_content = proposed_content[: self.MAX_PROPOSED_CONTENT_CHARS]
            warnings.append("proposed_content_truncated")

        # Pillar B: surgical string-replacement edits the executor can apply against the current file.
        edits = self._normalize_edits(llm_allowed.get("edits"), warnings)

        has_content = bool(proposed_content or diff_preview or edits or (file_changes and all(has_file_change_content(fc) for fc in file_changes)))
        metadata = {
            "source_type": str(input_payload.get("source_type") or "debug_review"),
            "requested_source_type": str(input_payload.get("requested_source_type") or ""),
            "patch_content_available": has_content,
            "base_file_revisions": dict(input_payload.get("base_file_revisions") or {}),
        }
        if file_changes:
            metadata["file_changes"] = file_changes
            metadata["change_set"] = {**DEFAULT_CHANGE_SET, **(llm_allowed.get("change_set") if isinstance(llm_allowed.get("change_set"), dict) else {})}
        if proposed_content:
            metadata["proposed_content"] = proposed_content
        if edits:
            metadata["edits"] = edits
        for key in (
            "satisfied_requirement_ids",
            "preserved_requirement_ids",
            "implemented_symbols",
            "behavioral_cases",
            "verification_cases",
            "known_limitations",
            "remaining_todos",
        ):
            metadata[key] = self._normalize_string_list(llm_allowed.get(key), warnings, key)

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
        return normalized, has_content

    @staticmethod
    def _normalize_string_list(value: object, warnings: list[str], key: str) -> list[str]:
        if value in (None, ""):
            return []
        if isinstance(value, list):
            out = [str(v).strip() for v in value if str(v).strip()]
            if len(out) != len(value):
                warnings.append(f"{key}_entries_dropped")
            return out
        text = str(value).strip()
        return [text] if text else []

    def _validate_task_complete_proposal(self, proposal: AtlasPatchProposal, input_payload: dict, *, has_content: bool) -> dict:
        item = input_payload.get("item") or {}
        target_files = [str(p) for p in (item.get("target_files") or []) if str(p)]
        allowed_targets = set(target_files)
        metadata = proposal.metadata or {}
        reasons: list[str] = []
        content_by_path = self._proposal_content_by_path(proposal)
        proposed_targets = set(str(p) for p in (proposal.target_files or []) if str(p))
        proposed_targets.update(content_by_path.keys())
        unauthorized_targets = sorted(p for p in proposed_targets if allowed_targets and p not in allowed_targets)
        if unauthorized_targets:
            reasons.append("unauthorized_target_files:" + ",".join(unauthorized_targets))
        if len(target_files) > 1:
            missing_content = sorted(p for p in target_files if not str(content_by_path.get(p) or "").strip())
            if missing_content:
                reasons.append("multi_file_content_missing:" + ",".join(missing_content))
        if self._plan_item_requires_content(input_payload) and not has_content:
            reasons.append("content_missing")

        authorized_req_ids = {str(v) for v in (item.get("requirement_ids") or []) if str(v)}
        all_req_ids = {str(r.get("requirement_id") or "") for r in (input_payload.get("all_requirements") or []) if isinstance(r, dict)}
        satisfied_ids = set(str(v) for v in (metadata.get("satisfied_requirement_ids") or []) if str(v))
        preserved_ids = set(str(v) for v in (metadata.get("preserved_requirement_ids") or []) if str(v))
        reported_ids = satisfied_ids | preserved_ids
        if authorized_req_ids:
            unknown = sorted(req_id for req_id in reported_ids if req_id not in authorized_req_ids)
            if unknown:
                reasons.append("unauthorized_requirement_ids:" + ",".join(unknown))
            if not satisfied_ids:
                reasons.append("satisfied_requirement_ids_missing")
        elif all_req_ids and reported_ids:
            reasons.append("requirement_ids_not_authorized_by_item")

        evidence_present = any(
            metadata.get(key)
            for key in ("satisfied_requirement_ids", "implemented_symbols", "behavioral_cases", "verification_cases")
        )
        if self._plan_item_requires_content(input_payload) and not evidence_present:
            reasons.append("semantic_evidence_missing")
        if metadata.get("remaining_todos"):
            reasons.append("remaining_todos_present")
        if metadata.get("known_limitations"):
            reasons.append("known_limitations_present")
        return {"status": "failed" if reasons else "passed", "reasons": reasons}

    _STUB_PATTERNS: list[re.Pattern] = [
        re.compile(r"//\s*(TODO|Implement|FIXME|Placeholder|implement logic)", re.IGNORECASE),
        re.compile(r"<!--\s*(content|game|todo|placeholder|\.\.\.)\s*(goes here|here|\.\.\.)?", re.IGNORECASE),
        re.compile(r"#\s*(TODO|Implement|FIXME|Placeholder)", re.IGNORECASE),
        re.compile(r"pass\s*#\s*(todo|implement|placeholder)", re.IGNORECASE),
        re.compile(r"^\s*return\s+(false|null|undefined|None)\s*;?\s*$"),
    ]
    _STUB_EXTENSIONS = {".html", ".js", ".ts", ".jsx", ".tsx"}

    def _self_review_proposal(self, proposal: AtlasPatchProposal, input_payload: dict, *, has_content: bool) -> dict:
        """Lightweight pre-apply review for generated content.

        This is intentionally static and bounded: no shell, no imports, no project mutation.
        It catches obvious Python syntax errors, missing literal requirement keywords, and
        stub/placeholder implementations before safe-apply sees the proposal.
        """
        findings: list[dict] = []
        if self._plan_item_requires_content(input_payload) and not has_content:
            findings.append({"type": "content_missing", "severity": "blocking", "message": "patch content is required"})
        content_by_path = self._proposal_content_by_path(proposal)
        for path, content in content_by_path.items():
            ext = Path(str(path)).suffix.lower()
            if ext == ".py":
                try:
                    ast.parse(content or "")
                except SyntaxError as exc:
                    findings.append({
                        "type": "python_syntax_error",
                        "severity": "blocking",
                        "path": path,
                        "message": str(exc),
                    })
            if ext in self._STUB_EXTENSIONS:
                stub_finding = self._detect_stub_content(path, content or "")
                if stub_finding:
                    findings.append(stub_finding)
        combined_content = "\n".join(content_by_path.values())
        for missing in self._missing_requirement_keywords(input_payload, combined_content):
            findings.append({
                "type": "requirement_keyword_missing",
                "severity": "blocking",
                **missing,
            })
        return {
            "status": "failed" if findings else "passed",
            "checks": ["python_ast_parse", "stub_code_detected", "requirement_keyword_match"],
            "findings": findings,
        }

    def _detect_stub_content(self, path: str, content: str) -> dict | None:
        lines = content.splitlines()
        if not lines:
            return None
        stub_lines = [ln for ln in lines if any(p.search(ln) for p in self._STUB_PATTERNS)]
        ratio = len(stub_lines) / max(len(lines), 1)
        if ratio > 0.08 or (len(stub_lines) >= 3 and ratio > 0.05):
            return {
                "type": "stub_code_detected",
                "severity": "blocking",
                "path": path,
                "message": (
                    f"{len(stub_lines)} of {len(lines)} lines ({ratio:.0%}) contain stub/placeholder patterns. "
                    "Rewrite with complete, working implementations. "
                    "Do not use '// TODO', '// Implement...', '<!-- content goes here -->', or bare stubs."
                ),
                "stub_line_examples": stub_lines[:3],
            }
        return None

    def _proposal_content_by_path(self, proposal: AtlasPatchProposal) -> dict[str, str]:
        metadata = proposal.metadata or {}
        out: dict[str, str] = {}
        target_files = [str(p) for p in (proposal.target_files or []) if str(p)]
        if metadata.get("proposed_content"):
            out[target_files[0] if target_files else "proposed_content"] = str(metadata.get("proposed_content") or "")
        for fc in metadata.get("file_changes") or []:
            if not isinstance(fc, dict):
                continue
            path = str(fc.get("path") or "").strip()
            if not path:
                continue
            pieces = [
                str(fc.get("proposed_content") or ""),
                str(fc.get("patch") or ""),
                str(fc.get("unified_diff_preview") or ""),
                str(fc.get("append_content") or ""),
            ]
            edits = fc.get("edits") if isinstance(fc.get("edits"), list) else []
            for edit in edits:
                if isinstance(edit, dict):
                    pieces.append(str(edit.get("new_string") or ""))
            content = "\n".join(piece for piece in pieces if piece)
            if content:
                out[path] = content
        edits = metadata.get("edits") if isinstance(metadata.get("edits"), list) else []
        if edits:
            path = target_files[0] if target_files else "edits"
            out[path] = "\n".join(str(e.get("new_string") or "") for e in edits if isinstance(e, dict))
        if proposal.unified_diff_preview and not out:
            out[target_files[0] if target_files else "unified_diff_preview"] = proposal.unified_diff_preview
        return out

    def _missing_requirement_keywords(self, input_payload: dict, content: str) -> list[dict]:
        item = input_payload.get("item") or {}
        requirements = [
            str(v).strip()
            for v in [item.get("goal"), *list(item.get("done_definition") or [])]
            if str(v).strip()
        ]
        content_l = (content or "").lower()
        missing: list[dict] = []
        for idx, req in enumerate(requirements, start=1):
            tokens = self._requirement_tokens(req)
            if not tokens:
                continue
            matched = [tok for tok in tokens if tok in content_l]
            required_count = max(1, min(len(tokens), (len(tokens) + 1) // 2))
            if len(matched) < required_count:
                missing.append({
                    "requirement_id": f"req_{idx:03d}",
                    "description": req,
                    "missing_keywords": [tok for tok in tokens if tok not in matched],
                })
        return missing

    @staticmethod
    def _requirement_tokens(text: str) -> list[str]:
        stopwords = {
            "the", "and", "for", "with", "that", "this", "should", "must", "shall", "need",
            "needs", "please", "add", "create", "make", "ensure", "show", "display", "update",
            "page", "code", "implement", "implementation", "from", "into", "when", "where",
            "which", "have", "has", "will", "your", "use", "using", "value", "values", "file",
            "files", "text", "appears", "contain", "contains",
        }
        tokens = [
            t.lower()
            for t in re.findall(r"[a-zA-Z][a-zA-Z0-9_]{2,}", text or "")
            if t.lower() not in stopwords
        ]
        return list(dict.fromkeys(tokens))[:8]

    def _no_content_failure_proposal(self, input_payload: dict, *, reason: str, parse_failures: int, empty_content_attempts: int) -> AtlasPatchProposal:
        # Honest "the LLM could not produce patch content" proposal: patch_content_available stays
        # False so the autopilot skips it (no fake success, no garbage file) and the UI can show why.
        item = input_payload.get("item") or {}
        target_files = list(item.get("target_files") or [])
        human_reason = (
            "empty proposed_content returned" if reason == "llm_returned_empty_patch_content"
            else "LLM output was not valid JSON" if str(reason).startswith("llm_output_unparseable")
            else reason
        )
        summary = (
            f"Patch content generation incomplete after {self.MAX_LLM_GENERATION_ATTEMPTS} attempt(s): {human_reason}. "
            "No file was written. Retry generation or refine the plan item."
        )
        return AtlasPatchProposal(
            proposal_id=f"proposal_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}",
            pool_id=str(input_payload.get("pool_id") or ""),
            item_id=str(input_payload.get("item_id") or ""),
            run_id=str(input_payload.get("run_id") or ""),
            title=f"Patch proposal failed for {item.get('title') or input_payload.get('item_id')}",
            summary=summary,
            root_cause="llm_patch_generation_failed",
            proposed_fix=str(item.get("description") or item.get("goal") or "Regenerate patch content for the target files."),
            target_files=target_files,
            suggested_changes=[],
            unified_diff_preview="",
            risk_level=str(item.get("risk_level") or "medium"),
            verification_plan=[],
            rollback_plan=[],
            assumptions=["No patch content was generated; nothing was applied."],
            warnings=["llm_no_patch_content_generated", "plan_item_patch_content_missing"],
            metadata={
                "source_type": str(input_payload.get("source_type") or "plan_item"),
                "patch_content_available": False,
                "generation_failed": True,
                "generation_failure_reason": reason,
                "generation_attempts": self.MAX_LLM_GENERATION_ATTEMPTS,
                "generation_parse_failures": parse_failures,
                "generation_empty_content_attempts": empty_content_attempts,
            },
        )

    def _normalize_edits(self, raw_edits: object, warnings: list[str]) -> list[dict]:
        """Validate LLM-proposed surgical edits: a list of {old_string, new_string} with non-empty
        old_string. Caps the count; drops malformed entries. Returns [] if none usable."""
        if not isinstance(raw_edits, list) or not raw_edits:
            return []
        out: list[dict] = []
        dropped = False
        for e in raw_edits[: self.MAX_EDITS]:
            if not isinstance(e, dict):
                dropped = True
                continue
            old = str(e.get("old_string", ""))
            new = str(e.get("new_string", ""))
            if old == "":
                dropped = True
                continue
            out.append({"old_string": old, "new_string": new})
        if dropped:
            warnings.append("some_edits_dropped")
        return out

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
            posix_path = PurePosixPath(candidate.replace("\\", "/"))
            if path_obj.is_absolute() or posix_path.is_absolute() or ".." in path_obj.parts or ".." in posix_path.parts:
                ignored = True
                continue
            safe_files.append(candidate)
        if ignored:
            warnings.append("unsafe_target_files_ignored")
        return safe_files or list(dict.fromkeys(fallback_target_files))

    def _normalize_file_changes(self, raw_file_changes: object, warnings: list[str]) -> list[dict]:
        if not isinstance(raw_file_changes, list) or not raw_file_changes:
            return []
        out: list[dict] = []
        seen: set[str] = set()
        for raw in raw_file_changes:
            if not isinstance(raw, dict):
                warnings.append("invalid_file_change_ignored")
                continue
            path = str(raw.get("path") or "").strip()
            action = normalize_safe_apply_action_type(raw.get("action_type"))
            posix_path = PurePosixPath(path.replace("\\", "/"))
            if not path or Path(path).is_absolute() or posix_path.is_absolute() or ".." in Path(path).parts or ".." in posix_path.parts:
                warnings.append("unsafe_file_change_ignored")
                continue
            if path in seen:
                warnings.append("duplicate_file_change_path")
                continue
            seen.add(path)
            change = {k: raw[k] for k in ("change_id", "path", "action_type", "content_mode", "proposed_content", "patch", "unified_diff_preview", "edits", "append_content", "metadata") if k in raw}
            change["path"] = path
            change["action_type"] = action
            out.append(change)
        return out

    def generate_fallback_proposal(self, input_payload: dict) -> AtlasPatchProposal:
        source_type = str(input_payload.get("source_type") or "debug_review")
        debug = input_payload.get("debug_review") or {}
        item = input_payload.get("item") or {}
        warnings = ["llm_unavailable_fallback_proposal"]
        if source_type == "plan_item":
            warnings.append("plan_item_patch_content_missing")
        # No LLM content and no fabrication: this advisory proposal carries no applicable patch.
        metadata = {"source_type": source_type, "patch_content_available": False}
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
        # Clear stale content from previous proposals before writing new values so that a
        # revised-but-empty proposal never silently inherits the prior implementation.
        for _stale_key in ("proposed_content", "content", "patch", "unified_diff_preview", "edits", "file_changes"):
            item.metadata.pop(_stale_key, None)
            item.metadata["patch_proposal"].pop(_stale_key, None)
        if proposed_content:
            item.metadata["patch_proposal"]["proposed_content"] = proposed_content
            item.metadata["proposed_content"] = proposed_content
            item.metadata["content"] = proposed_content
        proposal_file_changes = proposal_metadata.get("file_changes") if isinstance(proposal_metadata.get("file_changes"), list) else []
        if proposal_file_changes:
            item.metadata["patch_proposal"]["file_changes"] = proposal_file_changes
            item.metadata["file_changes"] = proposal_file_changes
            item.metadata["change_set"] = {**DEFAULT_CHANGE_SET, **(proposal_metadata.get("change_set") if isinstance(proposal_metadata.get("change_set"), dict) else {}), "change_set_id": f"cs_{item.item_id}"}
            normalize_plan_item_file_changes(item)
        if proposal.unified_diff_preview:
            item.metadata["patch_proposal"]["patch"] = proposal.unified_diff_preview
            item.metadata["unified_diff_preview"] = proposal.unified_diff_preview
            item.metadata["patch"] = proposal.unified_diff_preview
        proposal_edits = proposal_metadata.get("edits") if isinstance(proposal_metadata.get("edits"), list) else []
        if proposal_edits:
            item.metadata["patch_proposal"]["edits"] = proposal_edits
            item.metadata["edits"] = proposal_edits
        # When real patch content was produced, wire the item into the canonical safe-apply
        # vocabulary so the autopilot can actually apply it: action_type must be {create, update}
        # and item_type must be implementation/documentation (the executor + adapter reject others).
        # Empty/unknown action_type defaults to create (greenfield write); an existing action_type
        # is preserved (e.g. an LLM-specified "update" for edits) via normalization. Surgical edits
        # always target an existing file, so force update.
        if proposed_content or proposal.unified_diff_preview or proposal_edits:
            if proposal_edits and not proposed_content:
                item.metadata["action_type"] = "update"
            else:
                item.metadata["action_type"] = normalize_safe_apply_action_type(item.metadata.get("action_type"))
            if str(getattr(item, "item_type", "") or "") not in {"implementation", "documentation"}:
                item.item_type = "implementation"
            # Pillar E: connect the item to a concrete allowlisted verification command so the existing
            # verify -> self-correct loop actually runs (the item writes a test file, or a related test
            # exists for the changed file). Never override a verification the planner already set.
            if not ((item.metadata or {}).get("verification") or {}).get("command_id"):
                try:
                    from agent.atlas_verification_resolver import resolve_verification_for_item

                    spec = resolve_verification_for_item(
                        target_files=list(item.target_files or []),
                        project_path=str(getattr(pool, "project_path", "") or ""),
                    )
                    if spec:
                        item.metadata["verification"] = {**((item.metadata or {}).get("verification") or {}), **spec}
                except Exception:  # noqa: BLE001
                    pass

    def _append_event(self, pool_id: str, run_id: str, event_type: str, item: AtlasPlanItem | None, status: str, warnings: list[str] | None = None, errors: list[str] | None = None) -> None:
        if not run_id:
            return
        self.journal.append_event(pool_id, run_id, {"event_type": event_type, "pool_id": pool_id, "run_id": run_id, "item_id": item.item_id if item else "", "status": status, "warnings": list(warnings or []), "errors": list(errors or []), "created_at": datetime.now(timezone.utc).isoformat()})

    def _record_trace(self, pool_id: str, run_id: str, decision: str, reason: str, detail: dict) -> None:
        if not run_id:
            return
        try:
            trace = PlanTrace(data_root=self.journal.root_dir, pool_id=pool_id, run_id=run_id)
            trace.record(stage="patch_proposal", decision=decision, reason=reason, detail=detail)
            trace.to_journal(self.journal)
        except Exception:
            return
