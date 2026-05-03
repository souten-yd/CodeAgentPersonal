import pathlib
import unittest


class TestPhase280ClarificationResolutionOptInContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke = pathlib.Path("scripts/smoke_ui_modes_playwright.py").read_text(encoding="utf-8")
        cls.docs = pathlib.Path("docs/agent_guided_workflow_integration.md").read_text(encoding="utf-8")
        cls.readme = pathlib.Path("README.md").read_text(encoding="utf-8")
        cls.workflow = pathlib.Path(".github/workflows/playwright-ui-smoke.yml").read_text(encoding="utf-8")

    def test_new_env_gate_exists(self):
        self.assertIn("RUN_ATLAS_BACKEND_E2E_RESOLVE_CLARIFICATION", self.smoke)

    def test_gate_requires_e2e_and_wait_plan(self):
        self.assertIn("RUN_ATLAS_BACKEND_E2E_RESOLVE_CLARIFICATION requires RUN_ATLAS_BACKEND_E2E=1 and RUN_ATLAS_BACKEND_E2E_WAIT_PLAN=1.", self.smoke)

    def test_scenario_exists(self):
        self.assertIn("atlas_backend_e2e_resolve_clarification", self.smoke)

    def test_resolution_helper_exists(self):
        self.assertIn("async def resolve_atlas_clarification_once(page)", self.smoke)

    def test_one_attempt_limit(self):
        self.assertEqual(self.smoke.count("resolve_atlas_clarification_once(page)"), 2)
        self.assertIn('if diag.get("finalDecision") == "needs_clarification" and run_backend_resolve_clarification_opt_in', self.smoke)

    def test_proceed_with_assumptions_only_under_opt_in(self):
        for token in ["おまかせで進める", "proceed_with_assumptions", "resolutionAttempted"]:
            self.assertIn(token, self.smoke)

    def test_does_not_auto_answer_clarification(self):
        for token in ["clarification-input", "textarea[name='clarification']", "textarea#clarification-answer"]:
            self.assertIn(token, self.smoke)
        self.assertNotIn("generate clarification answer", self.smoke.lower())
        self.assertNotIn("fill(\"#atlas-clarification-input\"", self.smoke)

    def test_does_not_click_destructive_buttons(self):
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
