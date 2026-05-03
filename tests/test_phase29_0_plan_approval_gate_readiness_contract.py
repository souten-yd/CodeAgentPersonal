import pathlib
import unittest


class TestPhase290PlanApprovalGateReadinessContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke = pathlib.Path("scripts/smoke_ui_modes_playwright.py").read_text(encoding="utf-8")
        cls.workflow = pathlib.Path(".github/workflows/playwright-ui-smoke.yml").read_text(encoding="utf-8")

    def test_new_env_gate_exists(self):
        self.assertIn("RUN_ATLAS_BACKEND_E2E_CHECK_PLAN_APPROVAL", self.smoke)

    def test_gate_requires_e2e_and_wait_plan(self):
        self.assertIn(
            "RUN_ATLAS_BACKEND_E2E_CHECK_PLAN_APPROVAL requires RUN_ATLAS_BACKEND_E2E=1 and RUN_ATLAS_BACKEND_E2E_WAIT_PLAN=1.",
            self.smoke,
        )

    def test_scenario_exists(self):
        self.assertIn("atlas_backend_e2e_plan_approval_gate", self.smoke)

    def test_helper_exists(self):
        self.assertTrue(
            "async def collect_atlas_plan_approval_gate_diag(page)" in self.smoke
            or "async def verify_atlas_plan_approval_gate_readiness(page" in self.smoke
        )

    def test_approve_button_inspected_not_clicked(self):
        self.assertIn("approveButtonPresent", self.smoke)
        self.assertIn("approveButtonEnabled", self.smoke)
        self.assertNotIn("approvePlan(", self.smoke)

    def test_execute_patch_locked(self):
        self.assertIn("execute_preview_locked", self.smoke)
        self.assertIn("patchApplyLocked", self.smoke)

    def test_needs_clarification_skip_path_exists(self):
        self.assertIn("plan_approval_gate_skipped_needs_clarification", self.smoke)
        self.assertIn("needs_clarification_after_resolution", self.smoke)

    def test_destructive_actions_not_automated(self):
        for token in ["approvePlan(", "executePreview", "applyPatch", "bulk approve", "bulk apply", "auto approve", "auto apply"]:
            self.assertNotIn(token, self.smoke)

    def test_preflight_remains_get_only(self):
        preflight_block = self.smoke.split("async def collect_backend_preflight_status(page) -> dict:", 1)[1].split(
            "\n\nasync def run_backend_preflight", 1
        )[0]
        self.assertNotIn("page.request.post(", preflight_block)
        self.assertNotIn("/api/task/plan", preflight_block)

    def test_workflow_default_does_not_enable_gate(self):
        self.assertNotIn("RUN_ATLAS_BACKEND_E2E_CHECK_PLAN_APPROVAL=1", self.workflow)
        self.assertNotIn("RUN_ATLAS_BACKEND_E2E=1", self.workflow)
        self.assertNotIn("RUN_ATLAS_BACKEND_E2E_WAIT_PLAN=1", self.workflow)


if __name__ == "__main__":
    unittest.main()
