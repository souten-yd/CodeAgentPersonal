import re
import unittest
from pathlib import Path


class TestPhase252PlaywrightSmokeSplitContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke = Path("scripts/smoke_ui_modes_playwright.py").read_text(encoding="utf-8")

    def test_ui_smoke_function_remains(self):
        self.assertIn("async def verify_atlas_guided_workflow_safe_journey(page) -> None:", self.smoke)

    def test_backend_e2e_function_exists(self):
        self.assertIn("async def verify_atlas_backend_e2e_journey(page) -> None:", self.smoke)

    def test_backend_e2e_env_gate_exists(self):
        self.assertIn("RUN_ATLAS_BACKEND_E2E", self.smoke)
        self.assertIn("SKIP: RUN_ATLAS_BACKEND_E2E is not set", self.smoke)

    def test_backend_e2e_rejects_atlas_start_failed(self):
        m = re.search(r"async def verify_atlas_backend_e2e_journey\(page\) -> None:\n([\s\S]*?)\n\nasync def", self.smoke)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("Atlas Start failed:", body)
        self.assertIn("not in const_messages", body)

    def test_ui_smoke_accepts_visible_failure(self):
        m = re.search(r"async def verify_atlas_guided_workflow_safe_journey\(page\) -> None:\n([\s\S]*?)\n\nasync def verify_atlas_backend_e2e_journey", self.smoke)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("Atlas Start failed is visible in UI; accepted for backend-unavailable safe journey smoke.", body)

    def test_playwright_install_guidance_exists(self):
        self.assertIn("python -m pip install playwright", self.smoke)
        self.assertIn("python -m playwright install chromium", self.smoke)

    def test_no_destructive_actions(self):
        lower = self.smoke.lower()
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
