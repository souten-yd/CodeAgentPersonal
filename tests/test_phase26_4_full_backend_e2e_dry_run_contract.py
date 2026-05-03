import unittest
from pathlib import Path


class TestPhase264FullBackendE2EDryRunContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke = Path("scripts/smoke_ui_modes_playwright.py").read_text(encoding="utf-8")
        cls.workflow = Path(".github/workflows/playwright-ui-smoke.yml").read_text(encoding="utf-8")

    def test_full_e2e_opt_in_gate_remains(self):
        self.assertIn("RUN_ATLAS_BACKEND_E2E", self.smoke)
        self.assertIn("full_backend_e2e_mode", self.smoke)

    def test_full_e2e_scenarios_are_isolated(self):
        self.assertIn('(\"atlas_backend_preflight\", run_backend_preflight)', self.smoke)
        self.assertIn('(\"atlas_backend_e2e_journey\", verify_atlas_backend_e2e_journey)', self.smoke)
        self.assertNotIn('(\"mode_switches\", verify_mode_switches)', self.smoke.split("elif full_backend_e2e_mode:")[1].split("else:")[0])

    def test_full_e2e_presses_atlas_start_with_requirement(self):
        self.assertIn("phase1-plan-btn", self.smoke)
        self.assertIn("atlas_requirement", self.smoke)

    def test_atlas_start_failed_is_failure_condition(self):
        self.assertIn('assert "Atlas Start failed:" not in const_messages', self.smoke)

    def test_success_signals_remain(self):
        for token in [
            "Atlas Workflow Status",
            "Requirement Source: atlas",
            "Source: atlas",
            "Workspace: Atlas",
            "Using Atlas requirement input",
        ]:
            self.assertIn(token, self.smoke)

    def test_destructive_actions_not_automated(self):
        backend_block = self.smoke.split("async def verify_atlas_backend_e2e_journey(page) -> None:", 1)[1].split("\n\nasync def verify_nexus_tabs", 1)[0]
        for token in [
            "approvePlan(",
            "executePreview",
            "applyPatch",
            "bulk approve",
            "bulk apply",
            "auto approve",
            "auto apply",
        ]:
            self.assertNotIn(token, backend_block)

    def test_preflight_remains_get_only(self):
        preflight_block = self.smoke.split("async def collect_backend_preflight_status(page) -> dict:", 1)[1].split("\n\nasync def run_backend_preflight", 1)[0]
        self.assertNotIn("/api/task/plan", preflight_block)
        self.assertNotIn("page.request.post", preflight_block)

    def test_workflow_does_not_enable_backend_e2e_by_default(self):
        self.assertNotIn("RUN_ATLAS_BACKEND_E2E=1", self.workflow)


if __name__ == "__main__":
    unittest.main()
