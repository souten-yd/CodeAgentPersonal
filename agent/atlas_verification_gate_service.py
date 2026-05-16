from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from agent.atlas_journal import AtlasJournal
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_verification_gate_schema import AtlasVerificationRequest, AtlasVerificationResult
from agent.test_command_runner import TestCommandRunner
from agent.test_command_runner_schema import AtlasTestCommandRequest


class AtlasVerificationGateService:
    ALLOWED_PROFILES = {"default"}

    def __init__(self, *, journal: AtlasJournal, storage: AtlasPlanPoolStorage, test_runner: TestCommandRunner | None = None):
        self.journal = journal
        self.storage = storage
        self.test_runner = test_runner

    def verify_item(self, request: AtlasVerificationRequest) -> AtlasVerificationResult:
        pool = self.storage.load_pool(request.pool_id)
        item = pool.get_item(request.item_id)
        self._append_event(pool.pool_id, request.run_id, "verification_manual_started", item, status="started")
        if item is None:
            warnings = ["item_not_found"]
            self._append_event(pool.pool_id, request.run_id, "verification_manual_blocked", None, status="blocked", warnings=warnings)
            return AtlasVerificationResult(pool_id=pool.pool_id, item_id=request.item_id, run_id=request.run_id, status="blocked", warnings=warnings, plan_pool=pool.model_dump())

        ok, warnings = self.validate_item_for_verification(pool, item, request)
        if not ok:
            self.mark_item_from_verification(pool, item, {"status": "blocked"})
            self.storage.save_pool(pool)
            self.journal.save_plan_pool(pool)
            self._append_event(pool.pool_id, request.run_id, "verification_manual_blocked", item, status="blocked", warnings=warnings)
            return AtlasVerificationResult(pool_id=pool.pool_id, item_id=item.item_id, run_id=request.run_id, status="blocked", warnings=warnings, plan_pool=pool.model_dump())

        commands = self.build_verification_commands(pool, item, request)
        requests = [AtlasTestCommandRequest(command=cmd["command"], cwd=cmd.get("cwd", ""), timeout_seconds=cmd.get("timeout_seconds", 120), metadata=cmd.get("metadata", {})) for cmd in commands]
        batch = self.test_runner.run_many(requests, stop_on_failure=False)
        results = [(x.model_dump() if hasattr(x, "model_dump") else dict(x)) for x in (batch.results or [])]
        status = "failed" if any(r.get("status") in {"failed", "blocked", "timed_out"} for r in results) else "passed"
        result = AtlasVerificationResult(pool_id=pool.pool_id, item_id=item.item_id, run_id=request.run_id, status=status, verification_results=results, warnings=[])
        self.mark_item_from_verification(pool, item, result.model_dump())
        self.storage.save_pool(pool)
        self.journal.save_plan_pool(pool)
        json_path, md_path = self.save_verification_record(pool.pool_id, item.item_id, result)
        event_type = "verification_manual_passed" if status == "passed" else "verification_manual_failed"
        self._append_event(pool.pool_id, request.run_id, event_type, item, status=status, execution_record_json=json_path, execution_record_md=md_path)
        result.plan_pool = pool.model_dump()
        result.metadata.update({"verification_record_json": json_path, "verification_record_md": md_path})
        return result

    def validate_item_for_verification(self, pool: AtlasPlanPool, item: AtlasPlanItem, request: AtlasVerificationRequest) -> tuple[bool, list[str]]:
        warnings = []
        safe_apply_status = str(((item.metadata or {}).get("safe_apply") or {}).get("status") or "").lower()
        item_status = str(item.status or "").lower()
        if safe_apply_status not in {"applied", "simulated"} and item_status not in {"completed", "applied"}:
            warnings.append("safe_apply_not_done")
        if str((item.metadata or {}).get("action_type") or "").lower() == "run_command":
            warnings.append("forbidden_action_type")
        if request.command_profile not in self.ALLOWED_PROFILES:
            warnings.append("command_profile_not_allowed")
        if self.test_runner is None:
            warnings.append("test_runner_unavailable")
        return len(warnings) == 0, warnings

    def build_verification_commands(self, pool: AtlasPlanPool, item: AtlasPlanItem, request: AtlasVerificationRequest) -> list[dict]:
        commands = []
        py_targets = [p for p in (item.target_files or []) if str(p).endswith('.py')]
        for target in py_targets:
            commands.append({"command": f"python -m py_compile {target}", "timeout_seconds": 120, "metadata": {"pool_id": pool.pool_id, "item_id": item.item_id, "profile": request.command_profile}})
        if not commands:
            commands.append({"command": "node --check web/js/atlas_dashboard.js", "timeout_seconds": 120, "metadata": {"pool_id": pool.pool_id, "item_id": item.item_id, "profile": request.command_profile}})
        return commands

    def save_verification_record(self, pool_id: str, item_id: str, result: AtlasVerificationResult) -> tuple[str, str]:
        ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        out_dir = Path(self.journal.paths(pool_id=pool_id).plan_pool_json).parent / 'verification'
        out_dir.mkdir(parents=True, exist_ok=True)
        json_path = out_dir / f'{item_id}_{ts}.json'
        md_path = out_dir / f'{item_id}_{ts}.md'
        payload = result.model_dump()
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        md_path.write_text(f"# Atlas Verification\n\n- Pool ID: {pool_id}\n- Item ID: {item_id}\n- Status: {result.status}\n", encoding='utf-8')
        return str(json_path), str(md_path)

    def mark_item_from_verification(self, pool: AtlasPlanPool, item: AtlasPlanItem, result: dict) -> None:
        status = str(result.get("status") or "").lower()
        item.metadata.setdefault("verification", {})
        item.metadata["verification"].update({"status": status, "verified_at": datetime.now(timezone.utc).isoformat()})

    def _append_event(self, pool_id: str, run_id: str, event_type: str, item: AtlasPlanItem | None, *, status: str, warnings: list[str] | None = None, execution_record_json: str = '', execution_record_md: str = '') -> None:
        if not run_id:
            return
        self.journal.append_event(pool_id, run_id, {"event_type": event_type, "pool_id": pool_id, "run_id": run_id, "item_id": item.item_id if item else '', "status": status, "warnings": list(warnings or []), "errors": [], "execution_record_json": execution_record_json, "execution_record_md": execution_record_md, "created_at": datetime.now(timezone.utc).isoformat()})
