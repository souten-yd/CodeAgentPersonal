import pathlib
import unittest


class TestPhase271WaitPlanClarificationGateContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke = pathlib.Path("scripts/smoke_ui_modes_playwright.py").read_text(encoding="utf-8")
        cls.workflow_smoke = pathlib.Path(".github/workflows/playwright-ui-smoke.yml").read_text(encoding="utf-8") if pathlib.Path(".github/workflows/playwright-ui-smoke.yml").exists() else ""

    def test_clarification_gate_decision_exists(self):
        for token in [
            '"needs_clarification"',
            '"clarification_required_before_plan_generation"',
        ]:
            self.assertIn(token, self.smoke)

    def test_clarification_signals_exist(self):
        for token in [
            "answer clarification",
            "回答してplan生成",
            "おまかせで進める",
            '"clarification_required"',
        ]:
            self.assertIn(token, self.smoke)

    def test_pending_plan_review_recognized_as_clarification_state(self):
        for token in [
            "plan_flow_plan_pending",
            "plan_flow_review_pending",
            "plan_flow_requirement_done",
        ]:
            self.assertIn(token, self.smoke)

    def test_wait_plan_pass_terminal_states_include_completed_and_needs_clarification(self):
        self.assertIn('if diag.get("finalDecision") in ("failed", "timeout", "unknown"):', self.smoke)
        for token in ['"completed"', '"needs_clarification"']:
            self.assertIn(token, self.smoke)

    def test_needs_clarification_does_not_click_buttons(self):
        self.assertNotIn('click("text=おまかせで進める")', self.smoke)
        self.assertNotIn('click("text=回答してPlan生成")', self.smoke)
        self.assertNotIn("auto clarification", self.smoke.lower())

    def test_destructive_actions_not_automated(self):
        for token in ["approvePlan(", "executePreview", "applyPatch", "bulk approve", "bulk apply", "auto approve", "auto apply"]:
            self.assertNotIn(token, self.smoke)

    def test_preflight_remains_get_only(self):
        preflight_block = self.smoke.split("async def collect_backend_preflight_status(page) -> dict:", 1)[1].split("\n\nasync def run_backend_preflight", 1)[0]
        self.assertNotIn("page.request.post(", preflight_block)
        self.assertNotIn("/api/task/plan", preflight_block)

    def test_workflow_does_not_enable_wait_plan_by_default(self):
        self.assertNotIn("RUN_ATLAS_BACKEND_E2E_WAIT_PLAN=1", self.workflow_smoke)
        self.assertNotIn("RUN_ATLAS_BACKEND_E2E=1", self.workflow_smoke)


if __name__ == "__main__":
    unittest.main()
