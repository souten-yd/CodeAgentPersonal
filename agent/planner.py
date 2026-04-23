from __future__ import annotations

from agent.types import Action, EpicPlan, ExecutableTask, Plan, ProgramPlan, ToolResult

PHASE_DOD_CHECKS: dict[str, list[str]] = {
    "implementation": ["構文OK", "必須関数存在", "参照ファイル整合"],
    "static_verification": ["構文OK", "必須関数存在", "参照ファイル整合"],
    "execution_verification": ["実行時エラーなし", "期待挙動確認"],
}


class Planner:
    """3層計画 (Program/Epic/Task) を扱う Planner インターフェース。"""

    def create_plan(self, objective: str, context: dict) -> Plan:
        """Objective から ProgramPlan/EpicPlan/ExecutableTask を生成する。"""
        program = self.create_program_plan(objective=objective, context=context)
        epics = self.create_epic_plans(program=program, context=context)
        for epic in epics:
            epic.tasks = self.create_executable_tasks(program=program, epic=epic, context=context)
            for task in epic.tasks:
                phase = self._infer_phase_from_task(task)
                if not task.definition_of_done.checks:
                    task.definition_of_done.checks = list(PHASE_DOD_CHECKS.get(phase, []))
        return Plan(
            goal=objective,
            steps=[task.title for epic in epics for task in epic.tasks],
            metadata={"context": context},
            program=program,
            epics=epics,
        )

    def create_program_plan(self, objective: str, context: dict) -> ProgramPlan:
        raise NotImplementedError

    def create_epic_plans(self, program: ProgramPlan, context: dict) -> list[EpicPlan]:
        raise NotImplementedError

    def create_executable_tasks(self, program: ProgramPlan, epic: EpicPlan, context: dict) -> list[ExecutableTask]:
        raise NotImplementedError

    def choose_next_action(self, plan: Plan, history: list[ToolResult]) -> Action | None:
        task = self._next_pending_task(plan)
        if task is None:
            return None
        task.status = "in_progress"
        return Action(
            id=task.id,
            tool=task.action,
            input=task.input,
            rationale=f"ExecutableTask: {task.title}",
        )

    def mark_task_result(self, plan: Plan, result: ToolResult) -> None:
        """Executor の結果を Task 層へ反映する。"""
        task = self._find_task(plan, result.action_id)
        if task is None:
            return
        task.status = "done" if result.success else "failed"
        task.definition_of_done.satisfied = result.success

    def replan_minimal(self, plan: Plan, level: str, failed_action_id: str | None = None) -> Plan:
        """失敗時に最小階層のみ再計画する。"""
        if level == "task" and failed_action_id:
            task = self._find_task(plan, failed_action_id)
            if task is not None:
                task.status = "pending"
                task.definition_of_done.satisfied = False
            return plan

        if level == "epic":
            failed_epic = self._find_epic_by_action(plan, failed_action_id)
            if failed_epic is not None:
                for task in failed_epic.tasks:
                    task.status = "pending"
                    task.definition_of_done.satisfied = False
                failed_epic.status = "pending"
                failed_epic.definition_of_done.satisfied = False
            return plan

        if level == "program":
            context = dict(plan.metadata.get("context", {}))
            return self.create_plan(objective=plan.goal, context=context)

        return plan

    def _next_pending_task(self, plan: Plan) -> ExecutableTask | None:
        for epic in plan.epics:
            if not self._dependencies_satisfied(plan, epic):
                continue
            for task in epic.tasks:
                if task.status in {"pending", "failed"}:
                    return task
        return None

    def _infer_phase_from_task(self, task: ExecutableTask) -> str:
        if task.action in {"run_server", "run_browser"}:
            return "execution_verification"
        if task.action in {"run_shell", "run_python", "run_file", "run_npm", "run_node"}:
            return "static_verification"
        return "implementation"

    def _dependencies_satisfied(self, plan: Plan, epic: EpicPlan) -> bool:
        if not epic.dependencies:
            return True
        completed_ids = {item.id for item in plan.epics if item.status == "done"}
        return all(dep in completed_ids for dep in epic.dependencies)

    def _find_task(self, plan: Plan, task_id: str | None) -> ExecutableTask | None:
        if not task_id:
            return None
        for epic in plan.epics:
            for task in epic.tasks:
                if task.id == task_id:
                    return task
        return None

    def _find_epic_by_action(self, plan: Plan, task_id: str | None) -> EpicPlan | None:
        if not task_id:
            return None
        for epic in plan.epics:
            if any(task.id == task_id for task in epic.tasks):
                return epic
        return None
