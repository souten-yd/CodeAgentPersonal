from __future__ import annotations

from datetime import datetime, timezone
from pathlib import PurePosixPath

from agent.atlas_auto_verification_schema import AtlasAutoVerificationRequest, AtlasAutoVerificationResult
from agent.atlas_verification_allowlist import atlas_verification_allowlist
from agent.test_command_runner_schema import AtlasTestCommandRequest


class AtlasAutoVerificationService:
    def __init__(self, *, journal, storage, command_runner):
        self.journal = journal
        self.storage = storage
        self.command_runner = command_runner

    def run_after_auto_safe_apply(self, request: AtlasAutoVerificationRequest) -> AtlasAutoVerificationResult:
        pool = self.storage.load_pool(request.pool_id)
        item = pool.get_item(request.item_id)
        if item is None:
            return AtlasAutoVerificationResult(pool_id=request.pool_id, item_id=request.item_id, run_id=request.run_id, preset_id=request.preset_id, status="blocked", warnings=["item_not_found"], plan_pool=pool.model_dump())
        safe = ((item.metadata or {}).get("safe_apply") or {}).get("status")
        auto_safe = ((item.metadata or {}).get("auto_safe_apply") or {}).get("status")
        if str(safe or "").lower() != "applied" and str(auto_safe or "").lower() != "applied":
            return AtlasAutoVerificationResult(pool_id=pool.pool_id, item_id=item.item_id, run_id=request.run_id, preset_id=request.preset_id, status="skipped", warnings=["safe_apply_not_applied"], plan_pool=pool.model_dump())

        workspace_root = str(getattr(pool, "project_path", "") or "").strip()
        if not workspace_root:
            return self._blocked(pool, item.item_id, request, "project_path_missing")

        self._append_event(pool.pool_id, request.run_id, "auto_verification_started", item.item_id, status="started")
        allowlist = atlas_verification_allowlist()
        if request.metadata.get("command"):
            return self._blocked(pool, item.item_id, request, "arbitrary_command_forbidden")
        command_id = request.command_id or str(((item.metadata or {}).get("verification") or {}).get("command_id") or "")
        if not command_id:
            return self._blocked(pool, item.item_id, request, "verification_command_missing")
        if command_id not in allowlist or not allowlist[command_id].allowed:
            return self._blocked(pool, item.item_id, request, "verification_command_not_allowlisted")
        spec = allowlist[command_id]

        command = []
        for tok in spec.command:
            if tok == "{test_path}":
                v = str(request.metadata.get("test_path") or ((item.metadata or {}).get("verification") or {}).get("test_path") or "")
                if not self._safe_rel(v):
                    return self._blocked(pool, item.item_id, request, "unsafe_path")
                command.append(v)
            elif tok == "{test_file}":
                v = str(request.metadata.get("test_file") or ((item.metadata or {}).get("verification") or {}).get("test_file") or "")
                if not self._safe_rel(v):
                    return self._blocked(pool, item.item_id, request, "unsafe_path")
                command.append(v)
            elif tok.startswith("{") and tok.endswith("}"):
                return self._blocked(pool, item.item_id, request, "unsupported_template_token")
            else:
                command.append(tok)

        res = self.command_runner.run_command(AtlasTestCommandRequest(command=" ".join(command), cwd=workspace_root, timeout_seconds=spec.timeout_seconds, metadata={"pool_id": pool.pool_id, "item_id": item.item_id, "source": "auto_verification"}))
        status, classify_warnings = self._classify(res, command_id)
        event = {"passed": "auto_verification_passed", "blocked": "auto_verification_blocked"}.get(status, "auto_verification_failed")
        self._append_event(pool.pool_id, request.run_id, event, item.item_id, status=status, warnings=classify_warnings)
        out = AtlasAutoVerificationResult(pool_id=pool.pool_id, item_id=item.item_id, run_id=request.run_id, preset_id=request.preset_id, status=status, verification_result=res.model_dump(), command_id=command_id, command=command, exit_code=res.returncode, stdout_tail=(res.stdout or "")[-4000:], stderr_tail=(res.stderr or "")[-4000:], warnings=[*classify_warnings, *res.warnings], errors=list(res.errors), metadata={"workspace_root": workspace_root}, plan_pool=pool.model_dump())
        item.metadata.setdefault("auto_verification", {})
        item.metadata["auto_verification"].update({"status": status, "command_id": command_id, "verified_at": datetime.now(timezone.utc).isoformat()})
        self.storage.save_pool(pool)
        self.journal.save_plan_pool(pool)
        out.plan_pool = pool.model_dump()
        return out

    def _classify(self, res, command_id: str) -> tuple[str, list[str]]:
        """Map a raw command result to passed / failed / blocked, distinguishing a real test
        failure from an environment problem (interpreter or pytest missing, no tests collected).
        Environment problems become 'blocked' with an actionable warning so the autopilot does not
        treat a successfully-applied change as a code failure just because the harness can't run."""
        if res.status == "passed":
            return "passed", []
        # Missing interpreter/executable (python/python3/node not on PATH).
        if res.status == "blocked" and str(getattr(res, "blocked_reason", "")) == "executable_not_found":
            return "blocked", ["test_harness_unavailable", "interpreter_or_executable_missing"]
        is_pytest = str(command_id).startswith("pytest")
        stderr = (getattr(res, "stderr", "") or "") + (getattr(res, "stdout", "") or "")
        if is_pytest:
            # pytest itself is not installed in the interpreter we ran.
            if "No module named pytest" in stderr or "No module named 'pytest'" in stderr:
                return "blocked", ["test_harness_unavailable", "pytest_not_installed"]
            # pytest exit code 5 = no tests were collected (empty/placeholder test file). That is not
            # a failing assertion — surface it distinctly instead of as a hard failure.
            if getattr(res, "returncode", None) == 5:
                return "blocked", ["no_tests_collected"]
        # Everything else non-passed (assertion failures, compile errors, timeouts) is a real failure.
        return "failed", []

    def _safe_rel(self, value: str) -> bool:
        if not value:
            return False
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts:
            return False
        return True

    def _blocked(self, pool, item_id: str, request: AtlasAutoVerificationRequest, reason: str):
        self._append_event(pool.pool_id, request.run_id, "auto_verification_blocked", item_id, status="blocked", warnings=[reason])
        return AtlasAutoVerificationResult(pool_id=pool.pool_id, item_id=item_id, run_id=request.run_id, preset_id=request.preset_id, status="blocked", warnings=[reason], errors=[reason], plan_pool=pool.model_dump())

    def _append_event(self, pool_id: str, run_id: str, event_type: str, item_id: str, *, status: str, warnings: list[str] | None = None):
        if not run_id:
            return
        self.journal.append_event(pool_id, run_id, {"event_type": event_type, "pool_id": pool_id, "run_id": run_id, "item_id": item_id, "status": status, "warnings": list(warnings or []), "errors": [], "created_at": datetime.now(timezone.utc).isoformat()})
