import pathlib
import unittest


class TestPhase27AtlasJobLifecycleWaitPlanContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke = pathlib.Path("scripts/smoke_ui_modes_playwright.py").read_text(encoding="utf-8")
        cls.workflow = pathlib.Path(".github/workflows/ci.yml").read_text(encoding="utf-8") if pathlib.Path(".github/workflows/ci.yml").exists() else ""

    def test_new_opt_in_gate_exists(self):
        self.assertIn("RUN_ATLAS_BACKEND_E2E_WAIT_PLAN", self.smoke)

    def test_wait_plan_requires_e2e(self):
        self.assertIn("RUN_ATLAS_BACKEND_E2E_WAIT_PLAN requires RUN_ATLAS_BACKEND_E2E=1.", self.smoke)

    def test_modes_remain_defined(self):
        self.assertIn('("atlas_backend_preflight", run_backend_preflight)', self.smoke)
        self.assertIn('("atlas_backend_e2e_journey", verify_atlas_backend_e2e_journey)', self.smoke)

    def test_wait_plan_helpers_exist(self):
        self.assertIn("async def wait_atlas_plan_completion", self.smoke)
        self.assertIn("async def collect_atlas_job_lifecycle_diag", self.smoke)

    def test_diagnostics_fields_exist(self):
        for token in [
            "planFlowTextTail",
            "messagesTail",
            "lastError",
            "activeJobsResponse",
            "recentJobsResponse",
            "consoleErrors",
            "pageErrors",
            "elapsedMs",
        ]:
            self.assertIn(token, self.smoke)

    def test_backend_probes_get_only(self):
        block = self.smoke.split("async def collect_atlas_job_lifecycle_diag", 1)[1].split("async def wait_atlas_plan_completion", 1)[0]
        self.assertIn("page.request.get", block)
        self.assertNotIn("page.request.post", block)
        self.assertNotIn("/api/task/plan", block)

    def test_destructive_actions_not_automated(self):
        for token in ["approvePlan(", "executePreview", "applyPatch", "bulk approve", "bulk apply", "auto approve", "auto apply"]:
            self.assertNotIn(token, self.smoke)

    def test_workflow_does_not_enable_by_default(self):
        self.assertNotIn("RUN_ATLAS_BACKEND_E2E_WAIT_PLAN=1", self.workflow)
        self.assertNotIn("RUN_ATLAS_BACKEND_E2E=1", self.workflow)


    def test_wait_plan_scenario_branch_is_exclusive(self):
        self.assertIn("if run_backend_wait_plan_opt_in:", self.smoke)
        self.assertIn('("atlas_backend_e2e_wait_plan", verify_atlas_backend_e2e_wait_plan)', self.smoke)
        self.assertIn("scenarios = [", self.smoke)
        self.assertIn('("atlas_backend_e2e_journey", verify_atlas_backend_e2e_journey)', self.smoke)
        self.assertNotIn('scenarios.append(("atlas_backend_e2e_wait_plan", verify_atlas_backend_e2e_wait_plan))', self.smoke)

    def test_wait_plan_does_not_call_dry_run_helper(self):
        wait_plan_block = self.smoke.split("async def verify_atlas_backend_e2e_wait_plan", 1)[1].split("if run_backend_wait_plan_opt_in:", 1)[0]
        self.assertNotIn("await verify_atlas_backend_e2e_journey(page)", wait_plan_block)

    def test_failure_detection_avoids_generic_error_token(self):
        wait_block = self.smoke.split("async def wait_atlas_plan_completion", 1)[1].split("async def verify_nexus_tabs", 1)[0]
        self.assertNotIn('[" job failed", "failed", "error", "timeout"]', wait_block)
        self.assertIn('last_error not in ("", "-")', wait_block)

    def test_lifecycle_get_diagnostics_are_exception_safe(self):
        block = self.smoke.split("async def collect_atlas_job_lifecycle_diag", 1)[1].split("async def wait_atlas_plan_completion", 1)[0]
        for token in ['"status"', '"ok"', '"json"', '"jsonError"', '"error"']:
            self.assertIn(token, block)


if __name__ == "__main__":
    unittest.main()
