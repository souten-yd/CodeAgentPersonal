import pathlib
import unittest


class TestPhase270bWaitPlanCompletionRecognitionContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke = pathlib.Path("scripts/smoke_ui_modes_playwright.py").read_text(encoding="utf-8")
        cls.workflow = pathlib.Path(".github/workflows/playwright-ui-smoke.yml").read_text(encoding="utf-8") if pathlib.Path(".github/workflows/playwright-ui-smoke.yml").exists() else ""

    def test_plan_flow_generated_review_done_approval_required_is_recognized(self):
        for token in ["requirement: done", "plan: generated", "review: done", "approval: required"]:
            self.assertIn(token, self.smoke)

    def test_completion_signals_exist(self):
        for token in [
            "plan_flow_requirement_done",
            "plan_flow_plan_generated",
            "plan_flow_review_done",
            "plan_flow_approval_required",
        ]:
            self.assertIn(token, self.smoke)

    def test_final_decision_completed_reason_exists(self):
        self.assertIn('"finalDecision": final', self.smoke)
        self.assertIn('"completed"', self.smoke)
        self.assertIn("plan_flow_generated_review_done_approval_required", self.smoke)

    def test_empty_backend_jobs_not_required_for_failure(self):
        self.assertIn('"backendJobStatuses"', self.smoke)
        self.assertIn('"activeJobsResponse"', self.smoke)
        self.assertIn('has_completion_signal and not active_jobs_available', self.smoke)

    def test_last_error_dash_not_failure(self):
        self.assertIn('last_error not in ("", "-")', self.smoke)

    def test_destructive_actions_not_automated(self):
        for token in ["approvePlan(", "executePreview", "applyPatch", "bulk approve", "bulk apply", "auto approve", "auto apply"]:
            self.assertNotIn(token, self.smoke)

    def test_preflight_get_only(self):
        preflight_block = self.smoke.split("async def collect_backend_preflight_status(page) -> dict:", 1)[1].split("\n\nasync def run_backend_preflight", 1)[0]
        self.assertNotIn("page.request.post(", preflight_block)
        self.assertNotIn("/api/task/plan", preflight_block)

    def test_workflow_does_not_enable_wait_plan_by_default(self):
        self.assertNotIn("RUN_ATLAS_BACKEND_E2E_WAIT_PLAN=1", self.workflow)
        self.assertNotIn("RUN_ATLAS_BACKEND_E2E=1", self.workflow)


if __name__ == "__main__":
    unittest.main()
