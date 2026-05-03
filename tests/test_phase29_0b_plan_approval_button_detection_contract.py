import pathlib
import unittest


class TestPhase290bPlanApprovalButtonDetectionContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke = pathlib.Path("scripts/smoke_ui_modes_playwright.py").read_text(encoding="utf-8")
        cls.workflow = pathlib.Path(".github/workflows/playwright-ui-smoke.yml").read_text(encoding="utf-8")

    def test_button_inventory_diagnostics_exist(self):
        for token in ["allButtons", "approvalCandidateButtons", "destructiveCandidateButtons"]:
            self.assertIn(token, self.smoke)
        self.assertTrue("approvalPanelTextTail" in self.smoke or "workbenchHtmlTail" in self.smoke)

    def test_approve_selector_candidates_are_expanded(self):
        for token in [
            "[data-action*=\\\"approve\\\"]",
            "[data-a*=\\\"approve\\\"]",
            "[id*=\\\"approve\\\"]",
            "approve plan",
            "approve_plan",
        ]:
            self.assertIn(token, self.smoke)

    def test_approve_button_inspected_not_clicked(self):
        self.assertIn("approveButtonPresent", self.smoke)
        self.assertIn("approveButtonEnabled", self.smoke)
        self.assertNotIn("approvePlan(", self.smoke)

    def test_failure_reason_explicit(self):
        self.assertIn("approval_required_but_approve_button_missing", self.smoke)

    def test_execute_patch_lock_aliases_exist(self):
        self.assertIn("executePreviewLocked", self.smoke)
        self.assertIn("execute_preview_locked", self.smoke)
        self.assertIn("patchApplyLocked", self.smoke)

    def test_destructive_actions_not_automated(self):
        for token in ["approvePlan(", "executePreview(", "applyPatch(", "bulk approve", "bulk apply", "auto approve", "auto apply"]:
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
