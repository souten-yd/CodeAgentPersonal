import re
import unittest
from pathlib import Path


class TestPhase261BackendPreflightDryRunSeparationContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke = Path("scripts/smoke_ui_modes_playwright.py").read_text(encoding="utf-8")
        cls.workflow = Path(".github/workflows/playwright-ui-smoke.yml").read_text(encoding="utf-8")

    def test_preflight_gate_exists(self):
        self.assertIn("RUN_ATLAS_BACKEND_PREFLIGHT", self.smoke)

    def test_preflight_helper_is_get_only(self):
        self.assertIn("async def collect_backend_preflight_status(page) -> dict:", self.smoke)
        for token in [
            '"/health"',
            '"/system/summary"',
            '"/settings"',
            '"/projects"',
            '"/models/db/status"',
            "page.request.get",
        ]:
            self.assertIn(token, self.smoke)
        m = re.search(r"async def collect_backend_preflight_status\(page\) -> dict:\n([\s\S]*?)\n\nasync def run_backend_preflight", self.smoke)
        self.assertIsNotNone(m)
        self.assertNotIn("page.request.post", m.group(1))

    def test_diag_plan_post_removed(self):
        self.assertNotIn("phase26 backend e2e diag plan probe", self.smoke)
        backend_block = re.search(r"async def verify_atlas_backend_e2e_journey\(page\) -> None:\n([\s\S]*?)\n\nasync def verify_nexus_tabs", self.smoke)
        self.assertIsNotNone(backend_block)
        self.assertNotIn('page.request.post("/api/task/plan"', backend_block.group(1))

    def test_full_backend_e2e_gate_and_failure_condition_remain(self):
        self.assertIn("RUN_ATLAS_BACKEND_E2E", self.smoke)
        self.assertIn('assert "Atlas Start failed:" not in const_messages', self.smoke)

    def test_default_workflow_does_not_enable_preflight_or_e2e(self):
        self.assertNotIn("RUN_ATLAS_BACKEND_E2E=1", self.workflow)
        self.assertNotIn("RUN_ATLAS_BACKEND_PREFLIGHT=1", self.workflow)

    def test_default_9_ui_smoke_scenarios_remain(self):
        for name in [
            "bootstrap_api_contract",
            "mode_switches",
            "atlas_start_button_feedback",
            "atlas_guided_workflow_safe_journey",
            "mode_specific_subtabs",
            "nexus_tabs",
            "reference_card_actions",
            "chat_search_and_agent_web_tool_tts",
            "mobile_mode_switches",
        ]:
            self.assertIn(name, self.smoke)

    def test_no_destructive_actions(self):
        for token in ["approvePlan(", "executePreview", "applyPatch", "auto approve", "auto apply"]:
            self.assertNotIn(token, self.smoke)


if __name__ == "__main__":
    unittest.main()
