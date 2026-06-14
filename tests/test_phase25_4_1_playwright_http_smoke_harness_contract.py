import unittest
import importlib.util
import sys
import urllib.request
from pathlib import Path


class TestPhase2541PlaywrightHttpSmokeHarnessContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke = Path("scripts/smoke_ui_modes_playwright.py").read_text(encoding="utf-8")
        cls.workflow = Path(".github/workflows/playwright-ui-smoke.yml").read_text(encoding="utf-8")

    def test_file_scheme_not_used_for_smoke_base(self):
        self.assertNotIn("as_uri()", self.smoke)
        self.assertNotIn("file://", self.smoke)

    def test_http_mock_server_exists(self):
        for token in ["ThreadingHTTPServer", "127.0.0.1", '"/settings"', '"/health"', '"/system/summary"', '"/api/task/plan"']:
            self.assertIn(token, self.smoke)
        for token in ["_serve_static_asset", 'path.startswith("/static/")', 'path.startswith("/assets/")']:
            self.assertIn(token, self.smoke)

    def test_mock_server_serves_static_assets(self):
        spec = importlib.util.spec_from_file_location(
            "smoke_ui_modes_playwright_contract",
            Path("scripts/smoke_ui_modes_playwright.py"),
        )
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        sys.path.insert(0, str(Path("scripts").resolve()))
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        server, _thread = module.start_mock_server()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            js = urllib.request.urlopen(f"{base}/static/js/atlas_claude_panel.js", timeout=10)
            self.assertIn("javascript", js.headers.get("Content-Type", "").lower())
            self.assertIn(b"AtlasClaudePanel", js.read())
            css = urllib.request.urlopen(f"{base}/static/css/app.css", timeout=10)
            self.assertIn("css", css.headers.get("Content-Type", "").lower())
            self.assertIn(b"atlas-claude-llm-progress", css.read())
        finally:
            server.shutdown()
            server.server_close()

    def test_atlas_reload_resume_progress_smoke_exists(self):
        for token in [
            "verify_atlas_reload_resume_progress_smoke",
            '"atlas_reload_resume_progress_smoke"',
            "pool_auir5_reload",
            "run_auir5_reload",
            "/api/atlas/pipeline/events/pool_auir5_reload/run_auir5_reload",
            "atlas_claude_last_event_sequence",
            "tokens 64 / 8192",
        ]:
            self.assertIn(token, self.smoke)

    def test_scenario_isolation_exists(self):
        self.assertIn("await browser.new_page", self.smoke)
        self.assertIn("await page.close()", self.smoke)
        self.assertIn("DEFAULT_DESKTOP_VIEWPORT", self.smoke)
        self.assertIn("DEFAULT_MOBILE_VIEWPORT", self.smoke)

    def test_chat_input_helpers_exist(self):
        self.assertIn("async def set_chat_input", self.smoke)
        self.assertIn("async def get_chat_input_value", self.smoke)

    def test_summary_and_artifact_improvements_exist(self):
        self.assertIn("summary.md", self.smoke)
        self.assertIn("PLAYWRIGHT_ARTIFACT_DIR", self.smoke)
        self.assertIn(".log", self.smoke)

    def test_workflow_artifact_upload_and_step_summary_exist(self):
        self.assertIn("uses: actions/upload-artifact@v4", self.workflow)
        self.assertIn("if: always()", self.workflow)
        self.assertIn("$GITHUB_STEP_SUMMARY", self.workflow)

    def test_backend_e2e_default_stays_off(self):
        self.assertNotIn("RUN_ATLAS_BACKEND_E2E=1", self.workflow)

    def test_no_destructive_actions(self):
        lower = (self.smoke + "\n" + self.workflow).lower()
        for forbidden in ["approveplan(", "executepreview", "applypatch", "bulk apply", "bulk approve", "auto apply", "auto approve"]:
            self.assertNotIn(forbidden, lower)


if __name__ == "__main__":
    unittest.main()
