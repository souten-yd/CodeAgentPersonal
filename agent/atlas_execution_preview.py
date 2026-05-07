from __future__ import annotations

from uuid import uuid4


class AtlasExecutionPreview:
    def __init__(self, *, plan_storage=None, implementation_executor=None):
        self.plan_storage = plan_storage
        self.implementation_executor = implementation_executor

    def _load_plan(self, plan_id: str) -> dict:
        if not self.plan_storage or not plan_id:
            return {}
        for method in ("load_plan", "get_plan"):
            fn = getattr(self.plan_storage, method, None)
            if callable(fn):
                try:
                    loaded = fn(plan_id)
                    return loaded if isinstance(loaded, dict) else {}
                except Exception:
                    return {}
        return {}

    def prepare_preview(self, *, plan_id: str, requirement_id: str = "", approval: dict | None = None, project_path: str = "", project_name: str = "") -> dict:
        plan = self._load_plan(plan_id)
        planned_steps = list(plan.get("implementation_steps") or [])
        target_files = list(plan.get("target_files") or [])
        risk_notes = list(plan.get("risks") or [])
        verification_plan = list(plan.get("verification_plan") or plan.get("test_plan") or [])

        combined_text = " ".join([str(planned_steps), str(risk_notes)]).lower()
        high_risk = any(t in combined_text for t in ["destructive", "drop ", "delete ", "rm ", "truncate", "high risk"])
        status = "blocked" if high_risk else "execution_preview_ready"
        summary = "Execution preview prepared. No files were changed." if status == "execution_preview_ready" else "Execution preview blocked due to high-risk steps. No files were changed."
        warnings = ["Potential destructive or high-risk steps detected."] if high_risk else []

        return {
            "execution_preview_id": f"execprev_{uuid4().hex[:12]}",
            "status": status,
            "plan_id": plan_id,
            "requirement_id": requirement_id,
            "project_path": project_path,
            "project_name": project_name,
            "summary": summary,
            "planned_steps": planned_steps,
            "target_files": target_files,
            "risk_notes": risk_notes,
            "verification_plan": verification_plan,
            "safety_constraints": ["Preview only", "No file changes", "No patch apply", "No run_command"],
            "warnings": warnings,
        }
