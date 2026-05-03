import pathlib
import unittest


class TestPhase290cPlanApprovalInvalidSelectorGuardContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke = pathlib.Path("scripts/smoke_ui_modes_playwright.py").read_text(encoding="utf-8")
        cls.workflow = pathlib.Path(".github/workflows/playwright-ui-smoke.yml").read_text(encoding="utf-8")

    def test_no_has_text_in_page_evaluate_query_selectors(self):
        gate_block = self.smoke.split("async def collect_atlas_plan_approval_gate_diag(page) -> dict:", 1)[1].split(
            "\n\nasync def verify_atlas_plan_approval_gate_readiness", 1
        )[0]
        self.assertNotIn(":has-text(", gate_block)

    def test_dom_text_filtering_exists(self):
        for token in ["textContent", "approvalCandidateButtons", "承認", "approve"]:
            self.assertIn(token, self.smoke)

    def test_collector_exception_safe(self):
        for token in ["diagnosticError", "selectorErrors", "try", "catch"]:
            self.assertIn(token, self.smoke)

    def test_needs_clarification_skip_precedes_hard_assertions(self):
        verify_block = self.smoke.split("async def verify_atlas_plan_approval_gate_readiness(page, wait_diag: dict, console_errors: list[str], page_errors: list[str]) -> dict:", 1)[1].split(
            "\n\nasync def click_atlas_proceed_with_assumptions_once", 1
        )[0]
        skip_idx = verify_block.find("plan_approval_gate_skipped_needs_clarification")
        collect_idx = verify_block.find("collect_atlas_plan_approval_gate_diag")
        self.assertIn("needs_clarification_after_resolution", verify_block)
        self.assertGreaterEqual(skip_idx, 0)
        self.assertGreaterEqual(collect_idx, 0)
        self.assertLess(skip_idx, collect_idx)

    def test_completed_failure_reason_exists(self):
        self.assertIn("approval_required_but_approve_button_missing", self.smoke)

    def test_approve_inspected_not_clicked(self):
        self.assertIn("approveButtonPresent", self.smoke)
        self.assertIn("approveButtonEnabled", self.smoke)
        self.assertNotIn("approvePlan(", self.smoke)

    def test_destructive_actions_not_automated(self):
        for token in ["approvePlan(", "executePreview(", "applyPatch(", "bulk approve", "bulk apply", "auto approve", "auto apply"]:
            self.assertNotIn(token, self.smoke)

    def test_preflight_remains_get_only(self):
        preflight_block = self.smoke.split("async def collect_backend_preflight_status(page) -> dict:", 1)[1].split(
            "\n\nasync def run_backend_preflight", 1
        )[0]
        self.assertNotIn("page.request.post(", preflight_block)
        self.assertNotIn("/api/task/plan", preflight_block)

    def test_workflow_default_does_not_enable_gate(self):
        self.assertNotIn("RUN_ATLAS_BACKEND_E2E_CHECK_PLAN_APPROVAL=1", self.workflow)
        self.assertNotIn("RUN_ATLAS_BACKEND_E2E=1", self.workflow)
        self.assertNotIn("RUN_ATLAS_BACKEND_E2E_WAIT_PLAN=1", self.workflow)


if __name__ == "__main__":
    unittest.main()
