import unittest
from pathlib import Path


class TestPhase262BackendPreflightSummaryContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke = Path('scripts/smoke_ui_modes_playwright.py').read_text(encoding='utf-8')
        cls.workflow = Path('.github/workflows/playwright-ui-smoke.yml').read_text(encoding='utf-8')

    def test_preflight_scenario_exists_and_is_opt_in(self):
        self.assertIn('("atlas_backend_preflight", run_backend_preflight)', self.smoke)
        self.assertIn('RUN_ATLAS_BACKEND_PREFLIGHT', self.smoke)
        self.assertIn('backend preflight remains opt-in', self.smoke)

    def test_backend_e2e_gate_implies_preflight_added(self):
        self.assertIn('preflight_only_mode', self.smoke)
        self.assertIn('full_backend_e2e_mode', self.smoke)
        self.assertIn('("atlas_backend_preflight", run_backend_preflight)', self.smoke)
        self.assertIn('("atlas_backend_e2e_journey", verify_atlas_backend_e2e_journey)', self.smoke)

    def test_preflight_get_only_and_no_plan_post(self):
        self.assertIn('page.request.get(', self.smoke)
        self.assertNotIn('page.request.post("/api/task/plan"', self.smoke)
        self.assertNotIn('page.request.post(target_url', self.smoke)

    def test_preflight_diagnostics_fields(self):
        for token in ['"baseUrl"', '"health"', '"systemSummary"', '"settings"', '"projects"', '"modelDbStatus"', '"errors"']:
            self.assertIn(token, self.smoke)
        self.assertIn('INFO: backend preflight status', self.smoke)

    def test_summary_paths_remain(self):
        self.assertIn('PLAYWRIGHT_ARTIFACT_DIR / "summary.md"', self.smoke)
        self.assertIn('$GITHUB_STEP_SUMMARY', self.workflow)

    def test_default_workflow_does_not_enable_backend_optins(self):
        self.assertNotIn('RUN_ATLAS_BACKEND_PREFLIGHT=1', self.workflow)
        self.assertNotIn('RUN_ATLAS_BACKEND_E2E=1', self.workflow)

    def test_no_destructive_actions(self):
        for token in ['approvePlan(', 'executePreview', 'applyPatch', 'auto approve', 'auto apply']:
            self.assertNotIn(token, self.smoke)


if __name__ == '__main__':
    unittest.main()
