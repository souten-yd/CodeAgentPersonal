from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agent.implementation_schema import ImplementationRun, ImplementationStepResult
from agent.patch_generator import PatchGenerator
from agent.llm_patch_generator import generate_replace_block_patch
from agent.patch_safety import PatchSafetyChecker
from agent.patch_schema import PatchApplyResult, PatchProposal
from agent.patch_approval_manager import PatchApprovalManager
from agent.patch_storage import PatchStorage
from agent.plan_storage import PlanStorage
from agent.run_storage import RunStorage
from agent.verification_runner import VerificationRunner


class ImplementationExecutor:
    BLOCKED_DIR_NAMES = {".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build"}

    def __init__(self, storage: PlanStorage, run_storage: RunStorage, llm_patch_fn=None) -> None:
        self.storage = storage
        self.run_storage = run_storage
        self.patch_storage = PatchStorage(run_storage.base_dir)
        self.patch_generator = PatchGenerator()
        self.patch_approval_manager = PatchApprovalManager(self.patch_storage)
        self.patch_safety = PatchSafetyChecker()
        self.verification_runner = VerificationRunner()
        self.llm_patch_fn = llm_patch_fn

    def execute(self, plan_id: str, execution_mode: str = "dry_run", project_path: str = "", allow_update: bool = False, allow_create: bool = False, allow_delete: bool = False, allow_run_command: bool = False, user_comment: str = "", apply_patches: bool = False, preview_only: bool = True, max_patch_bytes: int = 20000, patch_generation_mode: str = "append") -> dict:
        if execution_mode not in {"dry_run", "safe_apply"}:
            raise ValueError("execution_mode must be dry_run or safe_apply")

        plan = self.storage.load_plan(plan_id)
        self._validate_plan_gate(plan)
        approval = self.storage.find_latest_approval_for_plan(plan_id)
        if not approval:
            raise ValueError("approval is required")
        if not bool(approval.get("execution_ready", False)) or not bool(approval.get("approved_for_execution", False)):
            raise ValueError("approval is not execution ready")

        run_id = f"run_{uuid4().hex[:12]}"
        now = self._now()
        resolved_project_path, project_path_source, path_warnings = self._resolve_execution_project_path(plan, project_path)
        steps = plan.get("implementation_steps") or []
        run = ImplementationRun(run_id=run_id, plan_id=plan_id, requirement_id=str(plan.get("requirement_id", "")), approval_id=str(approval.get("approval_id", "")), created_at=now, updated_at=now, status="running", execution_mode=execution_mode, project_path=resolved_project_path, total_steps=len(steps), warnings=[], errors=[], summary="", no_destructive_actions=True)
        run.warnings.extend(path_warnings)

        if execution_mode == "safe_apply":
            self._validate_project_path_for_safe_apply(resolved_project_path, project_path_source)
        elif not resolved_project_path:
            run.warnings.append("project_path was not resolved; dry_run only")

        logs = [f"[{now}] start run_id={run_id} plan_id={plan_id} mode={execution_mode} comment={user_comment}"]
        if allow_delete:
            run.warnings.append("allow_delete was ignored in Phase 7. delete remains blocked.")
        if allow_run_command:
            run.warnings.append("allow_run_command was ignored in Phase 7. run_command remains blocked.")

        self.run_storage.save_run(run)
        for idx, raw in enumerate(steps, start=1):
            step = ImplementationStepResult(step_id=str(raw.get("step_id", f"step_{idx}")), title=str(raw.get("title", f"Step {idx}")), action_type=str(raw.get("action_type", "inspect")), risk_level=str(raw.get("risk_level", "low")), target_files=[str(x) for x in (raw.get("target_files") or [])], status="pending")
            run.step_results.append(step)
            self._run_step(run, step, execution_mode=execution_mode, plan=plan, project_path=Path(resolved_project_path) if resolved_project_path else None, allow_update=allow_update, allow_create=allow_create, logs=logs, apply_patches=apply_patches, preview_only=preview_only, max_patch_bytes=max_patch_bytes, patch_generation_mode=patch_generation_mode)
            run.updated_at = self._now()

        self._finalize_run(run)
        logs.append(f"[{self._now()}] finished status={run.status} completed={run.completed_steps} skipped={run.skipped_steps} blocked={run.blocked_steps} failed={run.failed_steps}")
        self.run_storage.save_steps(run)
        self.run_storage.save_log(run.run_id, logs)
        self.run_storage.save_report(run)
        self.run_storage.save_run(run)
        return {"run_id": run.run_id, "plan_id": run.plan_id, "status": run.status, "execution_mode": run.execution_mode, "summary": run.summary, "run": run.model_dump(), "message": "Execution completed with Phase 7 safety restrictions."}


    def _validate_plan_gate(self, plan: dict) -> None:
        if str(plan.get("status", "")) != "execution_ready":
            raise ValueError("plan must be execution_ready")
        review = plan.get("review_result")
        if not isinstance(review, dict):
            raise ValueError("review_result is required")
        if str(review.get("recommended_next_action", "")) == "reject_plan":
            raise ValueError("plan review rejected execution")

    def _validate_project_path_for_safe_apply(self, resolved_project_path: str, source: str) -> None:
        resolved_dir = Path(resolved_project_path)
        if not resolved_project_path or not resolved_dir.exists() or not resolved_dir.is_dir():
            raise ValueError("safe_apply requires an explicit or stored resolved_project_path")
        cwd = Path.cwd().resolve()
        repo_root = Path(__file__).resolve().parent.parent
        if resolved_dir.resolve() in {cwd, repo_root} or str(resolved_dir.resolve()) == "/app":
            raise ValueError("safe_apply project_path is too broad; specify concrete project directory")

    def _run_step(self, run: ImplementationRun, step: ImplementationStepResult, execution_mode: str, plan: dict, project_path: Path | None, allow_update: bool, allow_create: bool, logs: list[str], apply_patches: bool, preview_only: bool, max_patch_bytes: int, patch_generation_mode: str = "append") -> None:
        step.started_at = self._now(); step.status = "running"
        action = step.action_type; risk = step.risk_level.lower(); step.log.append(f"start action={action} risk={risk}")
        try:
            if risk == "high": return self._block(step, run, "high risk step is blocked in Phase 7")
            if action in {"delete", "run_command"}: return self._block(step, run, f"{action} is blocked in Phase 7")
            if execution_mode == "dry_run":
                if action == "update" and project_path is not None and allow_update:
                    self._safe_update(step, project_path, run.run_id, run.plan_id, plan, apply_patches=False, preview_only=True, max_patch_bytes=max_patch_bytes, patch_generation_mode=patch_generation_mode)
                    step.status = "skipped"; step.skipped_reason = "dry_run: execution planned only"; step.message = "patch preview generated during dry_run; file unchanged"; run.skipped_steps += 1; return
                step.status = "skipped"; step.skipped_reason = "dry_run: execution planned only"; step.message = "Recorded planned action. No changes made."; run.skipped_steps += 1; return
            if action == "inspect":
                if project_path is None: step.status="skipped"; step.skipped_reason="project_path unresolved"; step.message="inspect skipped: project_path unresolved"; run.skipped_steps +=1; return
                self._inspect(step, project_path); self._tally_step_status(run, step); return
            if action == "create":
                if not allow_create: return self._block(step, run, "allow_create is false")
                if project_path is None: return self._block(step, run, "project_path unresolved")
                self._create_stub(step, project_path); self._tally_step_status(run, step); return
            if action == "update":
                if not allow_update: return self._block(step, run, "allow_update is false")
                if project_path is None: return self._block(step, run, "project_path unresolved")
                self._safe_update(step, project_path, run.run_id, run.plan_id, plan, apply_patches=apply_patches, preview_only=preview_only, max_patch_bytes=max_patch_bytes, patch_generation_mode=patch_generation_mode); self._tally_step_status(run, step); return
            step.status = "skipped"; step.skipped_reason = f"unsupported action_type={action}"; step.message = "Skipped unsupported action"; run.skipped_steps += 1
        except Exception as exc:
            step.status = "failed"; step.error = str(exc); step.message = f"failed: {exc}"; run.failed_steps += 1; run.errors.append(f"{step.step_id}: {exc}")
        finally:
            step.finished_at = self._now(); logs.append(f"[{step.finished_at}] step_id={step.step_id} status={step.status} action={step.action_type} message={step.message or step.skipped_reason or step.error}")

    def _inspect(self, step: ImplementationStepResult, project_path: Path) -> None:
        previews=[]
        for tf in step.target_files:
            resolved=self._resolve_target(project_path, tf)
            if resolved is None: previews.append(f"{tf}: blocked(path restriction)"); continue
            if not resolved.exists(): previews.append(f"{tf}: missing"); continue
            size=resolved.stat().st_size
            if self._is_binary(resolved): previews.append(f"{tf}: binary(size={size}) blocked"); continue
            previews.append(f"{tf}: exists size={size} preview={resolved.read_text(encoding='utf-8', errors='ignore')[:240]!r}")
        step.status="completed"; step.message="inspect completed"; step.log.extend(previews)

    def _create_stub(self, step: ImplementationStepResult, project_path: Path) -> None:
        if not step.target_files: raise ValueError("create step requires target_files")
        target=self._resolve_target(project_path, step.target_files[0])
        if target is None: self._block(step,None,"target path is outside project or blocked"); return
        if target.exists(): self._block(step,None,"target already exists; overwrite is blocked"); return
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("\n".join(["# TODO generated by CodeAgent Phase 6",f"# Step: {step.title}",""]), encoding="utf-8")
        step.changed_files.append(str(target)); step.status="completed"; step.message="created safe stub file"

    def _safe_update(self, step: ImplementationStepResult, project_path: Path, run_id: str, plan_id: str, plan: dict, apply_patches: bool, preview_only: bool, max_patch_bytes: int, patch_generation_mode: str = "append") -> None:
        if not step.target_files: raise ValueError("update step requires target_files")
        if len(step.target_files) != 1: self._block(step,None,"Phase 7 supports only single target_file for update patch MVP"); return
        target=self._resolve_target(project_path, step.target_files[0])
        if target is None: self._block(step,None,"target path is outside project or blocked"); return
        if not target.exists(): raise ValueError("target file does not exist")
        if self._is_binary(target): raise ValueError("binary file update is blocked")
        proposal = None
        mode = (patch_generation_mode or "append").strip().lower()
        try:
            if mode in {"llm_replace_block", "auto"}:
                content = target.read_text(encoding="utf-8")
                proposal = generate_replace_block_patch(
                    run_id,
                    plan_id,
                    step.step_id,
                    step.title,
                    str(plan.get("description", "")),
                    step.risk_level,
                    target,
                    content,
                    llm_fn=self.llm_patch_fn,
                    context={
                        "plan_id": plan_id,
                        "requirement_id": plan.get("requirement_id", ""),
                        "user_goal": plan.get("user_goal", ""),
                        "requirement_summary": plan.get("requirement_summary", ""),
                        "step": step.model_dump() if hasattr(step, "model_dump") else {},
                    },
                )
                if mode == "auto" and not proposal.apply_allowed:
                    fallback_reason = proposal.can_apply_reason or "llm_invalid"
                    proposal = self.patch_generator.generate_append_patch(run_id, plan_id, step.step_id, step.title, str(plan.get('description','')), step.risk_level, target)
                    proposal.metadata = {**(proposal.metadata or {}), "fallback_from": "llm_replace_block", "fallback_reason": fallback_reason}
            else:
                proposal=self.patch_generator.generate_append_patch(run_id, plan_id, step.step_id, step.title, str(plan.get('description','')), step.risk_level, target)
        except ValueError as exc:
            self._block(step, None, f"patch generation blocked: {exc}")
            return
        self.patch_safety.max_patch_bytes = max_patch_bytes
        allowed,warns=self.patch_safety.evaluate(proposal, project_path, step.risk_level)
        proposal.apply_allowed=allowed; proposal.safety_warnings=warns
        self.patch_storage.save_patch_proposal(proposal)
        step.patch_id = proposal.patch_id
        if preview_only:
            step.status = "completed"
            step.message = "patch preview generated; file unchanged"
            return
        if not apply_patches:
            step.status = "completed"
            step.message = "patch preview generated; file unchanged"
            return
        step.status = "completed"
        step.message = "patch preview generated; apply requires patch approval API in Phase 8"
        return


    def apply_patch(self, run_id: str, patch_id: str) -> dict:
        patch = self.patch_storage.load_patch(run_id, patch_id)
        approval = self.patch_approval_manager.require_approved_for_apply(run_id, patch_id)
        if not bool(patch.get("apply_allowed", False)):
            raise ValueError("patch apply is not allowed")
        if bool(patch.get("applied", False)):
            raise ValueError("duplicate apply is rejected")
        patch_type = str(patch.get("patch_type", "append"))
        proposed = str(patch.get("proposed_content", ""))
        if patch_type == "append":
            if not proposed.strip():
                raise ValueError("proposed_content is empty")
            if "CodeAgent Phase 7 patch note" not in proposed:
                raise ValueError("required patch marker is missing")
        elif patch_type == "replace_block":
            if not str(patch.get("original_block", "")).strip() or not str(patch.get("replacement_block", "")).strip():
                raise ValueError("original/replacement block is empty")
        else:
            raise ValueError("unsupported patch_type")

        run_payload = self.run_storage.load_run(run_id)
        project_path = str(run_payload.get("project_path", "")).strip()
        if not project_path:
            raise ValueError("run project_path is empty")
        project = Path(project_path)
        target = self._resolve_target(project, str(patch.get("target_file", "")))
        if target is None:
            raise ValueError("target file is outside project or blocked")
        if not target.exists():
            raise ValueError("target file does not exist")
        if self._is_binary(target):
            raise ValueError("binary target apply is rejected")

        before = target.read_text(encoding="utf-8")
        if patch_type == "replace_block":
            original_block = str(patch.get("original_block", ""))
            match_count = before.count(original_block)
            if match_count == 0:
                self.patch_storage.update_patch_payload(run_id, patch_id, {"apply_allowed": False, "safety_warnings": list(set(list(patch.get("safety_warnings") or []) + ["replace_block original_block no longer exists"]))})
                raise ValueError("replace_block original_block no longer exists")
            if match_count > 1:
                self.patch_storage.update_patch_payload(run_id, patch_id, {"apply_allowed": False, "safety_warnings": list(set(list(patch.get("safety_warnings") or []) + ["replace_block original_block is ambiguous"]))})
                raise ValueError("replace_block original_block is ambiguous")

        patch_model = PatchProposal(**patch)
        allowed, warnings = self.patch_safety.evaluate(patch_model, project, str(patch.get("risk_level", "low")))
        safety_updates = {"safety_warnings": warnings}
        if not allowed:
            safety_updates["apply_allowed"] = False
            self.patch_storage.update_patch_payload(run_id, patch_id, safety_updates)
            raise ValueError(f"patch safety check failed before apply: {'; '.join(warnings) if warnings else 'unknown reason'}")
        if warnings != list(patch.get("safety_warnings") or []):
            self.patch_storage.update_patch_payload(run_id, patch_id, safety_updates)

        backup = self._backup_path_for(target, patch_id)
        if patch_type == "append":
            backup.write_text(before, encoding="utf-8")
            with target.open("a", encoding="utf-8") as f:
                f.write(proposed)
        else:
            replacement_block = str(patch.get("replacement_block", ""))
            backup.write_text(before, encoding="utf-8")
            target.write_text(before.replace(original_block, replacement_block, 1), encoding="utf-8")

        vr = self.verification_runner.run(
            run_id=run_id,
            plan_id=str(patch.get("plan_id", "")),
            patch_id=patch_id,
            project_path=project,
            target_file=target,
            replacement_hint=str(patch.get("replacement_block", "")),
        )
        self.patch_storage.save_verification_result(vr)

        ar = PatchApplyResult(
            patch_id=patch_id,
            applied=True,
            target_file=str(target),
            backup_path=str(backup),
            changed_bytes=len((proposed if patch_type == "append" else str(patch.get("replacement_block", ""))).encode("utf-8")),
            message=f"patch applied; verification={vr.status}",
            verification_result_id=vr.verification_id,
            verification_status=vr.status,
            verification_summary=vr.summary,
        )
        self.patch_storage.save_apply_result(run_id, ar)
        approval = self.patch_approval_manager.mark_applied(run_id, patch_id, ar.model_dump(), vr.verification_id, vr.status, vr.summary)
        self.patch_storage.update_patch_payload(
            run_id,
            patch_id,
            {
                "applied": True,
                "status": "applied",
                "verification_id": vr.verification_id,
                "approval_status": "applied",
                "patch_approval_id": approval.patch_approval_id,
                "verification_status": vr.status,
                "verification_summary": vr.summary,
            },
        )
        return {
            "run_id": run_id,
            "patch_id": patch_id,
            "applied": True,
            "apply_result": ar.model_dump(),
            "verification_result": vr.model_dump(),
            "approval": approval.model_dump(),
        }


    def generate_reproposal(self, run_id: str, patch_id: str, reason: str = "verification_failed", user_comment: str = "") -> dict:
        patch = self.patch_storage.load_patch(run_id, patch_id)
        if str(patch.get("verification_status", "")) != "failed":
            raise ValueError("reproposal requires verification_status=failed")
        if str(patch.get("patch_type", "")) != "replace_block":
            raise ValueError("reproposal supports replace_block only")
        run_payload = self.run_storage.load_run(run_id)
        project = Path(str(run_payload.get("project_path", "")))
        target = self._resolve_target(project, str(patch.get("target_file", "")))
        if target is None or not target.exists():
            raise ValueError("target file is unavailable")
        content = target.read_text(encoding="utf-8")
        proposal = generate_replace_block_patch(
            run_id,
            str(patch.get("plan_id", "")),
            str(patch.get("step_id", "")),
            f"Reproposal: {patch.get('step_id','')}",
            user_comment or reason,
            str(patch.get("risk_level", "low")),
            target,
            content,
            llm_fn=self.llm_patch_fn,
            context={"reproposal_of_patch_id": patch_id, "reason": reason},
        )
        proposal.reproposal_of_patch_id = patch_id
        proposal.reproposal_reason = reason
        proposal.parent_verification_id = str(patch.get("verification_id", ""))
        proposal.status = "proposed"
        proposal.applied = False
        self.patch_storage.save_patch_proposal(proposal)
        return {"run_id": run_id, "patch_id": proposal.patch_id, "reproposal": proposal.model_dump()}

    def _backup_path_for(self, target: Path, patch_id: str = "") -> Path:
        safe_patch_id = patch_id or "unknown"
        return target.with_suffix(target.suffix + f".bak.phase8.{safe_patch_id}")

    def _resolve_target(self, project_path: Path, target_file: str) -> Path | None:
        if not target_file or ".." in Path(target_file).parts: return None
        target=Path(target_file)
        resolved=(project_path/target).resolve() if not target.is_absolute() else target.resolve(); project_resolved=project_path.resolve()
        if project_resolved not in resolved.parents and resolved != project_resolved: return None
        if any(part in self.BLOCKED_DIR_NAMES for part in resolved.parts): return None
        if "ca_data" in resolved.parts: return None
        return resolved

    def _resolve_execution_project_path(self, plan: dict, requested_project_path: str) -> tuple[str, str, list[str]]:
        warnings=[]; candidates=[]; req=str(requested_project_path or "").strip()
        if req:
            if req in {".", "./"}:
                warnings.append("request.project_path ignored: dot path is invalid for resolution fallback")
            else:
                candidates.append(("request.project_path", req))
        elif str(requested_project_path or "") != "":
            warnings.append("request.project_path ignored: blank input")
        plan_resolved=str(plan.get("resolved_project_path","")).strip()
        if plan_resolved: candidates.append(("plan.resolved_project_path", plan_resolved))
        plan_path=str(plan.get("project_path","")).strip()
        if plan_path: candidates.append(("plan.project_path", plan_path))
        rid=str(plan.get("requirement_id",""))
        if rid:
            try:
                requirement=self.storage.load_requirement(rid)
                for k in ["resolved_project_path","project_path"]:
                    v=str(requirement.get(k,"")).strip()
                    if v: candidates.append((f"requirement.{k}", v))
            except Exception as exc:
                warnings.append(f"requirement load warning: {exc}")
        for source,raw in candidates:
            try:
                resolved=Path(raw).expanduser().resolve()
                if str(resolved) == str(Path('.').resolve()):
                    warnings.append(f"project_path from {source} resolved to current directory")
                    continue
                return str(resolved), source, warnings
            except Exception as exc:
                warnings.append(f"invalid project_path from {source}: {exc}")
        return "", "", warnings

    def _tally_step_status(self, run: ImplementationRun, step: ImplementationStepResult) -> None:
        if step.status == "completed": run.completed_steps += 1
        elif step.status == "blocked": run.blocked_steps += 1; run.warnings.append(f"{step.step_id}: {step.message}")
        elif step.status == "skipped": run.skipped_steps += 1
        elif step.status == "failed": run.failed_steps += 1; run.errors.append(f"{step.step_id}: {step.error}")

    def _is_binary(self, path: Path) -> bool:
        return b"\x00" in path.read_bytes()[:1024]

    def _block(self, step: ImplementationStepResult, run: ImplementationRun | None, reason: str) -> None:
        step.status="blocked"; step.skipped_reason=reason; step.message=reason
        if run is not None: run.blocked_steps += 1; run.warnings.append(f"{step.step_id}: {reason}")

    def _finalize_run(self, run: ImplementationRun) -> None:
        run.status = "failed" if run.failed_steps > 0 else ("completed_with_skips" if run.blocked_steps > 0 or run.skipped_steps > 0 else "completed")
        run.summary = f"Run {run.run_id}: completed={run.completed_steps}, skipped={run.skipped_steps}, blocked={run.blocked_steps}, failed={run.failed_steps}."
        run.updated_at = self._now()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
