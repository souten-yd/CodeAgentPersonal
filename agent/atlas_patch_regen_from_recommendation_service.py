from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agent.atlas_dev_tool_path import validate_relative_path
from agent.atlas_journal import AtlasJournal
from agent.atlas_patch_regen_from_recommendation_policies import get_patch_regen_from_recommendation_policy
from agent.atlas_patch_regen_from_recommendation_schema import (
    AtlasPatchRegenFromRecommendationRequest,
    AtlasPatchRegenFromRecommendationResult,
)
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_supervised_patch_regen_schema import AtlasPatchRegenRequest
from agent.atlas_supervised_patch_regen_service import AtlasSupervisedPatchRegenService


ALLOWED_PATCH_REGEN_STATUSES = {"proposal_ready", "manual_required", "not_regeneratable", "blocked", "failed"}


def _dump(value):
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return value if isinstance(value, dict) else dict(value or {})


class AtlasPatchRegenFromRecommendationService:
    def __init__(self, *, storage=None, journal=None, patch_regen_service=None):
        self.storage = storage or AtlasPlanPoolStorage(Path("ca_data"))
        self.journal = journal or AtlasJournal(Path("ca_data"))
        self.patch_regen_service = patch_regen_service or AtlasSupervisedPatchRegenService(storage=self.storage, journal=self.journal)

    def run(self, request: AtlasPatchRegenFromRecommendationRequest) -> AtlasPatchRegenFromRecommendationResult:
        recommendation_exec_id = f"regenexec_{uuid4().hex[:12]}"
        run_id = request.run_id or recommendation_exec_id
        warnings: list[str] = []
        errors: list[str] = []
        validation: dict = {"allowed": False, "checks": []}
        recommendation_result: dict = {}
        recommended_payload: dict = {}
        patch_regen_result: dict = {}
        patch_regen_result_id = ""
        patch_request_preview: dict = {}
        policy = get_patch_regen_from_recommendation_policy(request.policy_id)
        request.policy_id = policy.policy_id

        self.emit_event("patch_regen_from_recommendation_started", request, recommendation_exec_id, run_id=run_id)
        status = "failed_internal"
        try:
            self.validate_request_ids(request)
            recommendation_result = self.load_recommendation_result(request.pool_id, request.recommendation_run_id)
            self.emit_event("patch_regen_from_recommendation_input_loaded", request, recommendation_exec_id, run_id=run_id, recommendation_result=recommendation_result)
            recommended_payload = dict(recommendation_result.get("recommended_payload") or {})
            validation = self.validate_recommendation_for_patch_regen(recommendation_result, request, policy)
            errors.extend(validation.get("errors") or [])
            warnings.extend(validation.get("warnings") or [])
            self.emit_event("patch_regen_from_recommendation_validation_completed", request, recommendation_exec_id, run_id=run_id, validation=validation, target_files=recommended_payload.get("target_files") or [], warnings=warnings, errors=errors)
            patch_request = None
            if validation.get("allowed"):
                patch_request = self.build_patch_regen_request(recommendation_result, request, recommendation_exec_id)
                patch_request_preview = patch_request.model_dump()
                if request.dry_run or not policy.allow_patch_regen_execution:
                    status = "dry_run"
                    self.emit_event("patch_regen_from_recommendation_dry_run", request, recommendation_exec_id, run_id=run_id, target_files=patch_request.target_files, warnings=warnings, errors=errors)
                else:
                    self.emit_event("patch_regen_from_recommendation_patch_regen_started", request, recommendation_exec_id, run_id=run_id, target_files=patch_request.target_files)
                    raw_result = self.patch_regen_service.regenerate(patch_request)
                    patch_regen_result = _dump(raw_result)
                    patch_regen_result_id = str(patch_regen_result.get("regen_run_id") or "")
                    patch_validation = self.validate_patch_regen_result(patch_regen_result, recommended_payload)
                    validation["patch_regen_result"] = patch_validation
                    warnings.extend(patch_validation.get("warnings") or [])
                    if patch_validation.get("errors"):
                        errors.extend(patch_validation["errors"])
                        status = "blocked"
                    else:
                        status = "patch_regen_created"
                    self.emit_event("patch_regen_from_recommendation_patch_regen_completed", request, recommendation_exec_id, run_id=run_id, patch_regen_result_id=patch_regen_result_id, patch_regen_status=patch_regen_result.get("status", ""), target_files=patch_request.target_files, warnings=warnings, errors=errors)
            else:
                status = "blocked"
                self.emit_event("patch_regen_from_recommendation_blocked", request, recommendation_exec_id, run_id=run_id, target_files=recommended_payload.get("target_files") or [], warnings=warnings, errors=errors)
        except json.JSONDecodeError:
            status = "failed_internal"
            errors.append("recommendation_json_parse_failed")
            self.emit_event("patch_regen_from_recommendation_failed_internal", request, recommendation_exec_id, run_id=run_id, warnings=warnings, errors=errors)
        except Exception as exc:
            status = "failed_internal"
            errors.append(str(exc) or "failed_internal")
            self.emit_event("patch_regen_from_recommendation_failed_internal", request, recommendation_exec_id, run_id=run_id, warnings=warnings, errors=errors)

        result = AtlasPatchRegenFromRecommendationResult(
            pool_id=request.pool_id,
            item_id=request.item_id,
            run_id=run_id,
            recommendation_run_id=request.recommendation_run_id,
            recommendation_exec_id=recommendation_exec_id,
            policy_id=policy.policy_id,
            patch_regen_policy_id=request.patch_regen_policy_id,
            status=status,
            patch_regen_result_id=patch_regen_result_id,
            patch_regen_result=patch_regen_result,
            recommendation_result=recommendation_result,
            recommended_payload=recommended_payload,
            validation=validation,
            warnings=warnings,
            errors=errors,
            metadata={
                "reviewer": request.reviewer,
                "reason": request.reason,
                "patch_regen_request_preview": patch_request_preview,
                "result_path": self.result_json_path(request.pool_id, recommendation_exec_id),
                "side_effects": self.side_effects(status == "patch_regen_created"),
            },
        )
        saved_json, _ = self.save_result(result)
        if status == "patch_regen_created":
            self.update_handoff_metadata(result)
            self.update_item_metadata(result)
            self.emit_event("patch_regen_from_recommendation_created", request, recommendation_exec_id, run_id=run_id, patch_regen_result_id=patch_regen_result_id, patch_regen_status=patch_regen_result.get("status", ""), target_files=recommended_payload.get("target_files") or [], warnings=warnings, errors=errors)
        self.emit_event("patch_regen_from_recommendation_result_saved", request, recommendation_exec_id, run_id=run_id, patch_regen_result_id=patch_regen_result_id, patch_regen_status=patch_regen_result.get("status", ""), target_files=recommended_payload.get("target_files") or [], warnings=warnings, errors=errors, metadata={"result_path": str(saved_json)})
        return result

    def resolve_policy(self, policy_id: str):
        return get_patch_regen_from_recommendation_policy(policy_id)

    def validate_request_ids(self, request):
        request.pool_id = validate_relative_path(request.pool_id)
        request.item_id = validate_relative_path(request.item_id)
        if request.run_id:
            request.run_id = validate_relative_path(request.run_id)
        request.recommendation_run_id = validate_relative_path(request.recommendation_run_id)
        if not request.recommendation_run_id.startswith("regenrec_"):
            raise ValueError("invalid_recommendation_run_id")

    def load_recommendation_result(self, pool_id: str, recommendation_run_id: str) -> dict:
        pool_id = validate_relative_path(pool_id)
        recommendation_run_id = validate_relative_path(recommendation_run_id)
        if not recommendation_run_id.startswith("regenrec_"):
            raise ValueError("invalid_recommendation_run_id")
        path = Path("ca_data") / "atlas" / "patch_regen_recommendations" / pool_id / f"{recommendation_run_id}.json"
        if not path.exists():
            return {"status": "missing", "errors": ["recommendation_not_found"]}
        return json.loads(path.read_text(encoding="utf-8"))

    def validate_recommendation_for_patch_regen(self, rec: dict, request, policy) -> dict:
        errors: list[str] = []
        warnings: list[str] = list(rec.get("warnings") or [])
        payload = rec.get("recommended_payload") or {}
        checks: list[str] = []
        if rec.get("status") == "missing":
            errors.append("recommendation_not_found")
        if rec.get("pool_id") != request.pool_id:
            errors.append("pool_id_mismatch")
        if rec.get("item_id") != request.item_id:
            errors.append("item_id_mismatch")
        if policy.require_recommendation_ready and rec.get("status") != "recommendation_ready":
            errors.append("recommendation_not_ready")
        if policy.require_recommended_payload and not payload:
            errors.append("recommended_payload_missing")
        metadata = rec.get("metadata") or {}
        side_effects = metadata.get("side_effects") or {}
        if metadata.get("auto_execute_patch_regen") is not False:
            errors.append("auto_execute_patch_regen_not_false")
        for key in ["patch_regeneration_executed", "safe_apply_executed", "verification_executed"]:
            if side_effects.get(key) is not False:
                errors.append(f"recommendation_side_effect_{key}")
        target_files = payload.get("target_files") or []
        safe_targets = []
        if not target_files:
            errors.append("target_files_missing")
        if len(target_files) > int(policy.max_target_files):
            errors.append("too_many_target_files")
        for target in target_files:
            try:
                safe_targets.append(validate_relative_path(target))
            except Exception:
                errors.append("target_files_unsafe")
        if len(set(safe_targets)) != len(safe_targets):
            warnings.append("duplicate_target_files")
        original_patch = str(payload.get("original_patch") or "")
        if not original_patch:
            errors.append("original_patch_missing")
        if len(original_patch) > int(policy.max_original_patch_chars):
            errors.append("original_patch_too_large")
        if not payload.get("failure_stop_suggestion"):
            errors.append("failure_stop_suggestion_missing")
        if not payload.get("verification_result"):
            errors.append("verification_result_missing")
        if policy.policy_id == "strict_patch_regen_from_recommendation_v1":
            if len(target_files) > 2:
                errors.append("strict_too_many_target_files")
            if rec.get("warnings"):
                errors.append("strict_recommendation_has_warnings")
        if (not request.allow_reexecute) and self.prior_execution_exists(rec, request):
            errors.append("prior_patch_regen_execution_exists")
        checks.extend(["ids", "status", "payload", "side_effects", "target_files", "original_patch", "failure_evidence", "prior_execution"])
        return {"allowed": not errors, "checks": checks, "errors": errors, "warnings": warnings, "target_files": safe_targets}

    def prior_execution_exists(self, rec: dict, request) -> bool:
        for entry in (rec.get("metadata") or {}).get("patch_regen_executions") or []:
            if entry.get("status") == "patch_regen_created":
                return True
        try:
            pool = self.storage.load_pool(request.pool_id)
            item = pool.get_item(request.item_id)
            md = dict(item.metadata or {}) if item else {}
            for entry in md.get("patch_regen_from_recommendation_results") or []:
                if entry.get("recommendation_run_id") == request.recommendation_run_id and entry.get("status") == "patch_regen_created":
                    return True
            handoff_id = str(rec.get("handoff_id") or "")
            for entry in md.get("safe_apply_handoffs") or []:
                if entry.get("handoff_id") == handoff_id:
                    for res in entry.get("patch_regen_from_recommendation_results") or []:
                        if res.get("recommendation_run_id") == request.recommendation_run_id and res.get("status") == "patch_regen_created":
                            return True
        except Exception:
            pass
        handoff = self.load_handoff(rec)
        for entry in (handoff.get("metadata") or {}).get("patch_regen_from_recommendation_results") or []:
            if entry.get("recommendation_run_id") == request.recommendation_run_id and entry.get("status") == "patch_regen_created":
                return True
        return False

    def build_patch_regen_request(self, rec: dict, request, recommendation_exec_id: str) -> AtlasPatchRegenRequest:
        payload = rec.get("recommended_payload") or {}
        target_files = [validate_relative_path(p) for p in payload.get("target_files") or []]
        changed_files = [validate_relative_path(p) for p in payload.get("changed_files") or []]
        return AtlasPatchRegenRequest(
            pool_id=request.pool_id,
            item_id=request.item_id,
            run_id=request.run_id or recommendation_exec_id,
            workspace_id=request.workspace_id,
            project_path=request.project_path or payload.get("project_path") or "",
            policy_id=request.patch_regen_policy_id,
            context_bundle_id=str(payload.get("context_bundle_id") or ""),
            retry_run_id=str(payload.get("retry_run_id") or ""),
            evaluator_result_id=str(payload.get("evaluator_result_id") or ""),
            verification_result=dict(payload.get("verification_result") or {}),
            bounded_retry_result=dict(payload.get("bounded_retry_result") or {}),
            failure_stop_suggestion=dict(payload.get("failure_stop_suggestion") or {}),
            original_patch=str(payload.get("original_patch") or ""),
            changed_files=changed_files,
            target_files=target_files,
            dry_run=False,
            metadata={
                "source": "patch_regen_from_recommendation",
                "recommendation_exec_id": recommendation_exec_id,
                "recommendation_run_id": request.recommendation_run_id,
                "supervised_retry_run_id": rec.get("supervised_retry_run_id") or payload.get("metadata", {}).get("supervised_retry_run_id", ""),
                "original_verification_run_id": rec.get("verification_run_id") or "",
                "safe_apply_execution_id": rec.get("safe_apply_execution_id") or "",
                "handoff_id": rec.get("handoff_id") or "",
                "manual_trigger": True,
                "reviewer": request.reviewer,
                "reason": request.reason,
                "auto_apply": False,
                "safe_apply_ready_expected": False,
            },
        )

    def validate_patch_regen_result(self, result: dict, recommended_payload: dict) -> dict:
        errors: list[str] = []
        warnings: list[str] = []
        candidate = result.get("candidate") or {}
        if result.get("status") not in ALLOWED_PATCH_REGEN_STATUSES:
            errors.append("patch_regen_status_not_allowed")
        if candidate.get("approval_required") is not True:
            errors.append("approval_required_not_true")
        if candidate.get("approval_status") != "pending":
            errors.append("approval_status_not_pending")
        if candidate.get("safe_apply_ready") is not False:
            errors.append("safe_apply_ready_not_false")
        side_effects = (result.get("metadata") or {}).get("side_effects") or {}
        for key in ["safe_apply_executed", "verification_executed", "bounded_retry_executed", "rollback_executed", "restore_executed", "debug_review_executed"]:
            if side_effects.get(key) is not False:
                errors.append(f"side_effect_{key}")
        allowed_targets = set(recommended_payload.get("target_files") or [])
        for target in candidate.get("target_files") or []:
            if target not in allowed_targets:
                errors.append("candidate_target_files_not_subset")
        return {"allowed": not errors, "errors": errors, "warnings": warnings}

    def update_recommendation_metadata(self):
        return None

    def update_handoff_metadata(self, result):
        handoff = self.load_handoff(result.recommendation_result)
        if not handoff:
            return
        md = dict(handoff.get("metadata") or {})
        entry = self.metadata_entry(result, include_targets=False)
        md.setdefault("patch_regen_from_recommendation_results", []).append(entry)
        md["last_patch_regen_from_recommendation_exec_id"] = result.recommendation_exec_id
        md["last_patch_regen_result_id"] = result.patch_regen_result_id
        md["patch_regen_executed_from_recommendation"] = result.status == "patch_regen_created"
        handoff["metadata"] = md
        path = self.handoff_path(result.recommendation_result)
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(handoff, ensure_ascii=False, indent=2), encoding="utf-8")

    def update_item_metadata(self, result):
        try:
            pool = self.storage.load_pool(result.pool_id)
            item = pool.get_item(result.item_id)
            if item is None:
                return
            md = dict(item.metadata or {})
            md.setdefault("patch_regen_from_recommendation_results", []).append(self.metadata_entry(result, include_targets=True))
            md["latest_patch_regen_from_recommendation_exec_id"] = result.recommendation_exec_id
            for rec_entry in md.get("patch_regen_recommendations") or []:
                if rec_entry.get("recommendation_run_id") == result.recommendation_run_id:
                    rec_entry["patch_regen_executed"] = True
                    rec_entry["patch_regen_exec_id"] = result.recommendation_exec_id
                    rec_entry["patch_regen_result_id"] = result.patch_regen_result_id
                    rec_entry["patch_regen_status"] = result.patch_regen_result.get("status", "")
            handoff_id = result.recommendation_result.get("handoff_id") or ""
            for handoff_entry in md.get("safe_apply_handoffs") or []:
                if handoff_entry.get("handoff_id") == handoff_id:
                    handoff_entry["patch_regen_executed_from_recommendation"] = True
                    handoff_entry["last_patch_regen_from_recommendation_exec_id"] = result.recommendation_exec_id
                    handoff_entry["last_patch_regen_result_id"] = result.patch_regen_result_id
                    handoff_entry.setdefault("patch_regen_from_recommendation_results", []).append(self.metadata_entry(result, include_targets=False))
            item.metadata = md
            self.storage.save_pool(pool)
        except Exception:
            return

    def metadata_entry(self, result, *, include_targets: bool) -> dict:
        entry = {
            "recommendation_exec_id": result.recommendation_exec_id,
            "recommendation_run_id": result.recommendation_run_id,
            "patch_regen_result_id": result.patch_regen_result_id,
            "patch_regen_status": result.patch_regen_result.get("status", ""),
            "status": result.status,
            "created_at": result.created_at,
            "result_path": self.result_json_path(result.pool_id, result.recommendation_exec_id),
        }
        if include_targets:
            entry["target_files"] = result.recommended_payload.get("target_files") or []
        else:
            entry["auto_approved"] = False
            entry["safe_apply_ready"] = False
        return entry

    def save_result(self, result):
        root = Path("ca_data") / "atlas" / "patch_regen_from_recommendations" / result.pool_id
        root.mkdir(parents=True, exist_ok=True)
        json_path = root / f"{result.recommendation_exec_id}.json"
        md_path = root / f"{result.recommendation_exec_id}.md"
        json_path.write_text(json.dumps(result.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
        md_path.write_text(self.markdown(result), encoding="utf-8")
        return json_path, md_path

    def markdown(self, result) -> str:
        rec = result.recommendation_result or {}
        payload = result.recommended_payload or {}
        candidate = (result.patch_regen_result or {}).get("candidate") or {}
        safety = self.side_effects(result.status == "patch_regen_created")
        return f"""# Patch Regen From Recommendation

## Summary
- recommendation_exec_id: {result.recommendation_exec_id}
- recommendation_run_id: {result.recommendation_run_id}
- pool_id: {result.pool_id}
- item_id: {result.item_id}
- status: {result.status}
- patch_regen_result_id: {result.patch_regen_result_id}
- patch_regen_status: {(result.patch_regen_result or {}).get('status', '')}
- reviewer: {(result.metadata or {}).get('reviewer', '')}
- reason: {(result.metadata or {}).get('reason', '')}

## Recommendation
- handoff_id: {rec.get('handoff_id', '')}
- safe_apply_execution_id: {rec.get('safe_apply_execution_id', '')}
- verification_run_id: {rec.get('verification_run_id', '')}
- supervised_retry_run_id: {rec.get('supervised_retry_run_id', '')}
- target_files: {payload.get('target_files') or []}
- retry_reason: {(rec.get('eligibility') or {}).get('retry_reason', '')}
- deterministic_failure_detected: {(rec.get('eligibility') or {}).get('deterministic_failure_detected', '')}

## Patch Regen Result
- status: {(result.patch_regen_result or {}).get('status', '')}
- proposal_id: {candidate.get('proposal_id', '')}
- candidate_status: {candidate.get('status', '')}
- approval_required: {candidate.get('approval_required', '')}
- approval_status: {candidate.get('approval_status', '')}
- safe_apply_ready: {candidate.get('safe_apply_ready', '')}

## Safety
- patch regeneration executed: {str(safety['patch_regeneration_executed']).lower()}
- safe_apply executed: false
- verification executed: false
- bounded retry executed: false
- rollback executed: false
- restore executed: false
- debug review executed: false
- auto approval executed: false

## Warnings
{self._md_list(result.warnings)}

## Errors
{self._md_list(result.errors)}
"""

    def emit_event(self, event_type, request, recommendation_exec_id, *, run_id="", patch_regen_result_id="", patch_regen_status="", target_files=None, recommendation_result=None, validation=None, warnings=None, errors=None, metadata=None):
        if not self.journal:
            return
        try:
            rec = recommendation_result or {}
            meta = {
                "recommendation_exec_id": recommendation_exec_id,
                "recommendation_run_id": request.recommendation_run_id,
                "patch_regen_result_id": patch_regen_result_id,
                "pool_id": request.pool_id,
                "item_id": request.item_id,
                "run_id": run_id or request.run_id or recommendation_exec_id,
                "handoff_id": rec.get("handoff_id", ""),
                "safe_apply_execution_id": rec.get("safe_apply_execution_id", ""),
                "verification_run_id": rec.get("verification_run_id", ""),
                "supervised_retry_run_id": rec.get("supervised_retry_run_id", ""),
                "status": event_type,
                "patch_regen_status": patch_regen_status,
                "target_files": target_files or [],
                "warning_count": len(warnings or []),
                "error_count": len(errors or []),
                "patch_regeneration_executed": event_type in {"patch_regen_from_recommendation_patch_regen_completed", "patch_regen_from_recommendation_created"},
                "safe_apply_executed": False,
                "verification_executed": False,
                "bounded_retry_executed": False,
                "rollback_executed": False,
                "restore_executed": False,
                "debug_review_executed": False,
                "auto_approval_executed": False,
                **(metadata or {}),
            }
            event = {"event_id": f"atlas_pipeline_event_{uuid4().hex}", "run_id": run_id or request.run_id or recommendation_exec_id, "event_type": "item_completed", "item_id": request.item_id, "message": event_type, "created_at": datetime.now(timezone.utc).isoformat(), "metadata": meta}
            self.journal.append_event(request.pool_id, run_id or request.run_id or recommendation_exec_id, event)
        except Exception:
            pass

    def load_handoff(self, rec: dict) -> dict:
        path = self.handoff_path(rec)
        if path and path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return dict(rec.get("handoff") or {})

    def handoff_path(self, rec: dict) -> Path | None:
        handoff_id = str(rec.get("handoff_id") or "")
        pool_id = str(rec.get("pool_id") or "")
        if not handoff_id or not handoff_id.startswith("handoff_") or not pool_id:
            return None
        return Path("ca_data") / "atlas" / "safe_apply_handoffs" / validate_relative_path(pool_id) / f"{validate_relative_path(handoff_id)}.json"

    def result_json_path(self, pool_id: str, recommendation_exec_id: str) -> str:
        return f"ca_data/atlas/patch_regen_from_recommendations/{pool_id}/{recommendation_exec_id}.json"

    def side_effects(self, patch_regeneration_executed: bool) -> dict:
        return {
            "patch_regeneration_executed": patch_regeneration_executed,
            "safe_apply_executed": False,
            "verification_executed": False,
            "bounded_retry_executed": False,
            "rollback_executed": False,
            "restore_executed": False,
            "debug_review_executed": False,
            "auto_approval_executed": False,
        }

    @staticmethod
    def _md_list(values) -> str:
        return "\n".join(f"- {v}" for v in values) if values else "- none"
