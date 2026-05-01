from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agent.implementation_schema import ImplementationRun, ImplementationStepResult
from agent.plan_storage import PlanStorage
from agent.run_storage import RunStorage


class ImplementationExecutor:
    BLOCKED_DIR_NAMES = {".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build"}

    def __init__(self, storage: PlanStorage, run_storage: RunStorage) -> None:
        self.storage = storage
        self.run_storage = run_storage

    def execute(
        self,
        plan_id: str,
        execution_mode: str = "dry_run",
        project_path: str = "",
        allow_update: bool = False,
        allow_create: bool = False,
        allow_delete: bool = False,
        allow_run_command: bool = False,
        user_comment: str = "",
    ) -> dict:
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
        resolved_project_path, path_warnings = self._resolve_execution_project_path(plan, project_path)
        steps = plan.get("implementation_steps") or []
        run = ImplementationRun(
            run_id=run_id,
            plan_id=plan_id,
            requirement_id=str(plan.get("requirement_id", "")),
            approval_id=str(approval.get("approval_id", "")),
            created_at=now,
            updated_at=now,
            status="running",
            execution_mode=execution_mode,
            project_path=resolved_project_path,
            total_steps=len(steps),
            warnings=[],
            errors=[],
            summary="",
            no_destructive_actions=True,
        )
        run.warnings.extend(path_warnings)
        if execution_mode == "safe_apply":
            if not resolved_project_path:
                raise ValueError("safe_apply requires an explicit or stored resolved_project_path")
            resolved_dir = Path(resolved_project_path)
            if not resolved_dir.exists() or not resolved_dir.is_dir():
                raise ValueError("safe_apply requires an explicit or stored resolved_project_path")
        elif not resolved_project_path:
            run.warnings.append("project_path was not resolved; dry_run only")
        logs = [f"[{now}] start run_id={run_id} plan_id={plan_id} mode={execution_mode} comment={user_comment}"]
        if allow_delete:
            run.warnings.append("allow_delete was ignored in Phase 6. delete remains blocked.")
        if allow_run_command:
            run.warnings.append("allow_run_command was ignored in Phase 6. run_command remains blocked.")

        self.run_storage.save_run(run)
        for idx, raw in enumerate(steps, start=1):
            step = ImplementationStepResult(
                step_id=str(raw.get("step_id", f"step_{idx}")),
                title=str(raw.get("title", f"Step {idx}")),
                action_type=str(raw.get("action_type", "inspect")),
                risk_level=str(raw.get("risk_level", "low")),
                target_files=[str(x) for x in (raw.get("target_files") or [])],
                status="pending",
            )
            run.step_results.append(step)
            self._run_step(
                run,
                step,
                execution_mode=execution_mode,
                plan=plan,
                project_path=Path(resolved_project_path) if resolved_project_path else None,
                allow_update=allow_update,
                allow_create=allow_create,
                logs=logs,
            )
            run.updated_at = self._now()

        self._finalize_run(run)
        logs.append(f"[{self._now()}] finished status={run.status} completed={run.completed_steps} skipped={run.skipped_steps} blocked={run.blocked_steps} failed={run.failed_steps}")
        self.run_storage.save_steps(run)
        self.run_storage.save_log(run.run_id, logs)
        self.run_storage.save_report(run)
        self.run_storage.save_run(run)

        message = "Execution dry-run completed. No file changes were made." if execution_mode == "dry_run" else "Execution safe-apply completed with Phase 6 safety restrictions."
        return {
            "run_id": run.run_id,
            "plan_id": run.plan_id,
            "status": run.status,
            "execution_mode": run.execution_mode,
            "summary": run.summary,
            "run": run.model_dump(),
            "message": message,
        }

    def _validate_plan_gate(self, plan: dict) -> None:
        if str(plan.get("status", "")) != "execution_ready":
            raise ValueError("plan must be execution_ready")
        review = plan.get("review_result")
        if not isinstance(review, dict):
            raise ValueError("review_result is required")
        if str(review.get("recommended_next_action", "")) == "reject_plan":
            raise ValueError("plan review rejected execution")

    def _run_step(self, run: ImplementationRun, step: ImplementationStepResult, execution_mode: str, plan: dict, project_path: Path | None, allow_update: bool, allow_create: bool, logs: list[str]) -> None:
        step.started_at = self._now()
        step.status = "running"
        action = step.action_type
        risk = step.risk_level.lower()
        step.log.append(f"start action={action} risk={risk}")

        try:
            if risk == "high":
                return self._block(step, run, "high risk step is blocked in Phase 6")
            if action in {"delete", "run_command"}:
                return self._block(step, run, f"{action} is blocked in Phase 6")
            if execution_mode == "dry_run":
                step.status = "skipped"
                step.skipped_reason = "dry_run: execution planned only"
                step.message = "Recorded planned action. No changes made."
                run.skipped_steps += 1
                return

            if action == "inspect":
                if project_path is None:
                    step.status = "skipped"
                    step.skipped_reason = "project_path unresolved"
                    step.message = "inspect skipped: project_path unresolved"
                    run.skipped_steps += 1
                    return
                self._inspect(step, project_path)
                self._tally_step_status(run, step)
                return
            if action == "create":
                if not allow_create:
                    return self._block(step, run, "allow_create is false")
                if project_path is None:
                    return self._block(step, run, "project_path unresolved")
                self._create_stub(step, project_path)
                self._tally_step_status(run, step)
                return
            if action == "update":
                if not allow_update:
                    return self._block(step, run, "allow_update is false")
                if project_path is None:
                    return self._block(step, run, "project_path unresolved")
                self._safe_update(step, project_path)
                self._tally_step_status(run, step)
                return

            step.status = "skipped"
            step.skipped_reason = f"unsupported action_type={action}"
            step.message = "Skipped unsupported action"
            run.skipped_steps += 1
        except Exception as exc:
            step.status = "failed"
            step.error = str(exc)
            step.message = f"failed: {exc}"
            run.failed_steps += 1
            run.errors.append(f"{step.step_id}: {exc}")
        finally:
            step.finished_at = self._now()
            logs.append(f"[{step.finished_at}] step_id={step.step_id} status={step.status} action={step.action_type} message={step.message or step.skipped_reason or step.error}")

    def _inspect(self, step: ImplementationStepResult, project_path: Path) -> None:
        previews: list[str] = []
        for tf in step.target_files:
            resolved = self._resolve_target(project_path, tf)
            if resolved is None:
                previews.append(f"{tf}: blocked(path restriction)")
                continue
            if not resolved.exists():
                previews.append(f"{tf}: missing")
                continue
            size = resolved.stat().st_size
            if self._is_binary(resolved):
                previews.append(f"{tf}: binary(size={size}) blocked")
                continue
            text = resolved.read_text(encoding="utf-8", errors="ignore")[:240]
            previews.append(f"{tf}: exists size={size} preview={text!r}")
        step.status = "completed"
        step.message = "inspect completed"
        step.log.extend(previews)

    def _create_stub(self, step: ImplementationStepResult, project_path: Path) -> None:
        if not step.target_files:
            raise ValueError("create step requires target_files")
        target = self._resolve_target(project_path, step.target_files[0])
        if target is None:
            self._block(step, None, "target path is outside project or blocked")
            return
        if target.exists():
            self._block(step, None, "target already exists; overwrite is blocked")
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        content = "\n".join([
            "# TODO generated by CodeAgent Phase 6",
            f"# Step: {step.title}",
            "",
        ])
        target.write_text(content, encoding="utf-8")
        step.changed_files.append(str(target))
        step.status = "completed"
        step.message = "created safe stub file"

    def _safe_update(self, step: ImplementationStepResult, project_path: Path) -> None:
        if not step.target_files:
            raise ValueError("update step requires target_files")
        target = self._resolve_target(project_path, step.target_files[0])
        if target is None:
            self._block(step, None, "target path is outside project or blocked")
            return
        if not target.exists():
            raise ValueError("target file does not exist")
        if self._is_binary(target):
            raise ValueError("binary file update is blocked")
        with target.open("a", encoding="utf-8") as f:
            f.write(f"\n# TODO safe update note (Phase 6): {step.title}\n")
        step.changed_files.append(str(target))
        step.status = "completed"
        step.message = "appended safe update note"

    def _resolve_target(self, project_path: Path, target_file: str) -> Path | None:
        if not target_file or ".." in Path(target_file).parts:
            return None
        target = Path(target_file)
        resolved = (project_path / target).resolve() if not target.is_absolute() else target.resolve()
        project_resolved = project_path.resolve()
        if project_resolved not in resolved.parents and resolved != project_resolved:
            return None
        if any(part in self.BLOCKED_DIR_NAMES for part in resolved.parts):
            return None
        if "ca_data" in resolved.parts:
            return None
        return resolved

    def _resolve_execution_project_path(self, plan: dict, requested_project_path: str) -> tuple[str, list[str]]:
        warnings: list[str] = []
        candidates: list[tuple[str, str]] = []
        req = str(requested_project_path or "").strip()
        if req:
            candidates.append(("request.project_path", req))
        plan_resolved = str(plan.get("resolved_project_path", "")).strip()
        if plan_resolved:
            candidates.append(("plan.resolved_project_path", plan_resolved))
        plan_path = str(plan.get("project_path", "")).strip()
        if plan_path:
            candidates.append(("plan.project_path", plan_path))
        requirement_id = str(plan.get("requirement_id", "")).strip()
        if requirement_id:
            try:
                requirement = self.storage.load_requirement(requirement_id)
                req_resolved = str(requirement.get("resolved_project_path", "")).strip()
                if req_resolved:
                    candidates.append(("requirement.resolved_project_path", req_resolved))
                req_path = str(requirement.get("project_path", "")).strip()
                if req_path:
                    candidates.append(("requirement.project_path", req_path))
            except Exception as exc:
                warnings.append(f"requirement load warning: {exc}")

        for source, raw in candidates:
            try:
                resolved = Path(raw).expanduser().resolve()
                if str(resolved) == str(Path(".").resolve()) and source != "request.project_path":
                    continue
                return str(resolved), warnings
            except Exception as exc:
                warnings.append(f"invalid project_path from {source}: {exc}")
        return "", warnings

    def _tally_step_status(self, run: ImplementationRun, step: ImplementationStepResult) -> None:
        if step.status == "completed":
            run.completed_steps += 1
        elif step.status == "blocked":
            run.blocked_steps += 1
            if step.message:
                run.warnings.append(f"{step.step_id}: {step.message}")
        elif step.status == "skipped":
            run.skipped_steps += 1
        elif step.status == "failed":
            run.failed_steps += 1
            if step.error:
                run.errors.append(f"{step.step_id}: {step.error}")

    def _is_binary(self, path: Path) -> bool:
        data = path.read_bytes()[:1024]
        return b"\x00" in data

    def _block(self, step: ImplementationStepResult, run: ImplementationRun | None, reason: str) -> None:
        step.status = "blocked"
        step.skipped_reason = reason
        step.message = reason
        if run is not None:
            run.blocked_steps += 1
            run.warnings.append(f"{step.step_id}: {reason}")

    def _finalize_run(self, run: ImplementationRun) -> None:
        if run.failed_steps > 0:
            run.status = "failed"
        elif run.blocked_steps > 0 or run.skipped_steps > 0:
            run.status = "completed_with_skips"
        else:
            run.status = "completed"
        run.summary = (
            f"Run {run.run_id}: completed={run.completed_steps}, skipped={run.skipped_steps}, "
            f"blocked={run.blocked_steps}, failed={run.failed_steps}."
        )
        run.updated_at = self._now()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
