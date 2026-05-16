from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent.atlas_journal_schema import AtlasJournalArtifact, AtlasJournalPaths
from agent.atlas_pipeline_runner_schema import AtlasPipelineEvent, AtlasPipelineRunState
from agent.atlas_plan_pool_schema import AtlasPlanPool


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _model_dump(model: Any) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def _model_validate(model_type: type[Any], payload: dict[str, Any]) -> Any:
    if hasattr(model_type, "model_validate"):
        return model_type.model_validate(payload)
    return model_type(**payload)


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


class AtlasJournal:
    def __init__(self, root_dir: Path | str, workspace_id: str = "default"):
        self.root_dir = Path(root_dir)
        self.workspace_id = self._validate_storage_id(workspace_id, "workspace_id")

    def workspace_dir(self) -> Path:
        return self.root_dir / "atlas" / "workspaces" / self.workspace_id

    def plan_pool_dir(self, pool_id: str) -> Path:
        safe_pool_id = self._validate_storage_id(pool_id, "pool_id")
        return self.workspace_dir() / "plan_pools" / safe_pool_id

    def pipeline_run_dir(self, pool_id: str, run_id: str) -> Path:
        safe_run_id = self._validate_storage_id(run_id, "run_id")
        return self.plan_pool_dir(pool_id) / "pipeline_runs" / safe_run_id

    def context_pack_path(self, pool_id: str, context_pack_id: str, suffix: str = ".json") -> Path:
        safe_context_pack_id = self._validate_storage_id(context_pack_id, "context_pack_id")
        return self.plan_pool_dir(pool_id) / "context_packs" / f"{safe_context_pack_id}{suffix}"

    def paths(self, pool_id: str = "", run_id: str = "") -> AtlasJournalPaths:
        workspace_dir = self.workspace_dir()
        plan_pool_dir = self.plan_pool_dir(pool_id) if pool_id else Path("")
        pipeline_run_dir = self.pipeline_run_dir(pool_id, run_id) if pool_id and run_id else Path("")
        approvals_dir = plan_pool_dir / "approvals" if pool_id else Path("")
        return AtlasJournalPaths(
            workspace_id=self.workspace_id,
            root_dir=str(self.root_dir),
            workspace_dir=str(workspace_dir),
            plan_pool_dir=str(plan_pool_dir) if pool_id else "",
            pipeline_run_dir=str(pipeline_run_dir) if pool_id and run_id else "",
            checkpoint_md=str(plan_pool_dir / "checkpoint.md") if pool_id else str(workspace_dir / "atlas_checkpoint.md"),
            plan_pool_json=str(plan_pool_dir / "plan_pool.json") if pool_id else "",
            plan_pool_md=str(plan_pool_dir / "plan_pool.md") if pool_id else "",
            pipeline_state_json=str(pipeline_run_dir / "state.json") if pool_id and run_id else "",
            pipeline_state_md=str(pipeline_run_dir / "state.md") if pool_id and run_id else "",
            events_ndjson=str(pipeline_run_dir / "events.ndjson") if pool_id and run_id else "",
            final_report_md=str(pipeline_run_dir / "final_report.md") if pool_id and run_id else "",
            approvals_json=str(approvals_dir / "approvals.json") if pool_id else "",
            approvals_md=str(approvals_dir / "approvals.md") if pool_id else "",
        )

    def save_plan_pool(self, pool: AtlasPlanPool) -> AtlasJournalArtifact:
        paths = self.paths(pool_id=pool.pool_id)
        json_path = _write_json(Path(paths.plan_pool_json), _model_dump(pool))
        markdown_path = self.write_plan_pool_markdown(pool)
        return AtlasJournalArtifact(
            artifact_id=pool.pool_id,
            artifact_type="plan_pool",
            json_path=str(json_path),
            markdown_path=str(markdown_path),
            metadata={"workspace_id": self.workspace_id, "pool_id": pool.pool_id},
        )

    def write_plan_pool_markdown(self, pool: AtlasPlanPool) -> Path:
        rows = ["| item_id | status | item_type | risk_level | title | depends_on |", "| --- | --- | --- | --- | --- | --- |"]
        for item in pool.items:
            rows.append(
                "| {item_id} | {status} | {item_type} | {risk_level} | {title} | {depends_on} |".format(
                    item_id=item.item_id,
                    status=item.status,
                    item_type=item.item_type,
                    risk_level=item.risk_level,
                    title=self._md_cell(item.title),
                    depends_on=", ".join(item.depends_on),
                )
            )
        body = f"""# Atlas Plan Pool

- Pool ID: {pool.pool_id}
- Root Goal: {pool.root_goal}
- Status: {pool.status}
- Planning Depth: {pool.planning_depth}
- Automation Level: {pool.automation_level}
- Execution Strategy: {pool.execution_strategy}

## Items

{chr(10).join(rows)}

## Warnings

{self._markdown_list(pool.warnings)}

## Errors

{self._markdown_list(pool.errors)}
"""
        path = self.plan_pool_dir(pool.pool_id) / "plan_pool.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return path

    def save_pipeline_state(self, pool_id: str, state: AtlasPipelineRunState) -> AtlasJournalArtifact:
        paths = self.paths(pool_id=pool_id, run_id=state.run_id)
        json_path = _write_json(Path(paths.pipeline_state_json), _model_dump(state))
        markdown_path = self.write_pipeline_state_markdown(pool_id, state)
        return AtlasJournalArtifact(
            artifact_id=state.run_id,
            artifact_type="pipeline_state",
            json_path=str(json_path),
            markdown_path=str(markdown_path),
            metadata={"workspace_id": self.workspace_id, "pool_id": pool_id, "run_id": state.run_id},
        )

    def write_pipeline_state_markdown(self, pool_id: str, state: AtlasPipelineRunState) -> Path:
        recent_events = state.events[-5:]
        event_lines = [f"- {event.event_type}: {event.message}" for event in recent_events]
        body = f"""# Atlas Pipeline State

- Run ID: {state.run_id}
- Pool ID: {state.pool_id}
- Status: {state.status}
- Current Item: {state.current_item_id or 'None'}

## Completed Item IDs

{self._markdown_list(state.completed_item_ids)}

## Failed Item IDs

{self._markdown_list(state.failed_item_ids)}

## Blocked Item IDs

{self._markdown_list(state.blocked_item_ids)}

## Warnings

{self._markdown_list(state.warnings)}

## Errors

{self._markdown_list(state.errors)}

## Recent Events Summary

{self._markdown_list(event_lines)}
"""
        path = self.pipeline_run_dir(pool_id, state.run_id) / "state.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return path

    def append_event(self, pool_id: str, run_id: str, event: AtlasPipelineEvent | dict) -> Path:
        path = self.pipeline_run_dir(pool_id, run_id) / "events.ndjson"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = _model_dump(event) if hasattr(event, "dict") or hasattr(event, "model_dump") else dict(event)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return path

    def write_checkpoint(
        self,
        pool: AtlasPlanPool | None = None,
        state: AtlasPipelineRunState | None = None,
        next_action: str = "",
    ) -> Path:
        pool_id = pool.pool_id if pool else (state.pool_id if state else "")
        run_id = state.run_id if state else ""
        status = state.status if state else (pool.status if pool else "ready")
        current_item_id = state.current_item_id if state else (pool.current_item_id if pool else "")
        current_item_title = ""
        if pool and current_item_id:
            item = pool.get_item(current_item_id)
            current_item_title = item.title if item else ""
        total_items = len(pool.items) if pool else 0
        completed_count = len(state.completed_item_ids) if state else (len(pool.completed_item_ids) if pool else 0)
        failed_count = len(state.failed_item_ids) if state else (len(pool.failed_item_ids) if pool else 0)
        blocked_count = len(state.blocked_item_ids) if state else (len(pool.blocked_item_ids) if pool else 0)
        last_event = state.events[-1] if state and state.events else None
        body = f"""# Atlas Checkpoint

- Workspace ID: {self.workspace_id}
- Current Goal: {pool.root_goal if pool else ''}
- Pool ID: {pool_id}
- Run ID: {run_id}
- Status: {status}
- Current Item: {current_item_id}{(' - ' + current_item_title) if current_item_title else ''}

## Progress

- completed / total: {completed_count} / {total_items}
- failed: {failed_count}
- blocked: {blocked_count}

## Last Event

{self._format_event(last_event)}

## Next Action

{next_action or self._default_next_action(status)}

## Recovery Notes

- JSON files are the machine-readable source of truth.
- Markdown files are human and LLM-readable recovery notes.
- events.ndjson is the append-only chronological event trail.
"""
        path = self.plan_pool_dir(pool_id) / "checkpoint.md" if pool_id else self.workspace_dir() / "atlas_checkpoint.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return path

    @staticmethod
    def _default_next_action(status: str) -> str:
        normalized = str(status or "").lower()
        if normalized == "waiting_for_clarification":
            return "Review planner questions and refine the goal before creating a PlanPool."
        if normalized == "ready":
            return "Start Dry-run to validate the generated PlanPool."
        if normalized in {"stale", "interrupted"}:
            return "Start a new dry-run from the recovered PlanPool."
        if normalized in {"paused", "approval_required"}:
            return "Review approval-required items before continuing."
        if normalized in {"completed", "completed_with_warnings"}:
            return "Review final report or create the next PlanPool."
        if normalized == "failed":
            return "Inspect failed items and prepare a debug follow-up."
        if normalized == "blocked":
            return "Review blocked items and policy reasons."
        return "Continue from the latest saved Atlas state."

    def write_next_actions(self, pool_id: str, actions: list[str]) -> Path:
        body = "# Atlas Next Actions\n\n" + self._markdown_list(actions) + "\n"
        path = self.plan_pool_dir(pool_id) / "next_actions.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return path

    def write_final_report(self, pool_id: str, run_id: str, title: str, body: str) -> Path:
        path = self.pipeline_run_dir(pool_id, run_id) / "final_report.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        report = f"# {title}\n\n- generated_at: {_utc_now_iso()}\n\n{body}\n"
        path.write_text(report, encoding="utf-8")
        return path

    def load_plan_pool(self, pool_id: str) -> AtlasPlanPool:
        path = self.plan_pool_dir(pool_id) / "plan_pool.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        return _model_validate(AtlasPlanPool, payload)

    def load_pipeline_state(self, pool_id: str, run_id: str) -> AtlasPipelineRunState:
        path = self.pipeline_run_dir(pool_id, run_id) / "state.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        return _model_validate(AtlasPipelineRunState, payload)

    def read_events(self, pool_id: str, run_id: str, limit: int | None = None) -> list[dict]:
        path = self.pipeline_run_dir(pool_id, run_id) / "events.ndjson"
        if not path.exists():
            return []
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if limit is None:
            return rows
        return rows[-limit:]

    def latest_pool_id(self) -> str:
        plan_pools_dir = self.workspace_dir() / "plan_pools"
        return self._latest_child_name(plan_pools_dir)

    def latest_run_id(self, pool_id: str) -> str:
        runs_dir = self.plan_pool_dir(pool_id) / "pipeline_runs"
        return self._latest_child_name(runs_dir)

    @staticmethod
    def _validate_storage_id(value: str, field_name: str) -> str:
        if not value:
            raise ValueError(f"{field_name} must not be empty")
        if "/" in value or "\\" in value or ".." in value:
            raise ValueError(f"{field_name} contains unsafe path segments: {value}")
        return value

    @staticmethod
    def _latest_child_name(directory: Path) -> str:
        if not directory.exists():
            return ""
        candidates = [path for path in directory.iterdir() if path.is_dir()]
        if not candidates:
            return ""
        latest = max(candidates, key=lambda path: (path.stat().st_mtime_ns, path.name))
        return latest.name

    @staticmethod
    def _markdown_list(values: list[str]) -> str:
        if not values:
            return "- None"
        return "\n".join(value if value.startswith("- ") else f"- {value}" for value in values)

    @staticmethod
    def _md_cell(value: str) -> str:
        return value.replace("|", "\\|").replace("\n", " ")

    @staticmethod
    def _format_event(event: AtlasPipelineEvent | None) -> str:
        if event is None:
            return "- None"
        return f"- {event.event_type}: {event.message}"
