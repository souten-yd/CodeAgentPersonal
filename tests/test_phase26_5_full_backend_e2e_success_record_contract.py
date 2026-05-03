import unittest
from pathlib import Path


class TestPhase265FullBackendE2ESuccessRecordContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs = Path("docs/agent_guided_workflow_integration.md").read_text(encoding="utf-8")
        cls.smoke = Path("scripts/smoke_ui_modes_playwright.py").read_text(encoding="utf-8")
        cls.workflow = Path(".github/workflows/playwright-ui-smoke.yml").read_text(encoding="utf-8")

    def test_docs_contain_phase265_success_note(self):
        for token in [
            "Phase 26.5",
            "Windows local real-backend full E2E dry-run",
            "Total scenarios: 2",
            "PASS: 2",
            "atlas_backend_preflight",
            "atlas_backend_e2e_journey",
        ]:
            self.assertIn(token, self.docs)

    def test_docs_record_dry_run_state(self):
        for token in [
            "atlasSubview: plan",
            "Using Atlas requirement input",
            "hasAtlasStartFailed: False",
            "consoleErrors: []",
            "pageErrors: []",
        ]:
            self.assertIn(token, self.docs)

    def test_docs_record_no_destructive_action(self):
        for token in [
            "approval",
            "execute",
            "patch",
            "bulk",
            "dry-run stops before",
            "no destructive action",
        ]:
            self.assertIn(token, self.docs)

    def test_script_still_enforces_opt_in_scenario_isolation(self):
        for token in [
            "full_backend_e2e_mode",
            '("atlas_backend_preflight", run_backend_preflight)',
            '("atlas_backend_e2e_journey", verify_atlas_backend_e2e_journey)',
            "default UI scenarios are skipped in full backend E2E mode",
        ]:
            self.assertIn(token, self.smoke)

    def test_workflow_still_does_not_enable_backend_e2e_or_preflight(self):
        self.assertNotIn("RUN_ATLAS_BACKEND_E2E=1", self.workflow)
        self.assertNotIn("RUN_ATLAS_BACKEND_PREFLIGHT=1", self.workflow)

    def test_preflight_remains_get_only(self):
        preflight_block = self.smoke.split("async def collect_backend_preflight_status(page) -> dict:", 1)[1].split(
            "\n\nasync def run_backend_preflight", 1
        )[0]
        self.assertNotIn("page.request.post(", preflight_block)
        self.assertNotIn("/api/task/plan", preflight_block)

    def test_destructive_action_not_automated_in_smoke_script(self):
        backend_block = self.smoke.split("async def verify_atlas_backend_e2e_journey(page) -> None:", 1)[1].split(
            "\n\nasync def verify_nexus_tabs", 1
        )[0]
        for token in ["approvePlan(", "executePreview", "applyPatch", "auto approve", "auto apply"]:
            self.assertNotIn(token, backend_block)


if __name__ == "__main__":
    unittest.main()
