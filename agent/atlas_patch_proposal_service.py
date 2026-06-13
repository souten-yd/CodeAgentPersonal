from __future__ import annotations

import ast
import hashlib
import json
import re
from html.parser import HTMLParser
from datetime import datetime, timezone
from uuid import uuid4
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from agent.atlas_file_safe_apply_executor import normalize_safe_apply_action_type
from agent.atlas_journal import AtlasJournal
from agent.atlas_llm_json_adapter import call_llm_json
from agent.atlas_llm_schemas import patch_proposal_json_schema
from agent.atlas_plan_item_file_changes import DEFAULT_CHANGE_SET, has_file_change_content, normalize_plan_item_file_changes
from agent.atlas_patch_generation_state import (
    ACTIVE_PATCH_GENERATION_STATES,
    default_patch_generation_state,
    is_patch_generation_success,
    reduce_patch_generation_state,
)
from agent.atlas_patch_proposal_schema import AtlasPatchProposal, AtlasPatchProposalRequest, AtlasPatchProposalResult
from agent.atlas_placeholder_detector import detect_placeholders
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_plan_target_contract import materialize_structural_targets, validate_plan_target_contract
from agent.atlas_plan_trace import PlanTrace
from agent.atlas_workspace_root import resolve_atlas_workspace_root
from agent.project_intelligence.adapters.atlas_generation import AtlasGeneratorBridge
from agent.project_intelligence.contracts import GenerationContextRequest, ProjectIdentity


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
    # an empty/invalid first response but succeed when told the prior attempt was unusable. Attempts
    # are spent only on OBJECTIVE failure signals (parse error, stub/placeholder, broken HTML,
    # real verification failure) — weak keyword heuristics are advisory and never burn a retry.
    MAX_LLM_GENERATION_ATTEMPTS = 3
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

    def __init__(
        self,
        *,
        journal: AtlasJournal,
        storage: AtlasPlanPoolStorage,
        llm_json_fn: Callable[[str, str], dict | None] | None = None,
        project_intelligence: Any | None = None,
    ):
        self.journal = journal
        self.storage = storage
        self.llm_json_fn = llm_json_fn
        self.project_intelligence = project_intelligence

    def propose_for_item(self, request: AtlasPatchProposalRequest) -> AtlasPatchProposalResult:
        run_id = request.run_id or f"patchgen_{uuid4().hex[:10]}"
        if run_id != request.run_id:
            request = request.model_copy(update={"run_id": run_id})
        pool = self.storage.load_pool(request.pool_id)
        item = pool.get_item(request.item_id)
        if item is None:
            warnings = ["item_not_found"]
            self._append_event(pool.pool_id, run_id, "patch_generation_blocked", None, "blocked", warnings=warnings, reason_code="item_not_found")
            self._record_trace(pool.pool_id, request.run_id, "blocked", "item_not_found", {"llm_called": False})
            return AtlasPatchProposalResult(pool_id=pool.pool_id, item_id=request.item_id, run_id=run_id, status="blocked", warnings=warnings, plan_pool=pool.model_dump(), metadata={"patch_generation": default_patch_generation_state(run_id=run_id)})
        # Critique gate (PR-8b): a plan flagged plan_revision_required must not generate patches
        # until the plan is revised / approved. full_auto-continuation pools never set this flag.
        if bool((pool.metadata or {}).get("plan_revision_required")):
            warnings = ["plan_revision_required_blocks_patch"]
            planner_fallback = (pool.metadata or {}).get("planner_fallback")
            if isinstance(planner_fallback, dict) and planner_fallback.get("reason"):
                warnings.append(f"planner_fallback:{planner_fallback.get('reason')}")
            self._record_trace(pool.pool_id, request.run_id, "blocked", "plan_revision_required_blocks_patch", {"llm_called": False})
            recovery_decision = (pool.metadata or {}).get("patch_generation_recovery_decision") or {
                "type": "request_plan_revision",
                "reason": "plan_revision_required",
            }
            return AtlasPatchProposalResult(
                pool_id=pool.pool_id,
                item_id=item.item_id,
                run_id=run_id,
                status="blocked",
                warnings=warnings,
                plan_pool=pool.model_dump(),
                metadata={"recovery_decision": recovery_decision, "patch_generation_started": False},
            )
        ok, warnings = self.validate_item_for_patch_proposal(pool, item, request)
        if not ok:
            self.persist_patch_generation_transition(pool, item, run_id=run_id, event_type="patch_generation_blocked", state="blocked", outcome="blocked", reason_code=warnings[0] if warnings else "patch_generation_blocked", warnings=warnings, retryable=False)
            self._record_trace(pool.pool_id, request.run_id, "blocked", ";".join(warnings), {"llm_called": False})
            return AtlasPatchProposalResult(pool_id=pool.pool_id, item_id=item.item_id, run_id=run_id, status="blocked", warnings=warnings, plan_pool=pool.model_dump(), metadata={"patch_generation": (item.metadata or {}).get("patch_generation") or {}})
        concurrency = self._patch_generation_concurrency_result(pool, item, run_id=run_id)
        if concurrency is not None:
            return concurrency
        try:
            self.persist_patch_generation_transition(pool, item, run_id=run_id, event_type="patch_generation_started", state="running", outcome="active", reason_code="patch_generation_started", retryable=True)
            payload = self.build_proposal_input(pool, item, request)
            payload, pi_generation = self._attach_project_intelligence_generation_context(pool, item, request, payload)
            if pi_generation.get("blocked"):
                warnings = ["project_intelligence_generation_blocked", *list(pi_generation.get("diagnostics") or [])]
                self.persist_patch_generation_transition(
                    pool,
                    item,
                    run_id=run_id,
                    event_type="patch_generation_blocked",
                    state="blocked",
                    outcome="blocked",
                    reason_code=str(pi_generation.get("blocking_reason") or "project_intelligence_generation_blocked"),
                    warnings=warnings,
                    retryable=True,
                )
                self._record_trace(pool.pool_id, request.run_id, "blocked", "project_intelligence_generation_blocked", {"llm_called": False, "project_intelligence_generation": pi_generation})
                return AtlasPatchProposalResult(pool_id=pool.pool_id, item_id=item.item_id, run_id=run_id, status="blocked", warnings=warnings, plan_pool=pool.model_dump(), metadata={"project_intelligence_generation": pi_generation, "patch_generation": (item.metadata or {}).get("patch_generation") or {}})
            proposal = self.generate_proposal_with_llm(payload) if self.llm_json_fn else self.generate_fallback_proposal(payload)
            proposal.pool_id = pool.pool_id
            proposal.item_id = item.item_id
            proposal.run_id = run_id
            if pi_generation:
                proposal.metadata["project_intelligence_generation"] = pi_generation
            # Honest signal: a proposal can be "proposed" yet carry NO applicable content (weak/absent
            # LLM, or fallback). Surface that explicitly so the UI does not report fake success and the
            # autopilot does not silently skip with "missing_patch_or_content".
            _pmeta = proposal.metadata or {}
            _file_changes = _pmeta.get("file_changes") if isinstance(_pmeta.get("file_changes"), list) else []
            has_file_changes_content = bool(_file_changes) and all(has_file_change_content(fc) for fc in _file_changes)
            has_content = bool(proposal.unified_diff_preview or _pmeta.get("proposed_content") or _pmeta.get("edits") or has_file_changes_content)
            if not isinstance(proposal.metadata.get("patch_generation"), dict):
                proposal.metadata["patch_generation"] = self._proposal_patch_generation_metadata(item, proposal)
            if not has_content or proposal.metadata.get("generation_failed"):
                proposal.metadata["patch_generation"] = reduce_patch_generation_state(
                    proposal.metadata.get("patch_generation"),
                    {
                        "event_type": "patch_generation_failed",
                        "run_id": run_id,
                        "state": "failed",
                        "outcome": "failure",
                        "reason_code": str(proposal.metadata.get("generation_failure_reason") or "patch_content_unavailable"),
                        "patch_content_available": False,
                        "retryable": True,
                    },
                )
            patch_generation = proposal.metadata.get("patch_generation") if isinstance(proposal.metadata.get("patch_generation"), dict) else {}
            generation_success = is_patch_generation_success(patch_generation)
            json_path, md_path = self.save_patch_proposal_record(pool.pool_id, item.item_id, proposal)
            self._record_trace(
                pool.pool_id,
                run_id,
                "generated",
                "patch_proposal_generated",
                {"llm_called": bool(self.llm_json_fn), "has_content": has_content, "patch_generation": patch_generation, "project_intelligence_generation": pi_generation},
            )
            source_type = str((proposal.metadata or {}).get("source_type") or request.source_type or "")
            result_status = "proposed" if generation_success or source_type == "debug_review" else str(patch_generation.get("state") or "failed")
            result = AtlasPatchProposalResult(pool_id=pool.pool_id, item_id=item.item_id, run_id=run_id, status=result_status, proposal=proposal, proposal_json_path=json_path, proposal_md_path=md_path, metadata={"patch_content_available": has_content, "patch_generation": patch_generation})
            self.mark_item_from_patch_proposal(pool, item, result)
            self.persist_patch_generation_transition(
                pool,
                item,
                run_id=run_id,
                event_type="patch_generation_succeeded" if generation_success else "patch_generation_failed",
                state="succeeded" if generation_success else "failed",
                outcome="success" if generation_success else "failure",
                proposal=proposal,
                reason_code="patch_generation_succeeded" if generation_success else str(proposal.metadata.get("generation_failure_reason") or "patch_generation_failed"),
                patch_content_available=has_content,
                passed_checks=["semantic_validation", "self_review"] if generation_success else [],
                failed_checks=[] if generation_success else list(((proposal.metadata or {}).get("semantic_validation") or {}).get("reasons") or proposal.warnings or []),
                retryable=not generation_success,
                candidate_fingerprint=self._candidate_fingerprint(proposal),
            )
            result.plan_pool = pool.model_dump()
            return result
        except Exception as exc:
            errors = [str(exc) or exc.__class__.__name__]
            self.persist_patch_generation_transition(pool, item, run_id=run_id, event_type="patch_generation_failed", state="failed", outcome="failure", reason_code="patch_proposal_exception", errors=errors, retryable=True)
            self._record_trace(pool.pool_id, run_id, "failed", "patch_proposal_exception", {"llm_called": bool(self.llm_json_fn), "errors": errors})
            return AtlasPatchProposalResult(pool_id=pool.pool_id, item_id=item.item_id, run_id=run_id, status="failed", errors=errors, plan_pool=pool.model_dump(), metadata={"patch_generation": (item.metadata or {}).get("patch_generation") or {}})

    def _attach_project_intelligence_generation_context(
        self,
        pool: AtlasPlanPool,
        item: AtlasPlanItem,
        request: AtlasPatchProposalRequest,
        payload: dict,
    ) -> tuple[dict, dict]:
        if self.project_intelligence is None:
            return payload, {}
        target_files = [str(path) for path in payload.get("item", {}).get("target_files") or item.target_files or []]
        target_refs = [path if "://" in path else f"file://{path}" for path in target_files if path]
        base_revision = (
            str(request.metadata.get("base_revision") or "")
            or str((item.metadata or {}).get("actual_twin_revision_id") or "")
            or str((pool.metadata or {}).get("actual_twin_revision_id") or "")
            or None
        )
        current_actual_revision = (
            str(request.metadata.get("current_actual_revision") or "")
            or str(request.metadata.get("actual_twin_revision_id") or "")
            or str((pool.metadata or {}).get("current_actual_twin_revision_id") or "")
            or str((pool.metadata or {}).get("actual_twin_revision_id") or "")
            or None
        )
        current_target_content = {
            path: str((entry or {}).get("content") or "")
            for path, entry in dict(payload.get("current_target_contents") or {}).items()
        }
        try:
            result = AtlasGeneratorBridge(self.project_intelligence).build_generation_context(
                request=GenerationContextRequest(
                    project=ProjectIdentity(
                        project_id=str(pool.project_name or (pool.metadata or {}).get("project_id") or "atlas"),
                        workspace_id=str(request.workspace_id or (pool.metadata or {}).get("workspace_id") or "default"),
                        project_path=str(pool.project_path or ""),
                    ),
                    plan_pool_id=pool.pool_id,
                    plan_item_id=item.item_id,
                    target_refs=target_refs,
                    correlation_id=request.run_id or "",
                ),
                legacy_context=dict(payload),
                base_revision=base_revision,
                current_actual_revision=current_actual_revision,
                current_target_content=current_target_content,
            )
        except Exception as exc:  # noqa: BLE001 - do not break legacy generation on PI failure.
            metadata = {
                "status": "failed",
                "mode": "unknown",
                "used_intelligence": False,
                "blocked": False,
                "refresh_requested": False,
                "diagnostics": [str(exc)[:300]],
                "error_kind": exc.__class__.__name__,
            }
            payload["project_intelligence_generation"] = metadata
            return payload, metadata
        metadata = {
            "status": "available",
            "mode": result.mode,
            "used_intelligence": result.used_intelligence,
            "blocked": result.blocked,
            "refresh_requested": result.refresh_requested,
            "context_manifest_id": result.manifest_id,
            "base_revision": result.base_revision,
            "diagnostics": list(result.diagnostics),
            "blocking_reason": "stale_actual_revision" if result.blocked else "",
        }
        payload = dict(result.context or payload)
        payload["project_intelligence_generation"] = metadata
        return payload, metadata

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
            contract = validate_plan_target_contract(item)
            if not contract.ok:
                warnings.extend(contract.reasons)
            materialized = materialize_structural_targets(item)
            if materialized.status in {"blocked", "unsupported"}:
                warnings.extend(str(d.get("reason") or d) for d in materialized.diagnostics)
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
        # Auto-detect: if the item has no debug_review data, it's a plan item (not an incident repair).
        # Only enforce the debug_review gate when the item actually carries debug_review metadata
        # (e.g. it was created via incident repair flow) but that review isn't yet marked "analyzed".
        if not debug_review:
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

    def _read_current_target_contents(self, pool: AtlasPlanPool, item: AtlasPlanItem, request: AtlasPatchProposalRequest, target_files_override: list[str] | None = None) -> dict[str, dict]:
        out: dict[str, dict] = {}
        try:
            target_files = [str(p).strip() for p in (target_files_override if target_files_override is not None else (item.target_files or [])) if str(p).strip()]
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
            from agent.project_intelligence.adapters.code_explorer import ProjectIntelligenceCodeExplorerAdapter

            project_path = str(getattr(pool, "project_path", "") or "")
            if not project_path:
                return out
            materialized = materialize_structural_targets(item)
            target_files = [str(p).strip() for p in ((materialized.patch_target_files or item.target_files) or []) if str(p).strip()]
            # Symbols across the project so the model knows what already exists to reuse (cap small for
            # weak models); related tests for the file under change.
            explorer = ProjectIntelligenceCodeExplorerAdapter()
            syms = explorer.extract_symbols(project_path, max_symbols=40)
            out["symbols"] = [f"{s['file']}:{s['line']} {s.get('signature') or s.get('name','')}" for s in syms[:40]]
            out["related_tests"] = explorer.find_related_tests(project_path, target_files, max_tests=8)
        except Exception:  # noqa: BLE001
            return {"symbols": [], "related_tests": []}
        return out

    def build_proposal_input(self, pool: AtlasPlanPool, item: AtlasPlanItem, request: AtlasPatchProposalRequest) -> dict:
        source_type = self._effective_source_type(item, request)
        debug_review = (item.metadata or {}).get("debug_review") or {}
        item_metadata = item.metadata or {}
        materialized = materialize_structural_targets(item)
        patch_target_files = list(materialized.patch_target_files or item.target_files or [])
        materialized_file_changes = list(materialized.file_changes or [])
        # Ground the model in the target files' CURRENT content (read-before-edit). Prefer real disk
        # bytes; fall back to any content captured in metadata for legacy single-target consumers.
        current_targets = self._read_current_target_contents(pool, item, request, target_files_override=patch_target_files)
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
        plan_file_manifest = self._plan_file_manifest(pool)
        plan_sibling_files = self._plan_sibling_file_contents(pool, item, request, plan_file_manifest)
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
            "plan_file_manifest": plan_file_manifest,
            "plan_sibling_files": plan_sibling_files,
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
                "target_files": patch_target_files,
                "original_target_files": list(item.target_files or []),
                "target_directories": list(getattr(item, "target_directories", []) or []),
                "patch_task_kind": str(getattr(item, "patch_task_kind", "") or ""),
                "operations": [op.model_dump() if hasattr(op, "model_dump") else dict(op) for op in (getattr(item, "operations", []) or [])],
                "file_changes": [*materialized_file_changes, *list(item_metadata.get("file_changes") or [])],
                "materialization": materialized.model_dump(),
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

    def _plan_file_manifest(self, pool: AtlasPlanPool) -> list[dict]:
        """Every file this plan creates/updates, so a step that references sibling files (a
        ``<script src>``, ``<link href>``, an import, a fetch path) uses the plan's REAL filenames
        instead of inventing one (e.g. referencing 'game.js' when the plan creates 'script.js').
        Marks each path created (a prior step already produced it) vs planned (a later step will).
        """
        completed_ids = set(getattr(pool, "completed_item_ids", []) or [])
        manifest: dict[str, dict] = {}
        for plan_item in (pool.items or []):
            produced = plan_item.item_id in completed_ids or str(getattr(plan_item, "status", "")).lower() == "completed"
            for path in (getattr(plan_item, "target_files", []) or []):
                rel = str(path).strip()
                if not rel:
                    continue
                entry = manifest.get(rel)
                if entry is None:
                    manifest[rel] = {
                        "path": rel,
                        "produced_by_items": [plan_item.item_id],
                        "title": str(getattr(plan_item, "title", "") or ""),
                        "status": "created" if produced else "planned",
                    }
                else:
                    entry["produced_by_items"].append(plan_item.item_id)
                    if produced:
                        entry["status"] = "created"
        return list(manifest.values())

    # Total chars of sibling-file content surfaced to the model (bounded to keep the prompt small).
    MAX_SIBLING_FILE_CHARS = 12000
    MAX_SIBLING_FILES_TOTAL_CHARS = 28000

    def _plan_sibling_file_contents(self, pool: AtlasPlanPool, item: AtlasPlanItem, request: AtlasPatchProposalRequest, manifest: list[dict]) -> dict[str, dict]:
        """Current on-disk content of OTHER files this plan already produced, so a step that writes
        tests for (or calls) them uses their REAL API instead of inventing one — the root cause of a
        test file that asserts a 'game.movePlayerLeft()' the implementation never defines. Bounded in
        size; only includes sibling files that already exist on disk.
        """
        own = {str(p).strip() for p in (item.target_files or []) if str(p).strip()}
        sibling_paths = [
            str(entry.get("path"))
            for entry in (manifest or [])
            if isinstance(entry, dict) and str(entry.get("path") or "").strip() and str(entry.get("path")) not in own
        ]
        if not sibling_paths:
            return {}
        raw = self._read_current_target_contents(pool, item, request, target_files_override=sibling_paths)
        out: dict[str, dict] = {}
        budget = self.MAX_SIBLING_FILES_TOTAL_CHARS
        for path in sibling_paths:
            entry = raw.get(path) or {}
            content = str(entry.get("content") or "")
            if not entry.get("exists") or not content:
                continue
            clipped = content[: self.MAX_SIBLING_FILE_CHARS]
            if budget - len(clipped) < 0:
                break
            budget -= len(clipped)
            out[path] = {"content": clipped, "truncated": bool(entry.get("truncated") or len(content) > len(clipped))}
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
                console_errors = [str(e) for e in (smoke_meta.get("console_errors") or []) if str(e).strip()][:8]
                feedback["browser_smoke_result"] = {
                    "status": smoke_meta.get("status", ""),
                    "reason": smoke_meta.get("reason", ""),
                    "style_changed": bool(diag.get("style_changed")),
                    "canvas_changed": bool(canvas_diag.get("changed")),
                    "canvas_present": bool(canvas_diag.get("present")),
                    "console_errors": console_errors,
                }
                # Claude-style targeted repair: put the EXACT console / page errors front-and-center
                # in the instruction (de-duplicated) so a weak model fixes the specific failing line
                # instead of guessing. Without this the errors sit in a nested dict the model ignores.
                if console_errors:
                    seen: list[str] = []
                    for err in console_errors:
                        trimmed = err.strip()[:300]
                        if trimmed and trimmed not in seen:
                            seen.append(trimmed)
                    bullet = "\n".join(f"  - {e}" for e in seen[:6])
                    feedback["instruction"] = (
                        f"{feedback['instruction']}\n\nThe browser reported these EXACT JavaScript "
                        f"errors at runtime — fix the specific cause of EACH one (a missing/renamed "
                        f"symbol, an undefined variable, a bad selector, a wrong import path, or a "
                        f"call before definition):\n{bullet}"
                    )
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
        if str(item_for_task.get("patch_task_kind") or "") == "structural_change":
            base_task = (
                "Generate a safe structural patch proposal as JSON. The plan requires repository "
                "structure, and input.item.materialization contains the Git-representable file_changes "
                "that materialize those directories. Return target_files and file_changes for those "
                "repository-relative files only. Do not return standalone directory names as file targets. "
                "For every input.item operation of type create_file that names a concrete repository file, "
                "return a file_changes entry for that exact path with action_type \"create\", "
                "content_mode \"full_content\", and non-empty \"proposed_content\" containing the COMPLETE, "
                "WORKING file text. For exactly one concrete target file, a top-level \"proposed_content\" "
                "for that file is also acceptable. Do not invent frameworks, entry points, tests, or "
                "unrelated files. Every requested directory must be materialized by a tracked file."
            )
        elif target_exists:
            base_task = (
                "Generate a safe patch proposal as JSON. The target file ALREADY EXISTS; its current "
                "content is provided in input.item.current_file_content. Apply ONLY the change required by "
                "the goal and PRESERVE all unrelated code. "
                "PREFERRED: return \"edits\" — a list of {\"old_string\",\"new_string\"} where each "
                "old_string is an EXACT, UNIQUE snippet copied from the current content (include enough "
                "surrounding context to be unique). This is safest for existing files. "
                "Example: {\"target_files\":[\"app.py\"],\"edits\":[{\"old_string\":\"def foo():\\n    return 1\",\"new_string\":\"def foo():\\n    return 2\"}],\"risk_level\":\"low\"} "
                "To ADD entirely new code (e.g. a new function or block) where there is no existing text to "
                "replace, return an INSERTION edit with an EMPTY old_string and an anchor: "
                "{\"old_string\":\"\",\"insert_after\":\"<exact, unique snippet the new code should FOLLOW>\","
                "\"new_string\":\"<the new code>\"} (or use \"insert_before\"). The anchor must be copied "
                "EXACTLY from the current content, match exactly once, and land the new code inside the "
                "correct scope (e.g. JavaScript must be anchored INSIDE the existing <script> block, never "
                "after </html>). NEVER return an empty old_string without an insert_after or insert_before "
                "anchor. "
                "ALTERNATIVELY, if a localized edit is impractical, return \"proposed_content\" with the "
                "COMPLETE updated file text. Use input.item.project_symbols to reuse existing functions. "
                "CRITICAL: All new_string values in edits (and proposed_content if used) must contain "
                "COMPLETE, WORKING code — do NOT use placeholder comments (e.g. '// TODO', '// Implement...', "
                "'<!-- content goes here -->'), stub return values (e.g. bare 'return false;' or 'return null;' "
                "with no real logic), or '...' abbreviations. Every new function body must have real, working "
                "logic that fulfills the step goal. "
                "Also return \"implemented_symbols\" (functions/files/identifiers you changed), "
                "\"behavioral_cases\" (observable behaviors the change enables) and \"verification_cases\" "
                "(how each behavior can be verified) as short string arrays describing the change."
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
                "Also return \"implemented_symbols\" (functions/files/identifiers you created), "
                "\"behavioral_cases\" (observable behaviors the file enables) and \"verification_cases\" "
                "(how each behavior can be verified) as short string arrays describing the change. "
                "Example: {\"target_files\":[\"index.html\"],\"proposed_content\":"
                "\"<!doctype html>\\n<html lang=\\\"en\\\"><head><title>App</title></head>"
                "<body><canvas id=\\\"gameCanvas\\\"></canvas><script>/* complete working implementation */</script></body></html>\","
                "\"implemented_symbols\":[\"index.html\"],\"behavioral_cases\":[\"renders the page\"],"
                "\"verification_cases\":[\"open index.html in a browser\"],\"risk_level\":\"low\"}"
            )
        # Cross-file consistency: when the plan produces several files, references between them must
        # use the plan's REAL filenames. Without this the model invents names (e.g. an index.html that
        # loads 'game.js' while the plan creates 'script.js'), which 404s and fails browser smoke.
        plan_files = [
            str(entry.get("path"))
            for entry in (input_payload.get("plan_file_manifest") or [])
            if isinstance(entry, dict) and str(entry.get("path") or "").strip()
        ]
        if len(plan_files) > 1:
            base_task += (
                " CROSS-FILE REFERENCES: this plan produces these files: " + ", ".join(plan_files) + ". "
                "When the file you write references another project file (a <script src>, <link href>, "
                "import, or fetch path), you MUST use the EXACT filenames from that list — do not invent "
                "or rename files. Keep references consistent so every file wires together once all steps "
                "are applied."
            )
        # Ground tests/callers in the REAL API of sibling files so a test step does not assert methods
        # the implementation never defines (e.g. game.movePlayerLeft()).
        sibling_files = input_payload.get("plan_sibling_files") or {}
        if sibling_files:
            base_task += (
                " SIBLING FILE CONTENTS: input.plan_sibling_files holds the CURRENT content of other files "
                "this plan already produced (" + ", ".join(str(p) for p in sibling_files) + "). When you "
                "write tests for, import, or call any of them, use their ACTUAL defined/exported API "
                "(functions, classes, globals) EXACTLY as written there — do NOT invent functions, methods, "
                "or an object shape that does not exist in that content. If the implementation uses module-level "
                "functions and globals rather than a class, test it the same way."
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
                if str(item_for_task.get("patch_task_kind") or "") == "structural_change":
                    user_obj["retry_note"] = {
                        "attempt": attempt,
                        "max_attempts": self.MAX_LLM_GENERATION_ATTEMPTS,
                        "instruction": (
                            "The previous candidate did not contain Git-representable structural evidence. "
                            "Generate concrete repository-relative file operations. For create_file operations, "
                            "include full working proposed_content for the created file. Do not return standalone "
                            "directory names as file targets. Materialize every required directory using a tracked file. "
                            "Do not modify unrelated files."
                        ),
                        "semantic_validation": self_review_feedback,
                    }
                else:
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
                claim_repair = self._sanitize_requirement_claims_and_infer_coverage(proposal, input_payload)
                if claim_repair.get("diagnostics"):
                    proposal.metadata.setdefault("requirement_claim_diagnostics", []).extend(claim_repair["diagnostics"])
                # Deterministically backfill semantic evidence (implemented_symbols / behavioral_cases /
                # verification_cases) from the generated content + plan-item metadata when the (weak)
                # model omitted these advisory fields. Mirrors the content-based requirement-coverage
                # inference above so a valid patch is not falsely rejected with semantic_evidence_missing.
                self._infer_semantic_evidence_from_content(proposal, input_payload, has_content=has_content)
            except Exception as exc:
                parse_failures += 1
                last_failure = f"llm_output_unparseable:{str(exc) or exc.__class__.__name__}"
                continue
            proposal.metadata["patch_generation"] = reduce_patch_generation_state(
                proposal.metadata.get("patch_generation") if isinstance(proposal.metadata.get("patch_generation"), dict) else default_patch_generation_state(run_id=str(input_payload.get("run_id") or "")),
                {
                    "event_type": "patch_candidate_generated",
                    "run_id": str(input_payload.get("run_id") or ""),
                    "state": "validating",
                    "outcome": "active",
                    "attempt": attempt,
                    "strategy": "initial_generation" if attempt == 1 else "targeted_regeneration",
                    "candidate_fingerprint": self._candidate_fingerprint(proposal),
                    "patch_content_available": has_content,
                },
            )
            semantic = self._validate_task_complete_proposal(proposal, input_payload, has_content=has_content)
            proposal.metadata["semantic_validation"] = semantic
            if semantic.get("status") == "failed":
                proposal.warnings.append("semantic_validation_failed")
                last_failure = "semantic_validation_failed:" + ",".join(semantic.get("reasons") or [])
                if attempt < self.MAX_LLM_GENERATION_ATTEMPTS:
                    proposal.metadata["patch_generation"] = reduce_patch_generation_state(
                        proposal.metadata.get("patch_generation"),
                        {
                            "event_type": "patch_validation_failed",
                            "run_id": str(input_payload.get("run_id") or ""),
                            "state": "repairing",
                            "outcome": "active",
                            "attempt": attempt,
                            "strategy": "deterministic_contract_or_metadata_repair",
                            "reason_code": "semantic_validation_failed",
                            "failed_checks": list(semantic.get("reasons") or []),
                            "retryable": True,
                            "candidate_fingerprint": self._candidate_fingerprint(proposal),
                            "failure_signature": self._failure_signature(proposal, semantic.get("reasons") or []),
                        },
                    )
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
                failure.metadata["patch_generation"] = reduce_patch_generation_state(
                    proposal.metadata.get("patch_generation"),
                    {
                        "event_type": "patch_generation_failed",
                        "run_id": str(input_payload.get("run_id") or ""),
                        "state": "failed",
                        "outcome": "failure",
                        "attempt": attempt,
                        "strategy": "terminal_failure",
                        "reason_code": last_failure,
                        "failed_checks": list(semantic.get("reasons") or []),
                        "retryable": False,
                        "patch_content_available": False,
                        "candidate_fingerprint": self._candidate_fingerprint(proposal),
                        "failure_signature": self._failure_signature(proposal, semantic.get("reasons") or []),
                    },
                )
                failure.warnings.append("semantic_validation_failed")
                return failure
            if not content_required and not has_content:
                proposal.metadata["patch_generation"] = reduce_patch_generation_state(
                    proposal.metadata.get("patch_generation"),
                    {
                        "event_type": "patch_generation_failed",
                        "run_id": str(input_payload.get("run_id") or ""),
                        "state": "failed",
                        "outcome": "failure",
                        "attempt": attempt,
                        "strategy": "advisory_no_content",
                        "reason_code": "patch_content_unavailable",
                        "patch_content_available": False,
                        "retryable": True,
                        "candidate_fingerprint": self._candidate_fingerprint(proposal),
                    },
                )
                return proposal
            if has_content or not content_required:
                review = self._self_review_proposal(proposal, input_payload, has_content=has_content)
                review["attempt_count"] = attempt
                review["regenerated"] = attempt > 1
                proposal.metadata["self_review"] = review
                if review.get("status") == "failed" and not content_required:
                    proposal.warnings.append("self_review_findings_unresolved")
                    proposal.metadata["patch_generation"] = reduce_patch_generation_state(
                        proposal.metadata.get("patch_generation"),
                        {
                            "event_type": "patch_generation_failed",
                            "run_id": str(input_payload.get("run_id") or ""),
                            "state": "failed",
                            "outcome": "failure",
                            "attempt": attempt,
                            "strategy": "advisory_self_review_failed",
                            "reason_code": "self_review_failed",
                            "failed_checks": ["self_review"],
                            "retryable": True,
                            "patch_content_available": has_content,
                            "candidate_fingerprint": self._candidate_fingerprint(proposal),
                        },
                    )
                    return proposal
                if review.get("status") == "failed" and attempt < self.MAX_LLM_GENERATION_ATTEMPTS:
                    proposal.warnings.append(f"self_review_failed_attempt_{attempt}")
                    self_review_feedback = {
                        "status": "failed",
                        "findings": list(review.get("findings") or []),
                        "advisories": list(review.get("advisories") or []),
                    }
                    last_failure = "self_review_failed"
                    continue
                if review.get("status") == "failed":
                    failure = self._no_content_failure_proposal(
                        input_payload,
                        reason="self_review_failed",
                        parse_failures=parse_failures,
                        empty_content_attempts=empty_content_attempts,
                    )
                    failure.metadata["self_review"] = review
                    failure.metadata["patch_generation"] = reduce_patch_generation_state(
                        proposal.metadata.get("patch_generation"),
                        {
                            "event_type": "patch_generation_failed",
                            "run_id": str(input_payload.get("run_id") or ""),
                            "state": "failed",
                            "outcome": "failure",
                            "attempt": attempt,
                            "strategy": "terminal_failure",
                            "reason_code": "self_review_failed",
                            "failed_checks": ["self_review"],
                            "retryable": False,
                            "patch_content_available": False,
                            "candidate_fingerprint": self._candidate_fingerprint(proposal),
                        },
                    )
                    failure.warnings.append("self_review_findings_unresolved")
                    return failure
                if attempt > 1:
                    proposal.warnings.append(f"llm_generation_succeeded_on_attempt_{attempt}")
                proposal.metadata["patch_generation"] = reduce_patch_generation_state(
                    proposal.metadata.get("patch_generation"),
                    {
                        "event_type": "patch_generation_succeeded",
                        "run_id": str(input_payload.get("run_id") or ""),
                        "state": "succeeded",
                        "outcome": "success",
                        "attempt": attempt,
                        "strategy": "deterministic_repair_then_validation" if attempt == 1 and proposal.metadata.get("requirement_claim_diagnostics") else ("targeted_regeneration" if attempt > 1 else "initial_generation"),
                        "reason_code": "patch_generation_succeeded",
                        "passed_checks": ["semantic_validation", "self_review"],
                        "patch_content_available": has_content,
                        "candidate_fingerprint": self._candidate_fingerprint(proposal),
                    },
                )
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

        raw_file_changes = llm_allowed.get("file_changes")
        if not raw_file_changes and str(item.get("patch_task_kind") or "") == "structural_change":
            raw_file_changes = item.get("file_changes")
            if raw_file_changes:
                warnings.append("structural_materialized_file_changes_used")
        file_changes = self._normalize_file_changes(raw_file_changes, warnings)
        file_change_paths = [str(fc.get("path") or "") for fc in file_changes if str(fc.get("path") or "")]
        target_files = self._normalize_target_files(llm_allowed.get("target_files"), [*list(item.get("target_files") or []), *file_change_paths], warnings)
        target_files = list(dict.fromkeys([*target_files, *file_change_paths]))

        raw_risk = str(llm_allowed.get("risk_level") or item.get("risk_level") or "medium").strip().lower()
        risk_level = raw_risk if raw_risk in self.ALLOWED_RISK_LEVELS else "medium"
        if raw_risk != risk_level:
            warnings.append("llm_risk_level_normalized")
        if risk_level == "medium" and self._is_single_static_html_update(item, target_files):
            risk_level = "low"
            warnings.append("single_static_html_medium_risk_normalized_to_low")

        diff_preview = str(llm_allowed.get("unified_diff_preview") or "")
        if len(diff_preview) > self.MAX_DIFF_PREVIEW_CHARS:
            diff_preview = diff_preview[: self.MAX_DIFF_PREVIEW_CHARS]
            warnings.append("diff_preview_truncated")

        proposed_content = str(llm_allowed.get("proposed_content") or "")
        proposed_content_too_large = len(proposed_content.encode("utf-8")) > self.MAX_PROPOSED_CONTENT_CHARS
        if proposed_content_too_large:
            proposed_content = ""
            warnings.append("proposed_content_too_large")

        # Pillar B: surgical string-replacement edits the executor can apply against the current file.
        edits = self._normalize_edits(llm_allowed.get("edits"), warnings)

        has_content = bool(proposed_content or diff_preview or edits or (file_changes and all(has_file_change_content(fc) for fc in file_changes)))
        metadata = {
            "source_type": str(input_payload.get("source_type") or "debug_review"),
            "requested_source_type": str(input_payload.get("requested_source_type") or ""),
            "patch_content_available": has_content,
            "base_file_revisions": dict(input_payload.get("base_file_revisions") or {}),
            "task_kind": str(item.get("patch_task_kind") or ""),
            "normalized_target_files": list(item.get("original_target_files") or []),
            "normalized_patch_target_files": list(target_files or []),
            "normalized_target_directories": list(item.get("target_directories") or []),
            "normalized_operations": list(item.get("operations") or []),
            "materialization": dict(item.get("materialization") or {}),
        }
        if proposed_content_too_large:
            metadata["oversized_content"] = {
                "field": "proposed_content",
                "max_bytes": self.MAX_PROPOSED_CONTENT_CHARS,
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
            "verification_plan": list(llm_allowed.get("verification_plan") or _default_structural_verification(item)),
            "rollback_plan": list(llm_allowed.get("rollback_plan") or _default_structural_rollback(item)),
            "assumptions": list(llm_allowed.get("assumptions") or item.get("assumptions") or []),
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
        target_directories = [str(p) for p in (item.get("target_directories") or []) if str(p)]
        patch_task_kind = str(item.get("patch_task_kind") or "")
        allowed_targets = set(target_files)
        metadata = proposal.metadata or {}
        reasons: list[str] = []
        missing_evidence: list[str] = []
        content_by_path = self._proposal_content_by_path(proposal)
        proposed_targets = set(str(p) for p in (proposal.target_files or []) if str(p))
        proposed_targets.update(content_by_path.keys())
        enforce_target_scope = str(input_payload.get("source_type") or "").strip() == "plan_item" or self._plan_item_requires_content(input_payload)
        unauthorized_targets = sorted(p for p in proposed_targets if allowed_targets and p not in allowed_targets)
        if enforce_target_scope and unauthorized_targets:
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
        if authorized_req_ids and patch_task_kind != "structural_change":
            unknown = sorted(req_id for req_id in satisfied_ids if req_id not in authorized_req_ids)
            if unknown:
                reasons.append("unauthorized_requirement_ids:" + ",".join(unknown))
            unknown_preserved = sorted(req_id for req_id in preserved_ids if all_req_ids and req_id not in all_req_ids)
            if unknown_preserved:
                reasons.append("unauthorized_preserved_requirement_ids:" + ",".join(unknown_preserved))
            if not satisfied_ids:
                reasons.append("satisfied_requirement_ids_missing")
        elif patch_task_kind != "structural_change" and all_req_ids and (satisfied_ids or preserved_ids):
            reasons.append("requirement_ids_not_authorized_by_item")

        evidence_present = any(
            metadata.get(key)
            for key in ("implemented_symbols", "behavioral_cases", "verification_cases")
        )
        if patch_task_kind == "structural_change":
            for directory in target_directories:
                if not any(path == directory or path.startswith(f"{directory.rstrip('/')}/") for path in content_by_path):
                    missing_evidence.append(f"Tracked file materializing {directory}")
            if missing_evidence:
                reasons.append("structural_targets_not_materialized")
            if any(path in target_directories for path in proposed_targets):
                reasons.append("directory_target_in_target_files")
        elif self._plan_item_requires_content(input_payload) and not evidence_present:
            reasons.append("semantic_evidence_missing")
        advisories: list[str] = []
        if metadata.get("remaining_todos"):
            reasons.append("remaining_todos_present")
        # ``known_limitations`` describe a complete-but-bounded implementation (honest notes like
        # "enemies use linear movement; no wave patterns"), NOT incompleteness. Hard-failing on them
        # punishes honesty and blocked real, working code (e.g. the enemy-spawning game step). Record
        # them as advisory instead. Genuine non-implementation is still caught by the stub/placeholder
        # /AST checks and by ``remaining_todos``.
        if metadata.get("known_limitations"):
            advisories.append("known_limitations_present")
        quality_findings = self._generation_quality_findings(input_payload, content_by_path, metadata)
        for finding in quality_findings:
            reason = str(finding.get("reason") or finding.get("type") or "generation_quality_failed")
            path = str(finding.get("path") or "")
            reasons.append(f"{reason}:{path}" if path else reason)
        return {
            "status": "failed" if reasons else "passed",
            "task_kind": patch_task_kind,
            "normalized_target_files": target_files,
            "normalized_target_directories": target_directories,
            "normalized_operations": list(item.get("operations") or []),
            "reasons": reasons,
            "advisories": advisories,
            "missing_evidence": missing_evidence,
            "quality_findings": quality_findings,
        }

    def _sanitize_requirement_claims_and_infer_coverage(self, proposal: AtlasPatchProposal, input_payload: dict) -> dict[str, Any]:
        metadata = proposal.metadata or {}
        item = input_payload.get("item") or {}
        all_requirements = [r for r in (input_payload.get("all_requirements") or []) if isinstance(r, dict)]
        item_requirement_ids = {str(v) for v in (item.get("requirement_ids") or []) if str(v)}
        all_requirement_ids = {str(r.get("requirement_id") or "") for r in all_requirements if str(r.get("requirement_id") or "")}
        already_satisfied = {
            str(r.get("requirement_id") or "")
            for r in (input_payload.get("already_satisfied_requirements") or [])
            if isinstance(r, dict) and str(r.get("requirement_id") or "")
        }
        satisfied_scope = item_requirement_ids
        preserved_scope = all_requirement_ids | item_requirement_ids | already_satisfied

        raw_satisfied = [str(v) for v in (metadata.get("satisfied_requirement_ids") or []) if str(v)]
        raw_preserved = [str(v) for v in (metadata.get("preserved_requirement_ids") or []) if str(v)]
        valid_satisfied_claims = [req_id for req_id in raw_satisfied if req_id in satisfied_scope]
        valid_preserved_claims = [req_id for req_id in raw_preserved if req_id in preserved_scope]
        unauthorized_satisfied = sorted(set(raw_satisfied) - satisfied_scope)
        unauthorized_preserved = sorted(set(raw_preserved) - preserved_scope)

        content = "\n".join(self._proposal_content_by_path(proposal).values())
        inferred_satisfied = self._infer_requirement_coverage_from_content(input_payload, content)
        metadata["llm_claimed_satisfied_requirement_ids"] = valid_satisfied_claims
        metadata["llm_claimed_preserved_requirement_ids"] = valid_preserved_claims
        metadata["satisfied_requirement_ids"] = sorted(req_id for req_id in inferred_satisfied if req_id in satisfied_scope)
        metadata["preserved_requirement_ids"] = sorted(set(valid_preserved_claims))

        diagnostics: list[dict[str, Any]] = []
        if unauthorized_satisfied:
            diagnostics.append({"type": "unauthorized_satisfied_requirement_claims_removed", "requirement_ids": unauthorized_satisfied})
        if unauthorized_preserved:
            diagnostics.append({"type": "unauthorized_preserved_requirement_claims_removed", "requirement_ids": unauthorized_preserved})
        if valid_satisfied_claims:
            diagnostics.append({"type": "llm_satisfied_claims_not_used_as_proof", "requirement_ids": valid_satisfied_claims})
        if metadata["satisfied_requirement_ids"]:
            diagnostics.append({"type": "content_based_requirement_coverage", "requirement_ids": list(metadata["satisfied_requirement_ids"])})
        metadata["requirement_claim_authorization"] = {
            "satisfied_scope": sorted(satisfied_scope),
            "preserved_scope": sorted(preserved_scope),
            "unauthorized_satisfied_requirement_ids": unauthorized_satisfied,
            "unauthorized_preserved_requirement_ids": unauthorized_preserved,
        }
        proposal.metadata = metadata
        return {"diagnostics": diagnostics}

    def _infer_semantic_evidence_from_content(self, proposal: AtlasPatchProposal, input_payload: dict, *, has_content: bool) -> None:
        """Backfill semantic evidence deterministically when the LLM omitted the advisory fields.

        `_validate_task_complete_proposal` requires at least one of implemented_symbols /
        behavioral_cases / verification_cases for content-required plan items. A weak local model
        reliably produces correct file content but skips these advisory fields, which would wrongly
        fail validation with ``semantic_evidence_missing``. When real content exists we derive the
        evidence from the produced content and the plan item's own contract (acceptance criteria,
        done definition, verification signals) — never fabricating it for an empty generation.

        Only runs for non-structural content-required plan items; structural_change uses
        materialization evidence and is left untouched. LLM-provided fields are respected; only
        empty fields are filled. Records the filled keys under ``semantic_evidence_inferred``.
        """
        if not has_content or not self._plan_item_requires_content(input_payload):
            return
        item = input_payload.get("item") or {}
        if str(item.get("patch_task_kind") or "") == "structural_change":
            return
        metadata = proposal.metadata or {}

        def _nonempty(key: str) -> bool:
            value = metadata.get(key)
            return isinstance(value, list) and bool([v for v in value if str(v).strip()])

        inferred: list[str] = []

        if not _nonempty("implemented_symbols"):
            content_paths = [p for p in self._proposal_content_by_path(proposal).keys() if str(p).strip()]
            symbols = content_paths or [str(p) for p in (proposal.target_files or []) if str(p).strip()]
            if symbols:
                metadata["implemented_symbols"] = list(dict.fromkeys(symbols))
                inferred.append("implemented_symbols")

        if not _nonempty("behavioral_cases"):
            cases = (
                list(item.get("acceptance_criteria") or [])
                or list(item.get("done_definition") or [])
                or ([item.get("goal")] if str(item.get("goal") or "").strip() else [])
            )
            cases = [str(c).strip() for c in cases if str(c).strip()]
            if cases:
                metadata["behavioral_cases"] = list(dict.fromkeys(cases))
                inferred.append("behavioral_cases")

        if not _nonempty("verification_cases"):
            contract = item.get("verification_contract") if isinstance(item.get("verification_contract"), dict) else {}
            signals = list(contract.get("signals") or contract.get("expected_signals") or [])
            cases = signals or list(item.get("acceptance_criteria") or [])
            cases = [str(c).strip() for c in cases if str(c).strip()]
            if cases:
                metadata["verification_cases"] = list(dict.fromkeys(cases))
                inferred.append("verification_cases")

        if inferred:
            metadata["semantic_evidence_inferred"] = inferred
        proposal.metadata = metadata

    def _infer_requirement_coverage_from_content(self, input_payload: dict, content: str) -> set[str]:
        item = input_payload.get("item") or {}
        item_requirement_ids = {str(v) for v in (item.get("requirement_ids") or []) if str(v)}
        content_l = (content or "").lower()
        covered: set[str] = set()
        requirements = [
            r
            for r in (input_payload.get("requirements_for_this_item") or input_payload.get("all_requirements") or [])
            if isinstance(r, dict) and str(r.get("requirement_id") or "") in item_requirement_ids
        ]
        for req in requirements:
            req_id = str(req.get("requirement_id") or "")
            descriptions = [
                str(req.get("description") or ""),
                str(req.get("title") or ""),
                str(req.get("acceptance_criteria") or ""),
            ]
            tokens = self._requirement_tokens(" ".join(descriptions))
            if not tokens:
                continue
            matched = [tok for tok in tokens if tok in content_l]
            required_count = max(1, min(len(tokens), (len(tokens) + 1) // 2))
            if len(matched) >= required_count:
                covered.add(req_id)
        if not covered and len(item_requirement_ids) == 1 and content_l.strip():
            covered.update(item_requirement_ids)
        return covered

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
        Only OBJECTIVE, language-correct defects are blocking: missing-when-required content,
        Python syntax errors, stub/placeholder content, and gross HTML structural breakage.

        High-signal requirement coverage (quoted literals / identifiers from the requirement that
        never appear in the produced artifact) is recorded as a non-blocking ``advisory`` that
        feeds the next regeneration attempt. It never terminally fails an otherwise valid patch:
        meta-predicate words like "exists", "valid", or "prominently" describe the artifact, they
        are not strings that must literally appear inside it. Real correctness is proven later by
        apply -> verification, not by static keyword overlap.
        """
        findings: list[dict] = []
        advisories: list[dict] = []
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
            if ext in {".html", ".htm"}:
                html_blocking, html_advisory = self._html_wellformedness_findings(path, content or "")
                findings.extend(html_blocking)
                advisories.extend(html_advisory)
            if ext in self._STUB_EXTENSIONS:
                stub_finding = self._detect_stub_content(path, content or "")
                if stub_finding:
                    findings.append(stub_finding)
            for placeholder in detect_placeholders(content or "", file_path=path):
                findings.append({
                    "type": "placeholder_content_detected",
                    "severity": "blocking",
                    "path": path,
                    "message": str(placeholder.get("type") or "placeholder"),
                    "line": placeholder.get("line"),
                    "snippet": placeholder.get("snippet", ""),
                })
        combined_content = "\n".join(content_by_path.values())
        if self._plan_item_requires_content(input_payload) and str((input_payload.get("item") or {}).get("patch_task_kind") or "") != "structural_change":
            for missing in self._missing_requirement_keywords(input_payload, combined_content):
                advisories.append({
                    "type": "requirement_keyword_missing",
                    "severity": "advisory",
                    **missing,
                })
        return {
            "status": "failed" if findings else "passed",
            "checks": ["python_ast_parse", "stub_code_detected", "placeholder_detected", "html_wellformedness", "requirement_keyword_advisory"],
            "findings": findings,
            "advisories": advisories,
        }

    def _generation_quality_findings(self, input_payload: dict, content_by_path: dict[str, str], metadata: dict) -> list[dict]:
        findings: list[dict] = []
        oversized = metadata.get("oversized_content") if isinstance(metadata.get("oversized_content"), dict) else {}
        if oversized:
            findings.append({"type": "oversized_content", "reason": "content_too_large", **oversized})
        for path, content in content_by_path.items():
            for placeholder in detect_placeholders(content or "", file_path=path):
                findings.append({
                    "type": "placeholder_content_detected",
                    "reason": "placeholder_content_detected",
                    "path": path,
                    "line": placeholder.get("line"),
                    "snippet": placeholder.get("snippet", ""),
                })
            findings.extend(self._trivial_function_findings(path, content or ""))
        findings.extend(self._disconnected_artifact_findings(content_by_path))
        findings.extend(self._requirement_evidence_mismatch_findings(input_payload, content_by_path, metadata))
        return findings

    def _trivial_function_findings(self, path: str, content: str) -> list[dict]:
        ext = Path(str(path)).suffix.lower()
        findings: list[dict] = []
        if ext == ".py":
            try:
                tree = ast.parse(content or "")
            except SyntaxError:
                return findings
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                body = [stmt for stmt in node.body if not (isinstance(stmt, ast.Expr) and isinstance(getattr(stmt, "value", None), ast.Constant) and isinstance(stmt.value.value, str))]
                if len(body) != 1:
                    continue
                stmt = body[0]
                trivial = isinstance(stmt, (ast.Pass, ast.Raise)) or (
                    isinstance(stmt, ast.Return)
                    and isinstance(stmt.value, ast.Constant)
                    and stmt.value.value in (None, False, True, 0, 1, "", "TODO", "todo")
                )
                if trivial:
                    findings.append({"type": "trivial_function_body", "reason": "trivial_function_body", "path": path, "function": node.name})
            return findings
        if ext in {".js", ".ts", ".jsx", ".tsx", ".html"}:
            pattern = re.compile(
                r"(?:function\s+([A-Za-z_$][\w$]*)\s*\([^)]*\)|([A-Za-z_$][\w$]*)\s*=\s*\([^)]*\)\s*=>)\s*\{\s*(?://[^\n]*\n\s*)?(?:return\s+(?:false|true|null|undefined|0|1|['\"][^'\"]*['\"])\s*;?)?\s*\}",
                re.IGNORECASE | re.MULTILINE,
            )
            for match in pattern.finditer(content or ""):
                findings.append({
                    "type": "trivial_function_body",
                    "reason": "trivial_function_body",
                    "path": path,
                    "function": match.group(1) or match.group(2) or "",
                })
        return findings

    @staticmethod
    def _disconnected_artifact_findings(content_by_path: dict[str, str]) -> list[dict]:
        html_paths = [path for path in content_by_path if Path(str(path)).suffix.lower() == ".html"]
        if not html_paths:
            return []
        html = "\n".join(content_by_path[path] for path in html_paths).lower()
        findings: list[dict] = []
        for path in content_by_path:
            suffix = Path(str(path)).suffix.lower()
            if suffix not in {".js", ".css"}:
                continue
            name = Path(str(path)).name.lower()
            if name and name not in html:
                findings.append({"type": "disconnected_artifact", "reason": "disconnected_artifact", "path": path})
        return findings

    def _requirement_evidence_mismatch_findings(self, input_payload: dict, content_by_path: dict[str, str], metadata: dict) -> list[dict]:
        satisfied = {str(v) for v in (metadata.get("satisfied_requirement_ids") or []) if str(v)}
        if not satisfied:
            return []
        combined = "\n".join(content_by_path.values()).lower()
        findings: list[dict] = []
        for req in input_payload.get("requirements_for_this_item") or []:
            if not isinstance(req, dict):
                continue
            req_id = str(req.get("requirement_id") or "")
            if req_id not in satisfied:
                continue
            tokens = self._requirement_tokens(str(req.get("description") or ""))
            if tokens and not any(token in combined for token in tokens):
                findings.append({"type": "requirement_evidence_mismatch", "reason": "requirement_evidence_mismatch", "requirement_id": req_id})
        return findings

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

    # Void (self-closing) HTML elements that legitimately have no closing tag.
    _HTML_VOID_ELEMENTS = frozenset({
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr",
    })
    # Elements whose absence/breakage signals a genuinely malformed document.
    _HTML_STRUCTURAL_ELEMENTS = ("html", "head", "body")

    def _html_wellformedness_findings(self, path: str, content: str) -> tuple[list[dict], list[dict]]:
        """Objective, bounded HTML structural check using only the standard library.

        Returns ``(blocking, advisory)``. Blocking covers gross breakage that makes the document
        invalid (mismatched/unclosed structural tags). Cosmetic issues (e.g. a missing <!doctype>)
        are advisory. No external parser (lxml etc.) is introduced.
        """
        text = content or ""
        if not text.strip():
            return ([{
                "type": "html_empty_content",
                "severity": "blocking",
                "path": path,
                "message": "HTML file content is empty.",
            }], [])

        void_elements = self._HTML_VOID_ELEMENTS

        class _TagBalanceParser(HTMLParser):
            def __init__(self) -> None:
                super().__init__(convert_charrefs=True)
                self.stack: list[str] = []
                self.mismatches: list[str] = []
                self.parse_error = ""

            def handle_starttag(self, tag: str, attrs: Any) -> None:
                if tag.lower() not in void_elements:
                    self.stack.append(tag.lower())

            def handle_startendtag(self, tag: str, attrs: Any) -> None:
                # Explicit self-close (<br/>) — never pushed onto the stack.
                return

            def handle_endtag(self, tag: str) -> None:
                tag = tag.lower()
                if tag in void_elements:
                    return
                if tag in self.stack:
                    # Pop until we reach the matching open tag (tolerate optional-close inline tags).
                    while self.stack and self.stack[-1] != tag:
                        self.stack.pop()
                    if self.stack:
                        self.stack.pop()
                else:
                    self.mismatches.append(tag)

        parser = _TagBalanceParser()
        try:
            parser.feed(text)
            parser.close()
        except Exception as exc:  # pragma: no cover - HTMLParser is lenient; defensive only
            return ([{
                "type": "html_parse_error",
                "severity": "blocking",
                "path": path,
                "message": str(exc),
            }], [])

        blocking: list[dict] = []
        advisory: list[dict] = []

        text_l = text.lower()
        for element in self._HTML_STRUCTURAL_ELEMENTS:
            has_open = f"<{element}" in text_l
            has_close = f"</{element}>" in text_l
            if has_open and not has_close:
                blocking.append({
                    "type": "html_unclosed_structural_tag",
                    "severity": "blocking",
                    "path": path,
                    "message": f"<{element}> is opened but never closed.",
                })

        unclosed = [tag for tag in parser.stack if tag in self._HTML_STRUCTURAL_ELEMENTS]
        if unclosed:
            blocking.append({
                "type": "html_unbalanced_tags",
                "severity": "blocking",
                "path": path,
                "message": f"Unbalanced structural tags left open: {', '.join(dict.fromkeys(unclosed))}.",
            })
        if parser.mismatches:
            structural_mismatch = [t for t in parser.mismatches if t in self._HTML_STRUCTURAL_ELEMENTS]
            if structural_mismatch:
                blocking.append({
                    "type": "html_unbalanced_tags",
                    "severity": "blocking",
                    "path": path,
                    "message": f"Closing tags without a matching open tag: {', '.join(dict.fromkeys(structural_mismatch))}.",
                })

        if "<!doctype" not in text_l:
            advisory.append({
                "type": "html_missing_doctype",
                "severity": "advisory",
                "path": path,
                "message": "Document is missing a <!doctype html> declaration.",
            })

        return (blocking, advisory)

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
        """Advisory-only high-signal coverage check.

        Only emits when a requirement carries *high-signal* tokens — quoted literals (e.g.
        'HelloWorld') or code identifiers — and NONE of them appear in the produced content.
        Meta-predicate words (exists / valid / prominently / well-formed ...) and the target
        filename are deliberately excluded: they describe the artifact, they are not strings that
        must literally appear inside it. This is never blocking; it only hints the next attempt.
        """
        item = input_payload.get("item") or {}
        requirements = [
            str(v).strip()
            for v in [item.get("goal"), *list(item.get("done_definition") or [])]
            if str(v).strip()
        ]
        # Target filenames are satisfied by file existence, not by appearing in file content.
        target_basenames = {
            Path(str(p)).name.lower()
            for p in (item.get("target_files") or [])
            if str(p).strip()
        }
        target_stems = {Path(name).stem for name in target_basenames}
        excluded = target_basenames | target_stems
        content_l = (content or "").lower()
        missing: list[dict] = []
        for idx, req in enumerate(requirements, start=1):
            tokens = [
                tok for tok in self._high_signal_requirement_tokens(req)
                if tok not in excluded
            ]
            if not tokens:
                continue
            matched = [tok for tok in tokens if tok in content_l]
            if not matched:
                missing.append({
                    "requirement_id": f"req_{idx:03d}",
                    "description": req,
                    "missing_keywords": tokens,
                })
        return missing

    @staticmethod
    def _high_signal_requirement_tokens(text: str) -> list[str]:
        """Extract only tokens that genuinely should appear in the produced artifact.

        High-signal = quoted literals ('...', "...", `...`) and code identifiers
        (snake_case, camelCase, PascalCase, foo()). Plain descriptive prose is ignored.
        """
        raw = text or ""
        signals: list[str] = []
        # Quoted literals carry the strongest intent (the exact text the user asked to appear).
        for match in re.findall(r"'([^']+)'|\"([^\"]+)\"|`([^`]+)`", raw):
            literal = next((g for g in match if g), "").strip()
            if literal:
                signals.append(literal.lower())
        # Code identifiers: multi-word case styles or call syntax.
        for match in re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(\)", raw):
            signals.append(match.lower())
        for token in re.findall(r"\b[A-Za-z][A-Za-z0-9_]*\b", raw):
            is_snake = "_" in token
            is_camel_or_pascal = bool(re.search(r"[a-z][A-Z]", token)) or bool(re.match(r"[A-Z][a-z]+[A-Z]", token))
            if is_snake or is_camel_or_pascal:
                signals.append(token.lower())
        # De-duplicate while preserving order; cap to keep the advisory compact.
        return list(dict.fromkeys(signals))[:8]

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
        target_directories = list(item.get("target_directories") or [])
        patch_task_kind = str(item.get("patch_task_kind") or "")
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
            status="failed",
            title=f"Patch proposal failed for {item.get('title') or input_payload.get('item_id')}",
            summary=summary,
            root_cause="llm_patch_generation_failed",
            proposed_fix=str(item.get("description") or item.get("goal") or "Regenerate patch content for the target files."),
            target_files=target_files,
            suggested_changes=[],
            unified_diff_preview="",
            risk_level=str(item.get("risk_level") or "medium"),
            verification_plan=_default_structural_verification(item),
            rollback_plan=_default_structural_rollback(item),
            assumptions=["No patch content was generated; nothing was applied."],
            warnings=["llm_no_patch_content_generated", "plan_item_patch_content_missing"],
            metadata={
                "source_type": str(input_payload.get("source_type") or "plan_item"),
                "patch_content_available": False,
                "generation_failed": True,
                "generation_failure_reason": reason,
                "detailed_failure_reasons": [reason],
                "task_kind": patch_task_kind,
                "normalized_target_files": target_files,
                "normalized_target_directories": target_directories,
                "normalized_operations": list(item.get("operations") or []),
                "materialization": dict(item.get("materialization") or {}),
                "generation_attempts": self.MAX_LLM_GENERATION_ATTEMPTS,
                "generation_parse_failures": parse_failures,
                "generation_empty_content_attempts": empty_content_attempts,
            },
        )

    def _normalize_edits(self, raw_edits: object, warnings: list[str]) -> list[dict]:
        """Validate LLM-proposed surgical edits. Each entry is either a REPLACEMENT (non-empty
        old_string -> new_string) or an INSERTION (empty old_string with an insert_after/insert_before
        anchor, or a bare new_string to append). Caps the count; drops malformed entries (an empty
        old_string with no anchor and no new_string would land code nowhere). Returns [] if none usable."""
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
            insert_after = str(e.get("insert_after", ""))
            insert_before = str(e.get("insert_before", ""))
            if old == "":
                if not (insert_after or insert_before or new):
                    dropped = True
                    continue
                entry = {"old_string": "", "new_string": new}
                if insert_after:
                    entry["insert_after"] = insert_after
                elif insert_before:
                    entry["insert_before"] = insert_before
                out.append(entry)
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
            # Nested edits must pass the SAME validation as top-level edits — without this, a malformed
            # edit (e.g. an empty old_string with no anchor) slips through and blocks the atomic apply.
            if "edits" in change:
                change["edits"] = self._normalize_edits(change.get("edits"), warnings)
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
            status="failed" if source_type == "plan_item" else "proposed",
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
            if str(getattr(item, "patch_task_kind", "") or "") != "structural_change":
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
        # Only explicit or compatible legacy action types are normalized. Empty/unknown values stay
        # invalid so the safe-apply path can fail closed instead of silently creating files.
        # Surgical edits always target an existing file, so force update.
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

    def persist_patch_generation_transition(
        self,
        pool: AtlasPlanPool,
        item: AtlasPlanItem,
        *,
        run_id: str,
        event_type: str,
        state: str,
        outcome: str,
        reason_code: str,
        proposal: AtlasPatchProposal | None = None,
        patch_content_available: bool = False,
        passed_checks: list[str] | None = None,
        failed_checks: list[str] | None = None,
        diagnostics: list[dict[str, Any]] | None = None,
        warnings: list[str] | None = None,
        errors: list[str] | None = None,
        retryable: bool = False,
        attempt: int | None = None,
        strategy: str = "",
        candidate_fingerprint: str = "",
        failure_signature: str = "",
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        current = (item.metadata or {}).get("patch_generation") if isinstance((item.metadata or {}).get("patch_generation"), dict) else default_patch_generation_state(run_id=run_id)
        event = {
            "event_type": event_type,
            "pool_id": pool.pool_id,
            "item_id": item.item_id,
            "run_id": run_id,
            "state": state,
            "outcome": outcome,
            "reason_code": reason_code,
            "retryable": retryable,
            "attempt": int(attempt if attempt is not None else ((proposal.metadata or {}).get("patch_generation") or {}).get("attempt") if proposal else current.get("attempt") or 0),
            "strategy": strategy or str(((proposal.metadata or {}).get("patch_generation") or {}).get("strategy") if proposal else current.get("strategy") or ""),
            "candidate_fingerprint": candidate_fingerprint or str(((proposal.metadata or {}).get("patch_generation") or {}).get("candidate_fingerprint") if proposal else current.get("candidate_fingerprint") or ""),
            "failure_signature": failure_signature or str(current.get("failure_signature") or ""),
            "patch_content_available": bool(patch_content_available),
            "passed_checks": list(passed_checks or []),
            "failed_checks": list(failed_checks or []),
            "diagnostics": list(diagnostics or []),
            "warnings": list(warnings or []),
            "errors": list(errors or []),
            "created_at": now,
        }
        next_state = reduce_patch_generation_state(current, event)
        if proposal is not None:
            proposal.metadata["patch_generation"] = next_state
            proposal.metadata["patch_generation_state"] = next_state.get("state")
            proposal.metadata["patch_generation_outcome"] = next_state.get("outcome")
        item.metadata = dict(item.metadata or {})
        item.metadata["patch_generation"] = next_state
        item.metadata["patch_generation_state"] = next_state.get("state")
        item.metadata["patch_generation_outcome"] = next_state.get("outcome")
        item.metadata["latest_patch_generation_run_id"] = run_id
        if state == "failed":
            item.status = "failed"
            if item.item_id not in pool.failed_item_ids:
                pool.failed_item_ids.append(item.item_id)
        elif state == "blocked":
            item.status = "blocked"
            if item.item_id not in pool.blocked_item_ids:
                pool.blocked_item_ids.append(item.item_id)
        elif state == "cancelled":
            item.status = "cancelled"
        elif state in {"queued", "running", "validating", "repairing", "retrying"}:
            item.status = "executing"
            pool.current_item_id = item.item_id
            if str(pool.status or "") in {"ready", "approved", "waiting"}:
                pool.status = "running"
        elif state == "succeeded":
            if item.status == "executing":
                item.status = "ready"
            pool.current_item_id = item.item_id
        pool.metadata = dict(pool.metadata or {})
        pool.metadata["latest_patch_generation"] = next_state
        pool.metadata.setdefault("patch_generation_reconciliation_inputs", {})[item.item_id] = {
            "run_id": run_id,
            "state": next_state.get("state"),
            "outcome": next_state.get("outcome"),
            "updated_at": next_state.get("updated_at"),
        }
        self.storage.save_pool(pool)
        self.journal.save_plan_pool(pool)
        self.journal.write_checkpoint(pool=pool, next_action=self._checkpoint_next_action(next_state))
        self._append_event(pool.pool_id, run_id, event_type, item, state, warnings=warnings, errors=errors, reason_code=reason_code, patch_generation=next_state)
        return next_state

    def _patch_generation_concurrency_result(self, pool: AtlasPlanPool, item: AtlasPlanItem, *, run_id: str) -> AtlasPatchProposalResult | None:
        current = (item.metadata or {}).get("patch_generation") if isinstance((item.metadata or {}).get("patch_generation"), dict) else {}
        current_run_id = str(current.get("run_id") or "")
        current_state = str(current.get("state") or "").lower()
        if current_state in ACTIVE_PATCH_GENERATION_STATES and current_run_id:
            if current_run_id == run_id:
                return AtlasPatchProposalResult(
                    pool_id=pool.pool_id,
                    item_id=item.item_id,
                    run_id=run_id,
                    status=current_state,
                    plan_pool=pool.model_dump(),
                    metadata={"patch_generation": current, "idempotent": True},
                    warnings=["patch_generation_run_already_active"],
                )
            if self._active_run_is_stale(current):
                self.persist_patch_generation_transition(
                    pool,
                    item,
                    run_id=current_run_id,
                    event_type="patch_generation_failed",
                    state="failed",
                    outcome="failure",
                    reason_code="stale_active_patch_generation_run",
                    retryable=True,
                    diagnostics=[{"type": "stale_active_run_recovered", "stale_run_id": current_run_id, "new_run_id": run_id}],
                )
                return None
            return AtlasPatchProposalResult(
                pool_id=pool.pool_id,
                item_id=item.item_id,
                run_id=run_id,
                status="blocked",
                plan_pool=pool.model_dump(),
                warnings=["patch_generation_active_run_exists"],
                metadata={"active_run_id": current_run_id, "patch_generation": current},
            )
        return None

    @staticmethod
    def _active_run_is_stale(current: dict[str, Any]) -> bool:
        updated_at = str(current.get("updated_at") or "")
        if not updated_at:
            return False
        try:
            dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - dt).total_seconds() > 3600
        except Exception:
            return False

    @staticmethod
    def _checkpoint_next_action(patch_generation: dict[str, Any]) -> str:
        state = str((patch_generation or {}).get("state") or "")
        if state == "succeeded":
            return "Review and approve the Patch Proposal before Safe Apply."
        if state == "failed":
            return "Retry Patch generation or revise the Plan."
        if state == "blocked":
            return "Resolve the Patch generation block before continuing."
        return "Patch generation is active; wait for the current run or cancel it."

    def _proposal_patch_generation_metadata(self, item: AtlasPlanItem, proposal: AtlasPatchProposal) -> dict[str, Any]:
        proposal_state = proposal.metadata.get("patch_generation") if isinstance(proposal.metadata.get("patch_generation"), dict) else {}
        item_state = (item.metadata or {}).get("patch_generation") if isinstance((item.metadata or {}).get("patch_generation"), dict) else {}
        return proposal_state or item_state or default_patch_generation_state(run_id=proposal.run_id)

    def _candidate_fingerprint(self, proposal: AtlasPatchProposal) -> str:
        payload = {
            "target_files": list(proposal.target_files or []),
            "unified_diff_preview": proposal.unified_diff_preview,
            "metadata_content": {
                "proposed_content": (proposal.metadata or {}).get("proposed_content"),
                "edits": (proposal.metadata or {}).get("edits"),
                "file_changes": (proposal.metadata or {}).get("file_changes"),
            },
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()

    @staticmethod
    def _is_single_static_html_update(item: dict[str, Any], target_files: list[str]) -> bool:
        if len(target_files) != 1:
            return False
        target = str(target_files[0] or "").strip().replace("\\", "/").lower()
        if not target.endswith(".html"):
            return False
        action_type = normalize_safe_apply_action_type(item.get("action_type"))
        return action_type in {"create", "update"}

    def _failure_signature(self, proposal: AtlasPatchProposal, reasons: list[str]) -> str:
        payload = {"fingerprint": self._candidate_fingerprint(proposal), "reasons": sorted(str(r) for r in reasons)}
        return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()

    def _append_event(self, pool_id: str, run_id: str, event_type: str, item: AtlasPlanItem | None, status: str, warnings: list[str] | None = None, errors: list[str] | None = None, reason_code: str = "", patch_generation: dict[str, Any] | None = None) -> None:
        if not run_id:
            return
        self.journal.append_event(pool_id, run_id, {"event_type": event_type, "pool_id": pool_id, "run_id": run_id, "item_id": item.item_id if item else "", "status": status, "state": status, "outcome": (patch_generation or {}).get("outcome", ""), "reason_code": reason_code, "warnings": list(warnings or []), "errors": list(errors or []), "patch_generation": patch_generation or {}, "created_at": datetime.now(timezone.utc).isoformat()})

    def _record_trace(self, pool_id: str, run_id: str, decision: str, reason: str, detail: dict) -> None:
        if not run_id:
            return
        try:
            trace = PlanTrace(data_root=self.journal.root_dir, pool_id=pool_id, run_id=run_id)
            trace.record(stage="patch_proposal", decision=decision, reason=reason, detail=detail)
            trace.to_journal(self.journal)
        except Exception:
            return


def _default_structural_verification(item: dict) -> list[str]:
    if str(item.get("patch_task_kind") or "") != "structural_change":
        return []
    return [
        "Parse the unified diff or file_changes successfully.",
        "Confirm every generated path is repository-relative.",
        "Confirm each requested directory is materialized by a tracked file.",
        "Confirm no unrelated files were changed.",
    ]


def _default_structural_rollback(item: dict) -> list[str]:
    if str(item.get("patch_task_kind") or "") != "structural_change":
        return []
    return [
        "Remove only the newly created materialization files.",
        "Remove resulting empty directories where applicable.",
        "Do not restore or modify unrelated paths.",
    ]
