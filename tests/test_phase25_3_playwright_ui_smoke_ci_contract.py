import unittest
from pathlib import Path


class TestPhase253PlaywrightUiSmokeCiContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke = Path("scripts/smoke_ui_modes_playwright.py").read_text(encoding="utf-8")
        cls.readme = Path("README.md").read_text(encoding="utf-8")
        cls.workflow = Path(".github/workflows/playwright-ui-smoke.yml")
        cls.workflow_text = cls.workflow.read_text(encoding="utf-8") if cls.workflow.exists() else ""

    def test_playwright_install_guidance_remains(self):
        self.assertIn("python -m pip install playwright", self.smoke)
        self.assertIn("python -m playwright install chromium", self.smoke)

    def test_backend_e2e_remains_opt_in(self):
        self.assertIn("RUN_ATLAS_BACKEND_E2E", self.smoke)
        self.assertIn("SKIP: RUN_ATLAS_BACKEND_E2E is not set", self.smoke)

    def test_ui_smoke_function_remains_default_path(self):
        self.assertIn("async def verify_atlas_guided_workflow_safe_journey(page) -> None:", self.smoke)
        self.assertIn("await verify_atlas_guided_workflow_safe_journey(page)", self.smoke)

    def test_backend_e2e_function_exists_with_gate(self):
        self.assertIn("async def verify_atlas_backend_e2e_journey(page) -> None:", self.smoke)
        self.assertIn("if os.environ.get(\"RUN_ATLAS_BACKEND_E2E\", \"\").strip() != \"1\":", self.smoke)

    def test_optional_ci_workflow_exists_and_does_not_force_backend_e2e(self):
        self.assertTrue(self.workflow.exists(), "optional Playwright UI smoke workflow should exist")
        self.assertIn("workflow_dispatch", self.workflow_text)
        self.assertIn("python scripts/smoke_ui_modes_playwright.py", self.workflow_text)
        self.assertNotIn("RUN_ATLAS_BACKEND_E2E=1", self.workflow_text)

    def test_no_destructive_actions(self):
        lower = self.smoke.lower() + "\n" + self.workflow_text.lower()
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

    def test_readme_has_playwright_smoke_commands(self):
        self.assertIn("python scripts/smoke_ui_modes_playwright.py", self.readme)
        self.assertIn("RUN_ATLAS_BACKEND_E2E=1 python scripts/smoke_ui_modes_playwright.py", self.readme)


if __name__ == "__main__":
    unittest.main()
