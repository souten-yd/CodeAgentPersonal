from __future__ import annotations

import json
from pathlib import Path

from agent.implementation_schema import ImplementationRun


class RunStorage:
    def __init__(self, ca_data_dir: str | Path) -> None:
        self.base_dir = Path(ca_data_dir)
        self.runs_dir = self.base_dir / "runs"
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def run_dir(self, run_id: str) -> Path:
        return self.runs_dir / run_id

    def save_run(self, run: ImplementationRun) -> Path:
        rd = self.run_dir(run.run_id)
        rd.mkdir(parents=True, exist_ok=True)
        path = rd / "run.json"
        path.write_text(json.dumps(run.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def save_steps(self, run: ImplementationRun) -> Path:
        rd = self.run_dir(run.run_id)
        rd.mkdir(parents=True, exist_ok=True)
        path = rd / "steps.json"
        payload = [s.model_dump() for s in run.step_results]
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def save_log(self, run_id: str, lines: list[str]) -> Path:
        rd = self.run_dir(run_id)
        rd.mkdir(parents=True, exist_ok=True)
        path = rd / "execution.log"
        path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        return path

    def save_report(self, run: ImplementationRun) -> Path:
        rd = self.run_dir(run.run_id)
        rd.mkdir(parents=True, exist_ok=True)
        path = rd / "final_report.md"
        step_summary = "\n".join(
            [f"- {s.step_id}: {s.status} ({s.title})" for s in run.step_results]
        ) or "- No steps"
        warnings = "\n".join([f"- {w}" for w in run.warnings]) or "- None"
        errors = "\n".join([f"- {e}" for e in run.errors]) or "- None"
        if run.failed_steps > 0:
            next_action = "Investigate failed steps and request plan revision if needed."
        elif run.blocked_steps > 0:
            next_action = "Review blocked steps and revise plan or explicit approvals."
        else:
            next_action = "Proceed to verification workflow in a later phase."
        report = "\n".join(
            [
                f"# Implementation Run Report: {run.run_id}",
                "",
                f"- run_id: {run.run_id}",
                f"- plan_id: {run.plan_id}",
                f"- approval_id: {run.approval_id}",
                f"- status: {run.status}",
                f"- execution_mode: {run.execution_mode}",
                f"- completed: {run.completed_steps}",
                f"- skipped: {run.skipped_steps}",
                f"- blocked: {run.blocked_steps}",
                f"- failed: {run.failed_steps}",
                "",
                "## Step summary",
                step_summary,
                "",
                "## Warnings",
                warnings,
                "",
                "## Errors",
                errors,
                "",
                "- destructive actions were not executed: true",
                f"- next recommended action: {next_action}",
            ]
        )
        path.write_text(report, encoding="utf-8")
        return path

    def load_run(self, run_id: str) -> dict:
        path = self.run_dir(run_id) / "run.json"
        if not path.exists():
            raise FileNotFoundError(str(path))
        return json.loads(path.read_text(encoding="utf-8"))

    def read_log(self, run_id: str) -> str:
        path = self.run_dir(run_id) / "execution.log"
        if not path.exists():
            raise FileNotFoundError(str(path))
        return path.read_text(encoding="utf-8")

    def read_report(self, run_id: str) -> str:
        path = self.run_dir(run_id) / "final_report.md"
        if not path.exists():
            raise FileNotFoundError(str(path))
        return path.read_text(encoding="utf-8")


    def list_runs(self, limit: int = 20) -> list[dict]:
        lim = max(1, min(int(limit or 20), 200))
        items: list[dict] = []
        run_root = self.base_dir / "runs"
        run_root.mkdir(parents=True, exist_ok=True)
        for rd in run_root.iterdir():
            if not rd.is_dir():
                continue
            run_id = rd.name
            run_json = rd / "run.json"
            payload = {
                "run_id": run_id,
                "created_at": "",
                "plan_id": "",
                "status": "unknown",
                "execution_mode": "",
            }
            if run_json.exists():
                try:
                    data = json.loads(run_json.read_text(encoding="utf-8"))
                    payload.update({
                        "run_id": str(data.get("run_id") or run_id),
                        "created_at": str(data.get("created_at") or ""),
                        "plan_id": str(data.get("plan_id") or ""),
                        "status": str(data.get("status") or "unknown"),
                        "execution_mode": str(data.get("execution_mode") or ""),
                    })
                except Exception:
                    payload["summary_error"] = "run_json_parse_error"
            try:
                payload["_sort_key"] = run_json.stat().st_mtime if run_json.exists() else rd.stat().st_mtime
            except Exception:
                payload["_sort_key"] = 0
            items.append(payload)
        items.sort(key=lambda x: x.get("_sort_key", 0), reverse=True)
        out = []
        for x in items[:lim]:
            x.pop("_sort_key", None)
            out.append(x)
        return out
