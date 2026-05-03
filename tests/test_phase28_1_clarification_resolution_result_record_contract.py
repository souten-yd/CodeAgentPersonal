import pathlib
import unittest


class TestPhase281ClarificationResolutionResultRecordContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke = pathlib.Path("scripts/smoke_ui_modes_playwright.py").read_text(encoding="utf-8")
        cls.docs = pathlib.Path("docs/agent_guided_workflow_integration.md").read_text(encoding="utf-8")
        cls.readme = pathlib.Path("README.md").read_text(encoding="utf-8")
        cls.workflow = pathlib.Path(".github/workflows/playwright-ui-smoke.yml").read_text(encoding="utf-8")

    def test_docs_contain_phase_28_1_note(self):
        for token in [
            "Phase 28.1",
            "clarification resolution opt-in",
            "atlas_backend_e2e_resolve_clarification",
            "Total scenarios: 2",
            "PASS: 2",
        ]:
            self.assertIn(token, self.docs)

    def test_docs_record_allowed_final_states(self):
        for token in ["completed", "needs_clarification_after_resolution"]:
            self.assertIn(token, self.docs)

    def test_one_attempt_policy_remains(self):
        for token in ["at most once", "おまかせで進める", "No automatic clarification answer"]:
            self.assertIn(token, self.docs)

    def test_script_still_enforces_opt_in_gates(self):
        for token in [
            "RUN_ATLAS_BACKEND_E2E_RESOLVE_CLARIFICATION",
            "RUN_ATLAS_BACKEND_E2E_WAIT_PLAN",
            "RUN_ATLAS_BACKEND_E2E",
        ]:
            self.assertIn(token, self.smoke)

    def test_destructive_actions_are_not_automated(self):
        for token in ["approvePlan(", "executePreview", "applyPatch", "bulk approve", "bulk apply", "auto approve", "auto apply"]:
            self.assertNotIn(token, self.smoke)

    def test_preflight_remains_get_only(self):
        preflight_block = self.smoke.split("async def collect_backend_preflight_status(page) -> dict:", 1)[1].split(
            "\n\nasync def run_backend_preflight", 1
        )[0]
        self.assertNotIn("page.request.post(", preflight_block)
        self.assertNotIn("/api/task/plan", preflight_block)

    def test_workflow_default_does_not_enable_resolution(self):
        self.assertNotIn("RUN_ATLAS_BACKEND_E2E_RESOLVE_CLARIFICATION=1", self.workflow)
        self.assertNotIn("RUN_ATLAS_BACKEND_E2E_WAIT_PLAN=1", self.workflow)
        self.assertNotIn("RUN_ATLAS_BACKEND_E2E=1", self.workflow)


if __name__ == "__main__":
    unittest.main()
