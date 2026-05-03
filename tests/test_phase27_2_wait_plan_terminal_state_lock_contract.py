import pathlib
import unittest


class TestPhase272WaitPlanTerminalStateLockContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs = pathlib.Path("docs/agent_guided_workflow_integration.md").read_text(encoding="utf-8")
        cls.readme = pathlib.Path("README.md").read_text(encoding="utf-8")
        cls.smoke = pathlib.Path("scripts/smoke_ui_modes_playwright.py").read_text(encoding="utf-8")
        cls.workflow = (
            pathlib.Path(".github/workflows/playwright-ui-smoke.yml").read_text(encoding="utf-8")
            if pathlib.Path(".github/workflows/playwright-ui-smoke.yml").exists()
            else ""
        )

    def test_docs_contain_phase272_note(self):
        for token in [
            "Phase 27.2",
            "Windows local wait-plan E2E",
            "completed",
            "needs_clarification",
            "human-in-the-loop",
        ]:
            self.assertIn(token, self.docs)

    def test_wait_plan_terminal_states_are_locked(self):
        for token in [
            '"completed"',
            '"needs_clarification"',
            "clarification_required_before_plan_generation",
            "plan_flow_generated_review_done_approval_required",
        ]:
            self.assertIn(token, self.smoke if token.startswith('"') else self.docs + self.smoke)

    def test_needs_clarification_not_same_as_generated_plan(self):
        self.assertIn("not the same as Plan generated", self.docs)
        self.assertIn("requires human action", self.readme)

    def test_clarification_buttons_are_diagnostic_only(self):
        for token in ["回答してPlan生成", "おまかせで進める", "not clicked automatically"]:
            self.assertIn(token, self.docs)
        self.assertNotIn('click("text=回答してPlan生成")', self.smoke)
        self.assertNotIn('click("text=おまかせで進める")', self.smoke)
        self.assertNotIn("auto clarification response", self.smoke.lower())

    def test_destructive_actions_not_automated(self):
        for token in ["approvePlan(", "executePreview", "applyPatch", "bulk approve", "bulk apply", "auto approve", "auto apply"]:
            self.assertNotIn(token, self.smoke)

    def test_preflight_remains_get_only(self):
        preflight_block = self.smoke.split("async def collect_backend_preflight_status(page) -> dict:", 1)[1].split(
            "\n\nasync def run_backend_preflight", 1
        )[0]
        self.assertNotIn("page.request.post(", preflight_block)
        self.assertNotIn("/api/task/plan", preflight_block)

    def test_workflow_does_not_enable_e2e_wait_plan_or_preflight_by_default(self):
        self.assertNotIn("RUN_ATLAS_BACKEND_E2E=1", self.workflow)
        self.assertNotIn("RUN_ATLAS_BACKEND_E2E_WAIT_PLAN=1", self.workflow)
        self.assertNotIn("RUN_ATLAS_BACKEND_PREFLIGHT=1", self.workflow)


if __name__ == "__main__":
    unittest.main()
