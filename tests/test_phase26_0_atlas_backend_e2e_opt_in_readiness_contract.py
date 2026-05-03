import unittest
from pathlib import Path


class TestPhase260AtlasBackendE2EOptInReadinessContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke = Path("scripts/smoke_ui_modes_playwright.py").read_text(encoding="utf-8")
        cls.workflow = Path(".github/workflows/playwright-ui-smoke.yml").read_text(encoding="utf-8")
        cls.docs = Path("docs/agent_guided_workflow_integration.md").read_text(encoding="utf-8")
        cls.readme = Path("README.md").read_text(encoding="utf-8")

    def test_run_atlas_backend_e2e_gate_and_default_skip_exist(self):
        self.assertIn("RUN_ATLAS_BACKEND_E2E", self.smoke)
        self.assertIn("SKIP: RUN_ATLAS_BACKEND_E2E is not set", self.smoke)

    def test_default_workflow_does_not_enable_backend_e2e(self):
        self.assertNotIn("RUN_ATLAS_BACKEND_E2E=1", self.workflow)

    def test_real_backend_base_url_path_exists(self):
        self.assertIn("PLAYWRIGHT_SMOKE_BASE_URL", self.smoke)

    def test_backend_e2e_rejects_atlas_start_failed(self):
        self.assertIn('assert "Atlas Start failed:" not in const_messages', self.smoke)
        self.assertIn('backend E2E smoke must not accept Atlas Start failed', self.smoke)

    def test_no_auto_approve_execute_apply_in_smoke(self):
        for token in ["approvePlan(", "executePreview", "applyPatch", "auto approve", "auto apply"]:
            self.assertNotIn(token, self.smoke)

    def test_backend_e2e_success_signals_remain(self):
        for token in [
            "Atlas Workflow Status",
            "Requirement Source: atlas",
            "Source: atlas",
            "Workspace: Atlas",
            "Using Atlas requirement input.",
        ]:
            self.assertIn(token, self.smoke)

    def test_docs_mention_opt_in_command(self):
        combined = self.docs + "\n" + self.readme
        self.assertIn("RUN_ATLAS_BACKEND_E2E=1", combined)
        self.assertIn("PLAYWRIGHT_SMOKE_BASE_URL", combined)


if __name__ == "__main__":
    unittest.main()
