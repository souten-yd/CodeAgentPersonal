import unittest
from pathlib import Path


class TestPhase255PlaywrightUiSmoke9of9LockContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke = Path("scripts/smoke_ui_modes_playwright.py").read_text(encoding="utf-8")
        cls.workflow = Path(".github/workflows/playwright-ui-smoke.yml").read_text(encoding="utf-8")
        cls.docs = Path("docs/agent_guided_workflow_integration.md").read_text(encoding="utf-8")

    def test_scenarios_are_fixed_to_current_9(self):
        scenarios = [
            "bootstrap_api_contract",
            "mode_switches",
            "atlas_start_button_feedback",
            "atlas_guided_workflow_safe_journey",
            "mode_specific_subtabs",
            "nexus_tabs",
            "reference_card_actions",
            "chat_search_and_agent_web_tool_tts",
            "mobile_mode_switches",
        ]
        for name in scenarios:
            self.assertIn(name, self.smoke)

    def test_aggregation_and_summary_contract(self):
        for token in [
            "run_smoke_scenario",
            "print_smoke_summary",
            'PLAYWRIGHT_ARTIFACT_DIR / "summary.md"',
            "has_smoke_failures",
            "raise AssertionError",
        ]:
            self.assertIn(token, self.smoke)

    def test_http_origin_mock_contract(self):
        required = [
            "ThreadingHTTPServer",
            '"127.0.0.1"',
            "PLAYWRIGHT_SMOKE_BASE_URL",
            "/settings",
            "/health",
            "/system/summary",
            "/api/task/plan",
        ]
        for token in required:
            self.assertIn(token, self.smoke)
        self.assertNotIn("file://", self.smoke)

    def test_source_url_download_are_diagnostic_only(self):
        for token in [
            "sourceUrlActionStatus",
            "downloadActionStatus",
            "sourceUrlButtonState",
            "downloadButtonState",
        ]:
            self.assertIn(token, self.smoke)
        forbidden = [
            'assert any("https://example.com/report" in url for url in opened_urls)',
            'assert any("https://example.com/report" in url for url in tracking["openedUrls"])',
            'assert any("/nexus/sources/src-1/original" in url for url in tracking["openedUrls"])',
            'assert any("/nexus/sources/src-1/original" in url for url in tracking["fetchedUrls"])',
            'assert any("/nexus/sources/src-1/original" in url for url in opened_urls)',
            'assert any("/nexus/sources/src-1/original" in url for url in fetched_urls)',
            "force=True",
        ]
        for token in forbidden:
            self.assertNotIn(token, self.smoke)

    def test_full_text_and_highlight_remain_required(self):
        for token in [
            "/nexus/sources/src-1/text",
            "/nexus/sources/src-1/chunks",
            "source_id: src-1",
            "mode: text",
            "doc-1:0",
        ]:
            self.assertIn(token, self.smoke)

    def test_backend_e2e_opt_in_gate_remains(self):
        self.assertIn("RUN_ATLAS_BACKEND_E2E", self.smoke)
        self.assertNotIn("RUN_ATLAS_BACKEND_E2E=1", self.workflow)

    def test_optional_manual_workflow_contract(self):
        for token in [
            "workflow_dispatch",
            "actions/upload-artifact",
            "if: always()",
            "GITHUB_STEP_SUMMARY",
            "scripts/check_ui_inline_script_syntax.py",
            "scripts/smoke_ui_modes_playwright.py",
        ]:
            self.assertIn(token, self.workflow)
        self.assertNotIn("pull_request:", self.workflow)
        self.assertNotIn("push:", self.workflow)

    def test_no_destructive_actions_added(self):
        banned = ["approvePlan(", "executePreview", "applyPatch", "bulk apply", "bulk approve", "auto apply", "auto approve"]
        for token in banned:
            self.assertNotIn(token, self.smoke)

    def test_phase255_docs_note_present(self):
        self.assertIn("Phase 25.5 note", self.docs)
        self.assertIn("Playwright UI smoke reached 9/9 PASS", self.docs)


if __name__ == "__main__":
    unittest.main()
