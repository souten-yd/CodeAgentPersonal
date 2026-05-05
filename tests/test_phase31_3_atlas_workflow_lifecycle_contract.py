import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = (ROOT / "ui.html").read_text(encoding="utf-8")
SMOKE = (ROOT / "scripts" / "smoke_ui_modes_playwright.py").read_text(encoding="utf-8")
MATRIX = (ROOT / "scripts" / "run_debug_test_matrix.py").read_text(encoding="utf-8")
MAIN = (ROOT / "main.py").read_text(encoding="utf-8")


class Phase313AtlasWorkflowLifecycleContract(unittest.TestCase):
    def test_wait_plan_success_is_plan_generated_review_ready_not_approval_click(self):
        wait_body = SMOKE.split("async def wait_atlas_plan_completion", 1)[1].split("async def collect_atlas_clarification_diag", 1)[0]
        self.assertIn('"plan_flow_plan_generated": "plan: generated"', wait_body)
        self.assertIn('"plan_flow_review_ready": "review: ready"', wait_body)
        self.assertIn('"completionDecisionReason": "plan_generated_review_ready"', wait_body)
        self.assertNotIn("approveButton.click", wait_body)
        self.assertNotIn("approvePlan(", wait_body)
        self.assertNotIn("executePreview(", wait_body)
        self.assertNotIn("applyPatch(", wait_body)

    def test_forbidden_contradictory_states_fail_fast(self):
        wait_body = SMOKE.split("async def wait_atlas_plan_completion", 1)[1].split("async def collect_atlas_clarification_diag", 1)[0]
        self.assertIn('"plan_pending_approval_required"', wait_body)
        self.assertIn('"plan_pending_patch_review_available"', wait_body)
        self.assertIn('"requirement_pending_approval_required"', wait_body)
        self.assertIn('"failure_signal_detected"', wait_body)
        self.assertIn('"no_current_job_id_or_sync_plan_id"', wait_body)
        self.assertIn('"current_job_missing_from_active_jobs_without_plan"', wait_body)

    def test_diagnostics_include_job_run_active_history_and_errors(self):
        diag_body = SMOKE.split("async def collect_atlas_job_lifecycle_diag", 1)[1].split("async def _write_atlas_lifecycle_snapshot", 1)[0]
        for token in [
            '"currentJobId"',
            '"currentRunId"',
            '"activeJobsResponse"',
            '"recentJobsResponse"',
            '"lastError"',
            '"preflightStatus"',
            '"atlasWorkflowStatusTextTail"',
            '"planFlowTextTail"',
        ]:
            self.assertIn(token, diag_body)
        self.assertIn("projects/default/jobs?limit=20", diag_body)
        self.assertIn("projects/default/history?limit=20", diag_body)
        self.assertIn("atlas_lifecycle_", SMOKE)

    def test_atlas_status_is_in_atlas_not_chat_and_start_uses_atlas_requirement(self):
        start_body = UI.split("async function startAtlasWorkflow()", 1)[1].split("function startAgentGuidedWorkflow", 1)[0]
        generate_body = UI.split("async function generatePlanOnlyFromInput", 1)[1].split("// ── PLAN APPROVAL", 1)[0]
        chat_block = UI.split("<!-- CHAT -->", 1)[1].split("<!-- ATLAS MODE -->", 1)[0]
        self.assertIn("requirementText", start_body)
        self.assertIn("generatePlanOnlyFromInput({ text: requirementText", UI)
        self.assertIn("source !== 'atlas'", generate_body)
        self.assertIn('id="atlas-workflow-status"', UI)
        self.assertNotIn("Atlas Workflow Status", chat_block)
        self.assertNotIn("Atlas status mirror", chat_block)

    def test_workflow_state_machine_locks_approval_until_plan_generated(self):
        derive_body = UI.split("function deriveAtlasPlanFlowState()", 1)[1].split("function findAtlasWorkflowTarget", 1)[0]
        self.assertIn("workflowPhase", UI)
        self.assertIn("flow.approval = 'locked'", derive_body)
        self.assertIn("flow.plan = 'running'", derive_body)
        self.assertIn("flow.plan = 'failed'", derive_body)
        self.assertIn("flow.plan = 'generated'", derive_body)
        self.assertIn("flow.review = hasReview ? 'ready' : 'pending'", derive_body)
        self.assertIn("flow.approval = hasApproved ? 'approved' : 'required'", derive_body)
        pending_block = derive_body.split("const flow =", 1)[1].split("if (hasPlan)", 1)[0]
        self.assertNotIn("required", pending_block)
        self.assertNotIn("available after preview", derive_body)

    def test_backend_sync_plan_exposes_lifecycle_ids(self):
        endpoint_body = MAIN.split('@app.post("/api/task/plan")', 1)[1].split('@app.get("/api/plans/{plan_id}")', 1)[0]
        self.assertIn('result["atlas_job_id"] = f"sync-plan:{sync_id}"', endpoint_body)
        self.assertIn('result["atlas_run_id"] = sync_id', endpoint_body)
        self.assertIn('result["job_status"]', endpoint_body)
        self.assertIn('result["plan_generated"] = bool(plan_id)', endpoint_body)

    def test_debug_matrix_current_ui_default_legacy_manual_and_no_destructive_presets(self):
        default_list = MATRIX.split('TEST_PRESETS: list[TestPreset] = [', 1)[1].split(']\n\nLEGACY_TEST_PRESETS', 1)[0]
        self.assertIn('TestPreset("atlas_current_ui_smoke"', default_list)
        for preset_id in [
            '"static_contracts"', '"atlas_current_ui_smoke"', '"backend_preflight"',
            '"backend_e2e_dry_run"', '"wait_plan"', '"clarification_resolution"',
            '"plan_approval_gate"', '"plan_approval_actionability"',
        ]:
            self.assertIn(preset_id, default_list)
        self.assertNotIn("ui_9of9_mock", default_list)
        self.assertNotIn("legacy_ui_9of9_mock", default_list)
        self.assertIn('TestPreset("legacy_ui_9of9_mock"', MATRIX)
        for forbidden in ['"approve_plan"', '"execute_preview"', '"apply_patch"']:
            self.assertNotIn(forbidden, MATRIX)

    def test_approval_presets_depend_on_wait_plan_and_do_not_click_destructive_actions(self):
        self.assertIn("plan approval gate failed: wait_plan_failed", SMOKE)
        self.assertIn("plan approval actionability failed: wait_plan_failed", SMOKE)
        self.assertIn("RUN_ATLAS_BACKEND_E2E_CHECK_PLAN_APPROVAL requires", SMOKE)
        banned = ["approvePlan(", "executePreview(", "applyPatch(", "bulk approve", "bulk apply", "auto approve", "auto apply"]
        lowered_smoke = SMOKE.lower()
        for token in banned:
            self.assertNotIn(token.lower(), lowered_smoke)

    def test_wait_plan_assertion_summary_is_compact_and_artifact_backed(self):
        self.assertIn("def compact_atlas_diag_reason", SMOKE)
        self.assertIn("artifact=atlas_lifecycle_final.json", SMOKE)
        self.assertIn('raise_compact_atlas_diag(diag, prefix="atlas wait-plan failed")', SMOKE)
        self.assertNotIn("atlas wait-plan did not complete successfully: {json.dumps(diag", SMOKE)

    def test_wait_plan_prompt_is_clear_non_destructive_and_ui_state_tracks_plan_result(self):
        self.assertIn("Create a non-destructive implementation plan for adding a small UI label", SMOKE)
        self.assertIn("lastPlanApiIds", UI)
        self.assertIn("generatedPlan", UI)
        self.assertIn("planMarkdown", UI)
        self.assertIn("apiAtlasJobId", SMOKE)
        self.assertIn("apiAtlasRunId", SMOKE)


if __name__ == "__main__":
    unittest.main()
