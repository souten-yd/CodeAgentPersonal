import unittest
from pathlib import Path


class TestPhase261bPlaywrightSmokeRegressionGuardContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke = Path("scripts/smoke_ui_modes_playwright.py").read_text(encoding="utf-8")
        cls.workflow = Path(".github/workflows/playwright-ui-smoke.yml").read_text(encoding="utf-8")

    def test_atlas_start_feedback_restores_errors_capture(self):
        anchor = "async def verify_atlas_start_button_feedback(page) -> None:"
        idx = self.smoke.find(anchor)
        self.assertNotEqual(idx, -1)
        block = self.smoke[idx: idx + 1200]
        self.assertIn("errors: list[str] = []", block)
        self.assertIn('page.on("pageerror"', block)
        self.assertIn('page.on("console"', block)

    def test_assert_not_errors_requires_errors_definition_same_function(self):
        anchor = "async def verify_atlas_start_button_feedback(page) -> None:"
        idx = self.smoke.find(anchor)
        self.assertNotEqual(idx, -1)
        tail = self.smoke[idx:self.smoke.find("async def verify_atlas_guided_workflow_safe_journey", idx)]
        if "assert not errors" in tail:
            self.assertIn("errors: list[str] = []", tail)

    def test_phase261_separation_contracts_still_present(self):
        for token in [
            "collect_backend_preflight_status",
            "run_backend_preflight",
            "RUN_ATLAS_BACKEND_PREFLIGHT",
            "RUN_ATLAS_BACKEND_E2E",
        ]:
            self.assertIn(token, self.smoke)
        self.assertNotIn('page.request.post("/api/task/plan"', self.smoke)
        self.assertNotIn("RUN_ATLAS_BACKEND_E2E=1", self.workflow)

    def test_source_url_download_remain_diagnostic_only(self):
        self.assertIn("Source URL action did not open a URL; continuing because Source URL is diagnostic-only.", self.smoke)
        self.assertIn("Download action inspected only; not clicked to avoid current-page navigation in UI smoke.", self.smoke)

    def test_no_auto_approval_execute_patch_apply(self):
        forbidden = ["approvePlan(", "executePreview", "applyPatch", "auto approve", "auto execute", "auto apply"]
        for token in forbidden:
            self.assertNotIn(token, self.smoke)


if __name__ == "__main__":
    unittest.main()
