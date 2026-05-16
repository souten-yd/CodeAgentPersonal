from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from agent.atlas_debug_review_schema import AtlasDebugReviewRequest, AtlasDebugReviewResult
from agent.atlas_journal import AtlasJournal
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.debug_loop_runner import DebugLoopRunner
from agent.debug_loop_schema import AtlasDebugInput


class AtlasDebugReviewService:
    ALLOWED_SOURCE_TYPES = {"verification", "safe_apply", "pipeline"}

    def __init__(self, *, journal: AtlasJournal, storage: AtlasPlanPoolStorage, debug_runner: DebugLoopRunner | None = None):
        self.journal = journal
        self.storage = storage
        self.debug_runner = debug_runner

    def review_item(self, request: AtlasDebugReviewRequest) -> AtlasDebugReviewResult:
        pool = self.storage.load_pool(request.pool_id)
        item = pool.get_item(request.item_id)
        self._append_event(pool.pool_id, request.run_id, "debug_review_manual_started", item, "started")
        if item is None:
            warnings = ["item_not_found"]
            self._append_event(pool.pool_id, request.run_id, "debug_review_manual_blocked", None, "blocked", warnings)
            return AtlasDebugReviewResult(pool_id=pool.pool_id, item_id=request.item_id, run_id=request.run_id, status="blocked", warnings=warnings, plan_pool=pool.model_dump())

        ok, warnings = self.validate_item_for_debug_review(pool, item, request)
        if not ok:
            self._append_event(pool.pool_id, request.run_id, "debug_review_manual_blocked", item, "blocked", warnings)
            return AtlasDebugReviewResult(pool_id=pool.pool_id, item_id=item.item_id, run_id=request.run_id, status="blocked", warnings=warnings, plan_pool=pool.model_dump())

        try:
            debug_input = self.build_debug_input(pool, item, request)
            attempt = self.debug_runner.analyze_failure(debug_input, retry_count=0)
            loop = self.debug_runner.create_loop_state(pool.pool_id, item.item_id, request.run_id or "debug_review")
            self.debug_runner.add_attempt(loop, attempt)
            notes_path = self.debug_runner.write_debug_notes(loop)

            result = AtlasDebugReviewResult(pool_id=pool.pool_id, item_id=item.item_id, run_id=request.run_id, status="analyzed", debug_attempt=attempt.model_dump(), debug_notes_path=str(notes_path or ""))
            json_path, md_path = self.save_debug_review_record(pool.pool_id, item.item_id, result, request)
            self.mark_item_from_debug_review(pool, item, result)
            self.storage.save_pool(pool)
            self.journal.save_plan_pool(pool)
            self._append_event(pool.pool_id, request.run_id, "debug_review_manual_analyzed", item, "analyzed")
            result.plan_pool = pool.model_dump()
            result.metadata.update({"debug_review_record_json": json_path, "debug_review_record_md": md_path})
            return result
        except Exception as exc:
            errors = [str(exc)]
            self._append_event(pool.pool_id, request.run_id, "debug_review_manual_failed", item, "failed", errors=errors)
            return AtlasDebugReviewResult(pool_id=pool.pool_id, item_id=item.item_id, run_id=request.run_id, status="failed", errors=errors, plan_pool=pool.model_dump())

    def validate_item_for_debug_review(self, pool: AtlasPlanPool, item: AtlasPlanItem, request: AtlasDebugReviewRequest) -> tuple[bool, list[str]]:
        warnings: list[str] = []
        verification_status = str(((item.metadata or {}).get("verification") or {}).get("status") or "").lower()
        item_status = str(item.status or "").lower()
        if verification_status != "failed" and item_status != "failed":
            warnings.append("verification_not_failed")
        if self.debug_runner is None:
            warnings.append("debug_runner_unavailable")
        if request.source_type not in self.ALLOWED_SOURCE_TYPES:
            warnings.append("source_type_not_allowed")
        return len(warnings) == 0, warnings

    def build_debug_input(self, pool: AtlasPlanPool, item: AtlasPlanItem, request: AtlasDebugReviewRequest) -> AtlasDebugInput:
        record = self.load_latest_verification_result(pool.pool_id, item.item_id, request.run_id)
        verification = (item.metadata or {}).get("verification") or {}
        payload = record or verification
        return AtlasDebugInput(
            pool_id=pool.pool_id,
            item_id=item.item_id,
            run_id=request.run_id,
            source_type=request.source_type,
            error_summary=str(payload.get("error_summary") or payload.get("status") or "verification failed"),
            stdout=str(payload.get("stdout") or ""),
            stderr=str(payload.get("stderr") or ""),
            returncode=payload.get("returncode") if isinstance(payload.get("returncode"), int) else None,
            status=str(payload.get("status") or "failed"),
            metadata={"warnings": list(payload.get("warnings") or []), "errors": list(payload.get("errors") or [])},
        )

    def load_latest_verification_result(self, pool_id: str, item_id: str, run_id: str = "") -> dict:
        out_dir = Path(self.journal.paths(pool_id=pool_id).plan_pool_json).parent / "verification"
        if not out_dir.exists():
            return {}
        candidates = sorted(out_dir.glob(f"{item_id}_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in candidates:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if run_id and str(payload.get("run_id") or "") not in {"", run_id}:
                continue
            results = payload.get("verification_results") or []
            failed = next((r for r in results if str(r.get("status")) in {"failed", "blocked", "timed_out"}), {})
            if failed:
                return failed
            return payload
        return {}

    def save_debug_review_record(self, pool_id: str, item_id: str, result: AtlasDebugReviewResult, request: AtlasDebugReviewRequest) -> tuple[str, str]:
        ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        out_dir = Path(self.journal.paths(pool_id=pool_id).plan_pool_json).parent / 'debug_review'
        out_dir.mkdir(parents=True, exist_ok=True)
        json_path = out_dir / f'{item_id}_{ts}.json'
        md_path = out_dir / f'{item_id}_{ts}.md'
        with json_path.open('w', encoding='utf-8') as f:
            json.dump(result.model_dump(), f, ensure_ascii=False, indent=2)
        attempt = result.debug_attempt or {}
        content = f"# Atlas Debug Review\n\n- Pool ID: {pool_id}\n- Item ID: {item_id}\n- Run ID: {request.run_id}\n- Source type: {request.source_type}\n- Status: {result.status}\n- Root cause category: {attempt.get('root_cause_category','')}\n- Root cause: {attempt.get('root_cause','')}\n- Proposed fix: {attempt.get('proposed_fix','')}\n- Reusable lesson: {attempt.get('reusable_lesson','')}\n- Retry recommended: {attempt.get('retry_recommended', False)}\n- Warnings: {', '.join(result.warnings)}\n- Errors: {', '.join(result.errors)}\n\n- No patch was generated.\n- No safe_apply was run.\n- No verification rerun was performed.\n"
        with md_path.open('w', encoding='utf-8') as f:
            f.write(content)
        return str(json_path), str(md_path)

    def mark_item_from_debug_review(self, pool: AtlasPlanPool, item: AtlasPlanItem, result: AtlasDebugReviewResult) -> None:
        attempt = result.debug_attempt or {}
        item.metadata.setdefault("debug_review", {})
        item.metadata["debug_review"].update({
            "status": result.status,
            "attempt_id": attempt.get("attempt_id", ""),
            "root_cause_category": attempt.get("root_cause_category", "unknown"),
            "retry_recommended": bool(attempt.get("retry_recommended", False)),
            "proposed_fix": attempt.get("proposed_fix", ""),
            "debug_notes_path": result.debug_notes_path,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
        })

    def _append_event(self, pool_id: str, run_id: str, event_type: str, item: AtlasPlanItem | None, status: str, warnings: list[str] | None = None, errors: list[str] | None = None) -> None:
        if not run_id:
            return
        self.journal.append_event(pool_id, run_id, {"event_type": event_type, "pool_id": pool_id, "run_id": run_id, "item_id": item.item_id if item else "", "status": status, "warnings": list(warnings or []), "errors": list(errors or []), "created_at": datetime.now(timezone.utc).isoformat()})
