import unittest
from pathlib import Path


class TestPhase291PlanApprovalActionabilityContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke = Path("scripts/smoke_ui_modes_playwright.py").read_text(encoding="utf-8")
        cls.workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8") if Path(".github/workflows/ci.yml").exists() else ""

    def test_new_env_gate_exists(self):
        self.assertIn("RUN_ATLAS_BACKEND_E2E_CHECK_PLAN_APPROVAL_ACTIONABLE", self.smoke)

    def test_actionability_gate_requires_parent_opt_ins(self):
        self.assertIn(
            "RUN_ATLAS_BACKEND_E2E_CHECK_PLAN_APPROVAL_ACTIONABLE requires RUN_ATLAS_BACKEND_E2E=1, RUN_ATLAS_BACKEND_E2E_WAIT_PLAN=1, and RUN_ATLAS_BACKEND_E2E_CHECK_PLAN_APPROVAL=1.",
            self.smoke,
        )

    def test_actionability_scenario_exists(self):
        self.assertIn("atlas_backend_e2e_plan_approval_actionability", self.smoke)

    def test_actionability_helper_exists(self):
        self.assertTrue(
            "async def open_atlas_approval_panel_for_inspection(page)" in self.smoke
            or "async def verify_atlas_plan_approval_actionability(page" in self.smoke
        )

    def test_open_approval_panel_click_and_diag_exist(self):
        self.assertIn("Open Approval Panel", self.smoke)
        self.assertIn("openApprovalPanelClicked", self.smoke)

    def test_approve_inspected_not_clicked(self):
        self.assertIn("approveButtonActionableCandidate", self.smoke)
        self.assertIn("approveButtonVisible", self.smoke)
        self.assertIn("approveButtonEnabled", self.smoke)
        self.assertNotIn("approvePlan(", self.smoke)

    def test_execute_patch_locked_checked(self):
        self.assertIn("executePreviewLocked", self.smoke)
        self.assertIn("patchApplyLocked", self.smoke)

    def test_no_destructive_automation_added(self):
        lowered = self.smoke.lower()
        self.assertNotIn("approveplan(", lowered)
        self.assertNotIn("executepreview(", lowered)
        self.assertNotIn("applypatch(", lowered)
        self.assertNotIn("bulk approve", lowered)
        self.assertNotIn("bulk apply", lowered)
        self.assertNotIn("auto approve", lowered)
        self.assertNotIn("auto apply", lowered)

    def test_preflight_remains_get_only(self):
        preflight_block = self.smoke.split("async def run_backend_preflight", 1)[1].split("\n\nasync def verify_atlas_backend_e2e_journey", 1)[0]
        self.assertNotIn("page.request.post(", preflight_block)
        self.assertNotIn("/api/task/plan", preflight_block)

    def test_workflow_default_does_not_enable_backend_e2e(self):
        self.assertNotIn("RUN_ATLAS_BACKEND_E2E_CHECK_PLAN_APPROVAL_ACTIONABLE=1", self.workflow)
        self.assertNotIn("RUN_ATLAS_BACKEND_E2E_CHECK_PLAN_APPROVAL=1", self.workflow)
        self.assertNotIn("RUN_ATLAS_BACKEND_E2E=1", self.workflow)


if __name__ == "__main__":
    unittest.main()
