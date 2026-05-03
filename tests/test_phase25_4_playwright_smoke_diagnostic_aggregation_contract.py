import unittest
from pathlib import Path


class TestPhase254PlaywrightSmokeDiagnosticAggregationContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke = Path("scripts/smoke_ui_modes_playwright.py").read_text(encoding="utf-8")
        cls.workflow = Path(".github/workflows/playwright-ui-smoke.yml").read_text(encoding="utf-8")

    def test_scenario_aggregation_helpers_exist(self):
        self.assertIn("async def run_smoke_scenario(", self.smoke)
        self.assertIn("def print_smoke_summary(", self.smoke)
        self.assertIn("def has_smoke_failures(", self.smoke)

    def test_artifacts_directory_and_summary_are_used(self):
        self.assertIn("PLAYWRIGHT_ARTIFACT_DIR", self.smoke)
        self.assertIn("summary.md", self.smoke)
        self.assertIn("page.screenshot", self.smoke)

    def test_failure_does_not_stop_next_scenarios_and_finally_fails(self):
        self.assertIn("for scenario_name, scenario_fn in scenarios:", self.smoke)
        self.assertIn("await run_smoke_scenario(scenario_name, browser, base_url, scenario_fn, results, DEFAULT_DESKTOP_VIEWPORT)", self.smoke)
        self.assertIn("if has_smoke_failures(results):", self.smoke)
        self.assertIn("raise AssertionError", self.smoke)

    def test_workflow_uploads_artifacts_always(self):
        self.assertIn("uses: actions/upload-artifact@v4", self.workflow)
        self.assertIn("if: always()", self.workflow)
        self.assertIn("artifacts/playwright/**", self.workflow)

    def test_workflow_summary_append_exists(self):
        self.assertIn("$GITHUB_STEP_SUMMARY", self.workflow)
        self.assertIn("summary.md", self.workflow)

    def test_backend_e2e_remains_opt_in(self):
        self.assertNotIn("RUN_ATLAS_BACKEND_E2E=1", self.workflow)
        self.assertIn("RUN_ATLAS_BACKEND_E2E", self.smoke)

    def test_no_destructive_actions(self):
        lower = (self.smoke + "\n" + self.workflow).lower()
        for forbidden in [
            "approveplan(",
            "executepreview",
            "applypatch",
            "bulk apply",
            "bulk approve",
            "auto apply",
            "auto approve",
        ]:
            self.assertNotIn(forbidden, lower)


if __name__ == "__main__":
    unittest.main()
